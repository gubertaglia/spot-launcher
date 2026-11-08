from heapq import merge
from itertools import islice
from urllib.parse import quote, urlsplit
import os
import subprocess
import time
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")

from gi.repository import Adw, Gdk, Gio, GLib, Gsk, Gtk
from src import _
from src.history import HistoryManager
from src.indexer import AppIndexer
from src.matcher import SearchMatcher
from src.search import search_score, result_key
from src.search_commands import command_query, command_suggestion, CommandSuggestion
from src.calculator import CalculatorPlugin
from src.files import FileSearchEngine, file_query
from src.tools import ToolsEngine
from src.tools import normalize_text
from src.calendar_view import CalendarView
from src.worker import LatestRequestWorker
from src.updater import check_update, install_update
from src.dictionary import lookup as dictionary_lookup
from src.translation import translate
from src.web import dictionary_search, translation_search, map_destination, map_search, web_search
from src.system_actions import system_actions, execute_action
from src.placement import hide_from_dock, position, default_position, gnome_placement
from src.scaled_layout import ScaledLayout
from src.terminal import get_default_terminal
from src.preferences import ConfigManager, PreferencesWindow, apply_theme, launcher_scale

RESULT_SHORTCUTS = "123456789abcdefghijklmnopqrstuvwxyz"

LAUNCHER_CSS = """
window.spotlight-window,
window.spotlight-window.background,
window.spotlight-window > contents {
    background: transparent;
    background-color: transparent;
    box-shadow: none;
    border: none;
    min-height: 0px;
}

.spotlight-card {
    background-color: @window_bg_color;
    border-radius: 20px;
    border: 1px solid alpha(@window_fg_color, 0.12);
    box-shadow: 0 12px 28px rgba(0, 0, 0, 0.24);
    padding: 12px;
}

window.blur-my-shell .spotlight-card {
    background-color: alpha(@window_bg_color, 0.78);
}

.spot-context {
    padding: 6px;
    border-radius: 12px;
    border: 1px solid alpha(@borders, 0.5);
}

.spot-context button {
    padding: 12px 10px;
    border-radius: 8px;
}

.search-field {
    border-radius: 12px;
    font-size: 1.2rem;
    padding: 10px 12px;
    border: 1px solid alpha(@window_fg_color, 0.10);
    background-color: alpha(@window_fg_color, 0.035);
    transition: border-color 100ms ease, background-color 100ms ease;
}

.search-field:focus-within {
    border-color: @accent_color;
    background-color: alpha(@accent_bg_color, 0.06);
}

.results-list {
    background: transparent;
    border-radius: 12px;
}

.results-list row {
    border-radius: 10px;
    padding: 4px;
    margin-bottom: 3px;
    transition: background-color 100ms ease;
}

.results-list row:hover {
    background-color: alpha(@window_fg_color, 0.06);
}

.results-list row:focus-visible {
    outline: 2px solid @accent_color;
    outline-offset: -2px;
}

.results-list row .title {
    font-weight: 500;
}

.results-list row .subtitle {
    opacity: 0.7;
}

.loading-status, .result-notice {
    color: alpha(@window_fg_color, 0.7);
}

.loading-status {
    padding: 6px 0;
}

.results-list row:selected {
    background-color: @accent_bg_color;
    color: @accent_fg_color;
}

.shortcut-badge {
    background-color: alpha(@window_fg_color, 0.08);
    color: alpha(@window_fg_color, 0.6);
    border-radius: 6px;
    padding: 3px 8px;
    font-size: 0.75rem;
    font-weight: 500;
}

.results-list row:selected .shortcut-badge {
    background-color: alpha(@accent_fg_color, 0.25);
    color: @accent_fg_color;
}
"""


class LauncherWindow(Gtk.Window):

    def __init__(self, app: Gtk.Application, indexer: AppIndexer):
        super().__init__(application=app)
        self.connect("realize", hide_from_dock)
        self.indexer = indexer
        self.history = HistoryManager()
        self.config = ConfigManager()
        apply_theme(self.config.get("theme"))
        self.matcher = SearchMatcher(self.history)
        self._remaining_rows = None
        self._result_count = 0
        self._viewport_tick = 0
        self._fade_tick = 0
        self._closing = False

        self.set_title(_("SpotLauncher"))
        self.set_default_size(580, -1)  # Altura dinâmica automática!
        self.set_resizable(False)
        self.set_decorated(False)
        self.add_css_class("spotlight-window")

        self._is_prefs_open = False
        self.preferences_window = None
        self._context_open = False
        self.calculator = CalculatorPlugin()
        self.tools = ToolsEngine()
        self._tools_worker = LatestRequestWorker(GLib.idle_add)
        self._file_worker = LatestRequestWorker(GLib.idle_add)
        self._update_worker = LatestRequestWorker(GLib.idle_add)
        self.available_update = None
        self.update_busy = False
        self._update_prompted = None
        self._last_update_check = 0
        self.files = FileSearchEngine()
        self._calc_result = None
        self._tool_copy_val = None

        # Bloqueia o fechamento destrutivo e detecta clique fora da janela
        self.connect("close-request", self._on_close_request)
        self.connect("notify::is-active", self._on_active_changed)

        self._apply_css()
        self.set_blur_compatibility()
        self._build_ui()
        self._setup_events()
        self.clipboard = Gdk.Display.get_default().get_clipboard()
        self._clipboard_generation = 0
        self._clipboard_handler = self.clipboard.connect("changed", self._on_clipboard_changed)
        self._on_clipboard_changed(self.clipboard)
        self._moving = False
        self._focus_ready = False
        self.connect("map", self._on_map)
        self.connect("hide", self._on_hide)
        self.check_updates()

    def _on_close_request(self, window):
        self.hide_launcher()
        return True

    def _apply_css(self):
        provider = Gtk.CssProvider()
        provider.load_from_data(LAUNCHER_CSS.encode("utf-8"))
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def set_blur_compatibility(self):
        if self.config.get("blur_my_shell", False):
            self.add_css_class("blur-my-shell")
        else:
            self.remove_css_class("blur-my-shell")

    def _build_ui(self):
        self.card_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=10,
            valign=Gtk.Align.START,  # Encolhe o cartão estritamente ao tamanho do conteúdo!
            css_classes=["spotlight-card"],
        )

        self.search_entry = Gtk.SearchEntry(
            placeholder_text=self.search_placeholder(),
            css_classes=["search-field"],
        )
        self._search_timeout_id = 0
        self.search_entry.connect("changed", self._on_search_changed)
        self.card_box.append(self.search_entry)

        self.search_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.card_box.append(self.search_content)

        self.loading_status = Gtk.Box(spacing=8, margin_start=12, visible=False,
                                      css_classes=["loading-status"])
        self.loading_spinner = Gtk.Spinner()
        self.loading_status.append(self.loading_spinner)
        self.loading_label = Gtk.Label()
        self.loading_status.append(self.loading_label)
        self.search_content.append(self.loading_status)

        self.calendar_panel = None

        # Janela com altura adaptável (encolhe se tiver poucos itens)
        self.scrolled_window = Gtk.ScrolledWindow(
            hscrollbar_policy=Gtk.PolicyType.NEVER,
            vscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
            propagate_natural_height=True,
            max_content_height=420,
        )
        self.scrolled_window.set_visible(False)  # Começa invisível!

        self.list_box = Gtk.ListBox(
            selection_mode=Gtk.SelectionMode.SINGLE,
            activate_on_single_click=True,  # Permite abrir com 1 clique do mouse!
            css_classes=["results-list"],
        )
        self.list_box.connect("row-activated", self._on_row_activated)
        self.list_box.connect("row-selected", self._scroll_to_selected)
        self.scrolled_window.set_child(self.list_box)
        self.scrolled_window.get_vadjustment().connect("value-changed", self._on_scroll)
        self.search_content.append(self.scrolled_window)

        self.card_box.set_size_request(580, -1)
        self.scaled_content = Gtk.Box()
        self.scaled_content.append(self.card_box)
        self.scaled_content.set_layout_manager(ScaledLayout())
        self.set_child(self.scaled_content)
        self.apply_scale()

    def search_placeholder(self):
        text = self.config.get("search_placeholder", "")
        return text if isinstance(text, str) and text else _("Pesquisar aplicativos, arquivos ou na web...")

    def apply_scale(self):
        scale = launcher_scale(self.config) / 100
        old_size = (self.get_width(), self.get_height())
        anchor = position(self) if self.get_mapped() else None
        layout = self.scaled_content.get_layout_manager()
        layout.scale = scale
        layout.after_allocate = None
        if self.get_mapped():
            # Move only after GTK allocates the new dimensions.
            layout.after_allocate = lambda: GLib.idle_add(self._center_scaled_window, anchor, old_size)
        layout.layout_changed()
        self.set_default_size(round(580 * scale), -1)

    def _center_scaled_window(self, anchor, old_size):
        if self.get_mapped():
            if anchor is not None:
                scale = self.get_surface().get_scale_factor()
                position(self, [round(anchor[0] + (old_size[0] - self.get_width()) * scale / 2),
                                round(anchor[1] + (old_size[1] - self.get_height()) * scale / 2)])
            else:
                gnome_placement(old_size)
        return False

    def _setup_events(self):
        self.context_menu = Gtk.ListBox(
            visible=False, selection_mode=Gtk.SelectionMode.SINGLE,
            activate_on_single_click=True, css_classes=["results-list"],
        )
        for index, (title, icon, callback) in enumerate((
            (_("Configurações do SpotLauncher"), "emblem-system-symbolic", self._context_settings),
            (_("Reiniciar SpotLauncher"), "view-refresh-symbolic", self._restart),
            (_("Fechar SpotLauncher"), "application-exit-symbolic", lambda *_: self.get_application().quit()),
        )):
            row = Adw.ActionRow(title=title, activatable=True)
            image = Gtk.Image.new_from_icon_name(icon)
            image.set_pixel_size(32)
            row.add_prefix(image)
            row.add_suffix(Gtk.Label(
                label=_("Enter") if index == 0 else f"Alt + {index}",
                valign=Gtk.Align.CENTER, css_classes=["shortcut-badge"],
            ))
            row._context_action = callback
            self.context_menu.append(row)
        self.context_menu.connect("row-activated", lambda box, row: row._context_action(None))
        self.card_box.insert_child_after(self.context_menu, self.search_entry)
        self.context_menu.connect("notify::visible", self._context_visibility_changed)
        secondary = Gtk.GestureClick(button=3)
        secondary.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        secondary.connect("pressed", self._show_context_menu)
        self.card_box.add_controller(secondary)

        self._drag_start = None
        click = Gtk.GestureClick(button=1)
        click.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        click.connect("pressed", self._on_pointer_pressed)
        self.add_controller(click)
        motion = Gtk.EventControllerMotion()
        motion.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        motion.connect("motion", self._pointer_motion)
        self.add_controller(motion)

        # CRUCIAL: Usamos a fase CAPTURE para a janela pegar as teclas antes da barra de busca!
        key_controller = Gtk.EventControllerKey()
        key_controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        key_controller.connect("key-pressed", self._on_key_pressed)
        self.add_controller(key_controller)

        # Garantia extra: se o SearchEntry acionar o evento stop-search do Esc
        self.search_entry.connect(
            "stop-search", lambda entry: self.hide_launcher()
        )

    def _show_context_menu(self, gesture, count, x, y):
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        self.context_menu.set_visible(not self.context_menu.get_visible())
        if self.context_menu.get_visible():
            self.context_menu.get_row_at_index(0).grab_focus()

    def _context_visibility_changed(self, menu, param):
        self._context_open = menu.get_visible()
        self.search_content.set_visible(not self._context_open)
        if not self._context_open:
            self.search_entry.grab_focus()
            GLib.idle_add(self._check_focus)

    def _restart(self, *args):
        app = self.get_application()
        app.restart_launcher = True
        app.quit()

    def check_updates(self):
        if self.update_busy:
            return
        self.update_busy = True
        self._last_update_check = time.monotonic()
        self._update_worker.submit(check_update, self._update_checked)

    def _update_checked(self, available):
        self.update_busy = False
        self.available_update = available
        self._refresh_update_settings()
        if available and self.config.get("auto_update", False):
            self.install_update()
        elif available and self.is_visible():
            self._show_update_prompt()

    def _refresh_update_settings(self):
        if self.preferences_window is not None:
            self.preferences_window.update_status(self.available_update, self.update_busy)

    def _show_update_prompt(self):
        version = self.available_update
        if (not version or self._update_prompted == version or self.config.get("hide_updates")
                or self.config.get("hide_update_version") == version or self._is_prefs_open):
            return
        self._update_prompted = version
        self._is_prefs_open = True
        dialog = Adw.MessageDialog.new(self, _("Atualização disponível"),
                                      _("Uma nova versão do SpotLauncher está disponível."))
        choices = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        until_next = Gtk.CheckButton(label=_("Não exibir novamente até a próxima atualização"))
        never = Gtk.CheckButton(label=_("Nunca mais exibir novamente"))
        choices.append(until_next)
        choices.append(never)
        dialog.set_extra_child(choices)
        dialog.add_response("close", _("Fechar"))
        dialog.add_response("update", _("Atualizar"))
        dialog.set_default_response("close")
        dialog.set_close_response("close")

        def respond(dialog, response):
            self._is_prefs_open = False
            if until_next.get_active():
                self.config.set("hide_update_version", version)
            if never.get_active():
                self.config.set("hide_updates", True)
            if response == "update":
                self.install_update()

        dialog.connect("response", respond)
        dialog.present()

    def install_update(self):
        if self.update_busy or not self.available_update:
            return
        self.update_busy = True
        self._refresh_update_settings()
        version = self.available_update
        self._update_worker.submit(lambda: install_update(version), self._update_installed)

    def _update_installed(self, success):
        self.update_busy = False
        self._refresh_update_settings()
        if success:
            self._restart()
            return
        self._is_prefs_open = True
        dialog = Adw.MessageDialog.new(self, _("Não foi possível atualizar"),
            _("Verifique a conexão e as alterações locais no repositório Git."))
        dialog.add_response("close", _("Fechar"))
        dialog.connect("response", lambda *_: setattr(self, "_is_prefs_open", False))
        dialog.present()

    def _context_settings(self, button):
        self.open_preferences()
        self.context_menu.set_visible(False)

    def _context_closed(self, popover):
        self._context_open = False
        GLib.idle_add(self._check_focus)

    def _check_focus(self):
        if (self.is_visible() and self._focus_ready
                and self.config.get("hide_on_focus_loss", True) and not self.is_active()
                and not self._is_prefs_open and not self._moving and not self._context_open
                and not any(window.is_visible() and window.get_transient_for() == self
                            for window in Gtk.Window.list_toplevels())):
            self.hide_launcher()
        return False

    def _on_pointer_pressed(self, gesture, count, x, y):
        self._drag_start = None
        widget = self.pick(x, y, Gtk.PickFlags.DEFAULT)
        while widget is not None:
            if isinstance(widget, Gtk.Scrollbar):
                return
            widget = widget.get_parent()
        if self.config.get("allow_move"):
            self._drag_start = (x, y)

    def _pointer_motion(self, controller, x, y):
        if not self._drag_start or self._moving:
            return
        if not controller.get_current_event_state() & Gdk.ModifierType.BUTTON1_MASK:
            self._drag_start = None
            return
        start_x, start_y = self._drag_start
        if self.drag_check_threshold(int(start_x), int(start_y), int(x), int(y)):
            self._drag_start = None
            device = controller.get_current_event_device()
            self._moving = True
            self._move_position = None
            self._last_motion = time.monotonic()
            self.get_surface().begin_move(device, 1, x, y, controller.get_current_event_time())
            GLib.timeout_add(120, self._finish_move, device)

    def _finish_move(self, device):
        if not self.get_mapped():
            self._moving = False
            return False
        current = position(self)
        if current != self._move_position:
            self._move_position = current
            self._last_motion = time.monotonic()
        # A compositor grab can hide the button release from GTK. Wait for
        # the last configure event before saving the settled coordinates.
        if time.monotonic() - self._last_motion < 0.3:
            return True
        if device.get_modifier_state() & Gdk.ModifierType.BUTTON1_MASK:
            return True
        self._moving = False
        self._save_position()
        GLib.idle_add(self._check_focus)
        return False

    def _save_position(self):
        if self.config.get("allow_move") and self.config.get("remember_position"):
            current = position(self)
            if current is not None and current != self.config.get("window_position"):
                self.config.set("window_position", current)

    def _on_hide(self, *args):
        self._save_position()

    def _on_map(self, *args):
        # Let the compositor finish its initial placement before moving.
        self.scaled_content.get_layout_manager().after_allocate = lambda: GLib.idle_add(self._restore_position, self, None)
        self.scaled_content.queue_allocate()

    def _restore_position(self, widget, clock):
        if self.get_mapped():
            saved = self.config.get("window_position") if (self.config.get("allow_move") and self.config.get("remember_position")) else None
            target = default_position(self, saved)
            if target is not None:
                position(self, target)
            else:
                gnome_placement()
        return False

    def _on_key_pressed(self, controller, keyval, keycode, state):
        if getattr(self, "_closing", False):
            return True
        if self._context_open:
            if state & Gdk.ModifierType.ALT_MASK:
                shortcut = chr(Gdk.keyval_to_unicode(Gdk.keyval_to_lower(keyval)))
                if shortcut in RESULT_SHORTCUTS:
                    row = self.context_menu.get_row_at_index(RESULT_SHORTCUTS.index(shortcut) + 1)
                    if row:
                        row._context_action(None)
                        return True
            if keyval == Gdk.KEY_Escape:
                self.context_menu.set_visible(False)
                return True
            return False
        if self.calendar_panel is not None and self.calendar_panel.get_visible() and keyval != Gdk.KEY_Escape:
            if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter) and self.search_entry.has_focus():
                self.calendar_panel.copy_date()
                return True
            return False
        # Atalhos rápidos: Alt + 1, Alt + 2, etc.
        if state & Gdk.ModifierType.ALT_MASK:
            shortcut = chr(Gdk.keyval_to_unicode(Gdk.keyval_to_lower(keyval)))
            if shortcut in RESULT_SHORTCUTS:
                target_index = RESULT_SHORTCUTS.index(shortcut) + 1
                while target_index >= self._result_count and self._remaining_rows is not None:
                    self._append_page()
                row = self.list_box.get_row_at_index(target_index)
                if row:
                    self._on_row_activated(self.list_box, row)
                    return True

        # Tecla ESC -> Oculta na mesma hora
        if keyval == Gdk.KEY_Escape:
            self.hide_launcher()
            return True

        # Seta para BAIXO -> Move seleção na lista
        elif keyval == Gdk.KEY_Down:
            selected_row = self.list_box.get_selected_row()
            if selected_row:
                next_index = selected_row.get_index() + 1
                if next_index >= self._result_count:
                    self._append_page()
                next_row = self.list_box.get_row_at_index(next_index)
                if next_row:
                    self.list_box.select_row(next_row)
            return True

        # Seta para CIMA -> Move seleção na lista
        elif keyval == Gdk.KEY_Up:
            selected_row = self.list_box.get_selected_row()
            if selected_row:
                prev_index = selected_row.get_index() - 1
                if prev_index >= 0:
                    prev_row = self.list_box.get_row_at_index(prev_index)
                    if prev_row:
                        self.list_box.select_row(prev_row)
            return True

        # Tecla ENTER -> Executa o item selecionado
        elif keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            selected_row = self.list_box.get_selected_row()
            if selected_row:
                self._on_row_activated(self.list_box, selected_row)
            return True

        return False

    def _cancel_pending_search(self):
        if self._search_timeout_id:
            GLib.source_remove(self._search_timeout_id)
            self._search_timeout_id = 0
        self._tools_worker.invalidate()
        self._file_worker.invalidate()
        self.loading_spinner.stop()
        self.loading_status.set_visible(False)

    def _on_search_changed(self, entry):
        self._cancel_pending_search()
        self._do_search(entry.get_text())

    def _schedule_search(self, worker, task, deliver, label, delay):
        self.loading_label.set_label(label)
        self.loading_status.set_visible(True)
        self.loading_spinner.start()

        def complete(result):
            self.loading_spinner.stop()
            self.loading_status.set_visible(False)
            deliver(result)

        def submit():
            self._search_timeout_id = 0
            worker.submit(task, complete)
            return False

        self._search_timeout_id = GLib.timeout_add(delay, submit)

    def close_services(self):
        self._cancel_fade()
        self._save_position()
        self.clipboard.disconnect(self._clipboard_handler)
        self._cancel_pending_search()
        self._tools_worker.close()
        self._file_worker.close()
        self._update_worker.close()
        self.files.close()

    def _clear_results(self):
        self._remaining_rows = None
        self._result_count = 0
        self.scrolled_window.get_vadjustment().set_value(0)
        while child := self.list_box.get_first_child():
            self.list_box.remove(child)

    def _do_search(self, query: str):
        self._clear_results()
        query = command_query(query) or query
        query_clean = query.strip().lower()
        command = normalize_text(query)
        show_calendar = command in (
            "calendario", "calendar", "calendrier", "agenda",
        )
        if show_calendar and self.calendar_panel is None:
            self.calendar_panel = CalendarView()
            self.search_content.insert_child_after(self.calendar_panel, self.loading_status)
        if self.calendar_panel is not None:
            if show_calendar and not self.calendar_panel.get_visible():
                self.calendar_panel.select_today()
            self.calendar_panel.set_visible(show_calendar)

        self._tool_copy_val = None
        self._calc_result = None
        if show_calendar:
            self.scrolled_window.set_visible(False)
            return
        # SE A BUSCA ESTIVER VAZIA: Esconde a lista
        if not query_clean:
            self.scrolled_window.set_visible(False)
            return

        if query.lstrip().startswith(">"):
            command_text = query.lstrip()[1:].strip()
            if command_text:
                row = Adw.ActionRow(title=GLib.markup_escape_text(command_text),
                                    subtitle=_("Executar no terminal"), activatable=True)
                row.add_prefix(Gtk.Image.new_from_icon_name("utilities-terminal-symbolic"))
                row._terminal_command = command_text
                self._append_result(row)
                self.scrolled_window.set_visible(True)
                self.list_box.select_row(row)
            else:
                self.scrolled_window.set_visible(False)
            return

        translation = translation_search(query)
        if translation:
            if len(translation[0].encode('utf-8')) > 500:
                self._show_notice(_("Tradução limitada a 500 bytes de texto"))
                return
            self._schedule_search(self._tools_worker,
                                  lambda: translate(*translation),
                                  lambda text: self._show_translation(translation, text),
                                  _("Carregando resultado…"), 400)
            return

        dictionary = dictionary_search(query)
        if dictionary:
            self._schedule_search(self._tools_worker,
                                  lambda: dictionary_lookup(*dictionary),
                                  lambda items: self._show_dictionary(dictionary, items),
                                  _("Carregando resultado…"), 400)
            return

        destination = map_destination(query)
        if destination:
            for row in self._map_rows(destination):
                self._append_result(row)
            self.scrolled_window.set_visible(True)
            self.list_box.select_row(self.list_box.get_row_at_index(0))
            return

        if command in ("emoji", "emojis"):
            row = Adw.ActionRow(title=_("Selecionar emoji"), activatable=True)
            row._emoji = True
            self._append_result(row)
            self.scrolled_window.set_visible(True)
            self.list_box.select_row(row)
            return

        web_result = web_search(query)
        if web_result and web_result.explicit:
            self._append_result(self._web_row(web_result))
            self.scrolled_window.set_visible(True)
            self.list_box.select_row(self.list_box.get_row_at_index(0))
            return

        # Histórico da Área de Transferência
        if command in ("clip", "clipboard", "clipboard history", "copiado", "historico",
                       "area de transferencia", "portapapeles", "historial", "presse-papiers", "historique",
                       "historial del portapapeles", "historique du presse-papiers",
                       "historico da area de transferencia"):
            self.scrolled_window.set_visible(False)
            self._schedule_search(self._file_worker, self.tools.get_clipboard_history,
                                  self._show_clipboard, _("Carregando resultado…"), 80)
            return

        if self.tools.supports_query(query):
            def show_tool(result):
                if result:
                    self._show_tool_result(result)
                else:
                    self._search_local(query, web_result)
            self.scrolled_window.set_visible(False)
            self._schedule_search(self._tools_worker, lambda: self.tools.search(query),
                                  show_tool, _("Carregando resultado…"), 180)
            return

        self._calc_result = self.calculator.evaluate(query_clean)

        # Se for conta matemática
        if self._calc_result is not None:
            self.scrolled_window.set_visible(True)
            self._tool_copy_val = self._calc_result
            calc_row = Adw.ActionRow(
                title=f"= {self._calc_result}",
                subtitle=_("Pressione Enter para copiar o resultado"),
                activatable=True,
            )
            calc_icon = Gtk.Image.new_from_icon_name("accessories-calculator-symbolic")
            calc_icon.set_pixel_size(32)
            calc_row.add_prefix(calc_icon)
            self._append_result(calc_row)
            self.list_box.select_row(calc_row)
            return

        self._search_local(query, web_result)

    def _show_clipboard(self, clip_items):
        if clip_items:
            self.scrolled_window.set_visible(True)
            for item in clip_items:
                row = Adw.ActionRow(
                    title=GLib.markup_escape_text(item.strip().replace("\n", " ")[:60]),
                    subtitle=_("Pressione Enter para copiar"),
                    activatable=True,
                )
                icon = Gtk.Image.new_from_icon_name("edit-copy-symbolic")
                icon.set_pixel_size(32)
                row.add_prefix(icon)
                row._clipboard_text = item
                self._append_result(row)
            first = self.list_box.get_row_at_index(0)
            if first:
                self.list_box.select_row(first)
            return

        self._show_notice(_("O histórico da área de transferência está vazio"))

    def _show_translation(self, translation, text):
        if not text:
            self._show_notice(_("Tradução indisponível"))
            return
        row = Adw.ActionRow(title=GLib.markup_escape_text(text),
                            subtitle="MyMemory · " + translation[1] + " → " + translation[2],
                            activatable=True, title_lines=0)
        row._clipboard_text = text
        self._append_result(row)
        self.scrolled_window.set_visible(True)
        self.list_box.select_row(row)

    def _show_dictionary(self, dictionary, items):
        if not items:
            self._show_notice(_("Definição indisponível"))
        source = "Wiktionary · " + urlsplit(dictionary[1]).netloc.split('.')[0]
        for text in items or []:
            row = Adw.ActionRow(title=GLib.markup_escape_text(text), subtitle=source,
                                activatable=True, title_lines=0)
            row._clipboard_text = text
            self._append_result(row)
        row = Adw.ActionRow(title=GLib.markup_escape_text(dictionary[0]), subtitle="Wiktionary ↗", activatable=True)
        row._web_url = dictionary[1]
        self._append_result(row)
        self.scrolled_window.set_visible(True)
        self.list_box.select_row(self.list_box.get_row_at_index(0))

    def _show_tool_result(self, result):
        self._tool_copy_val = result["copy"]
        row = Adw.ActionRow(
            title=GLib.markup_escape_text(result["title"]),
            subtitle=GLib.markup_escape_text(result["sub"]),
            activatable=result["copy"] is not None,
        )
        icon = Gtk.Image.new_from_icon_name(result["icon"])
        icon.set_pixel_size(32)
        row.add_prefix(icon)
        self._append_result(row)
        self.scrolled_window.set_visible(True)
        self.list_box.select_row(row)

    def _show_notice(self, message):
        self._append_result(Adw.ActionRow(title=message, activatable=False,
                                         css_classes=["result-notice"]))
        self.scrolled_window.set_visible(True)

    def _search_local(self, query, web_result):
        command = normalize_text(query)
        kind, text = file_query(query)
        actions = [] if kind else system_actions(query)
        suggestion = command_suggestion(query)
        if suggestion:
            actions.append(suggestion)
        launcher_action = next((action for action in ("reiniciar", "reset", "restart", "reboot", "redemarrer", "fechar", "close", "encerrar", "sair", "quit", "cerrar", "fermer", "quitter")
                                if action in command.split() and any(term in command.split() for term in ("spot", "spotlauncher", "launcher"))), None)
        if not kind and launcher_action:
            actions.insert(0, (launcher_action, lambda: self._restart() if launcher_action in ("reiniciar", "reset", "restart", "reboot", "redemarrer") else self.get_application().quit()))
        show_settings = 0 if kind else max(search_score(query, alias) for alias in (
            "Configurações do SpotLauncher", "SpotLauncher settings", "ajustes de SpotLauncher",
            "parametres de SpotLauncher", "config", "settings", "preferences", "preferencias",
            "ajustes", "configuracao", "configuracoes", "configuracion", "parametres", "reglages"))
        limit = None if self.config.get("scroll_results", True) else self.config.get("max_results", 7)
        apps = [] if kind else self.matcher.search(query, self.indexer.get_apps(), limit=limit)

        if not kind and len(text) < 2:
            self._render_matches(apps, [], show_settings, web_result, actions=actions, query=query)
            return

        # Keep apps actionable while files are being indexed. Wait for local
        # results before offering the web fallback to the Enter shortcut.
        self._render_matches(apps, [], show_settings, None, actions=actions, query=query)

        def show_files(files):
            if files is None:
                message = _("Não foi possível pesquisar os arquivos")
            elif kind and not files:
                message = _("Nenhum arquivo encontrado")
            else:
                message = None
            self._render_matches(apps, files or [], show_settings, web_result, message, actions, query=query)

        self._schedule_search(self._file_worker, lambda: self.files.search_current(query, limit),
                              show_files, {
                                  "image": _("Pesquisando fotos…"),
                                  "document": _("Pesquisando documentos…"),
                                  "audio": _("Pesquisando áudios…"),
                                  "video": _("Pesquisando vídeos…"),
                              }.get(kind, _("Pesquisando arquivos…")), 80)

    def _render_matches(self, apps, files, show_settings, web_result, message=None, actions=(), query=""):
        self._clear_results()
        if message:
            self._show_notice(message)

        def rows():
            ranked = []
            if show_settings:
                def settings_row():
                    row = Adw.ActionRow(title=_("Configurações do SpotLauncher"),
                                        subtitle=_("Personalizar comportamento e preferências"), activatable=True)
                    row.add_prefix(Gtk.Image.new_from_icon_name("preferences-system-symbolic"))
                    row._settings = True
                    return row
                ranked.append(((-float(show_settings), 1, "settings", "settings"), settings_row))
            for action in actions:
                if isinstance(action, CommandSuggestion):
                    def suggestion_row(action=action):
                        row = Adw.ActionRow(title=GLib.markup_escape_text(action.query), activatable=True)
                        row._search_query = action.query
                        return row
                    ranked.append(((-action.score, 1, action.query, action.query), suggestion_row))
                    continue
                if isinstance(action, tuple):
                    name, callback = action
                    def launcher_row(name=name, callback=callback):
                        row = Adw.ActionRow(title=_("Reiniciar SpotLauncher") if name in ("reiniciar", "reset", "restart", "reboot", "redemarrer") else _("Fechar SpotLauncher"), activatable=True)
                        row._launcher_action = callback
                        return row
                    score = max(search_score(query, name + " " + target)
                                for target in ("spot", "spotlauncher", "launcher"))
                    ranked.append(((-score, 1, name, name), launcher_row))
                    continue
                def action_row(action=action):
                    row = Adw.ActionRow(title=action.title, subtitle=action.subtitle, activatable=True)
                    row.add_prefix(Gtk.Image.new_from_icon_name(action.icon))
                    row._system_action = action
                    return row
                ranked.append(((-action.score, 1, action.title, str(action.command)), action_row))
            local_rows = ((result_key(item), lambda item=item: self._match_row(item))
                          for item in merge(apps, files, key=result_key))
            for rank, make_row in merge(local_rows, sorted(ranked, key=lambda item: item[0]),
                                        key=lambda item: item[0]):
                yield make_row()
            if web_result:
                yield self._web_row(web_result)
                # shortcut: offer maps for any text; add place recognition if suggestions become distracting.
                yield from self._map_rows(web_result.query)

        self._remaining_rows = rows()
        self._append_page()
        self.scrolled_window.set_visible(self._result_count > 0)
        self.list_box.select_row(self.list_box.get_row_at_index(0))

    def _match_row(self, item):
        if hasattr(item, "entry"):
            app = item.entry
            row = Adw.ActionRow(title=GLib.markup_escape_text(app.name),
                                subtitle=GLib.markup_escape_text(app.description or app.id),
                                activatable=True)
            row._app_entry = app
            icon_name = app.icon_name
        else:
            label = {
                "folder": _("Pasta"), "file": _("Arquivo"), "image": _("Foto"),
                "video": _("Vídeo"), "audio": _("Áudio"), "document": _("Documento"),
            }[item.kind]
            path = GLib.markup_escape_text(item.path.replace(os.path.expanduser("~"), "~", 1))
            row = Adw.ActionRow(title=GLib.markup_escape_text(item.name),
                                subtitle=f"[{label}] {path}", activatable=True)
            row._file_entry = item
            icon_name = item.icon_name
        icon = Gtk.Image.new_from_icon_name(icon_name)
        icon.set_pixel_size(32)
        row.add_prefix(icon)
        return row

    def _append_page(self):
        if self._remaining_rows is None:
            return
        scrolling = self.config.get("scroll_results", True)
        limit = self.config.get("max_results", 7)
        size = limit + 1 if scrolling else max(0, limit - self._result_count)
        previous = self._result_count
        for row in islice(self._remaining_rows, size):
            self._append_result(row)
        if not scrolling or self._result_count - previous < size:
            self._remaining_rows = None

    def _on_scroll(self, adjustment):
        if adjustment.get_value() > 0 and (
            adjustment.get_value() + adjustment.get_page_size() >= adjustment.get_upper() - 1
        ):
            self._append_page()

    def _scroll_to_selected(self, list_box, row):
        if row is not None and row.get_height():
            ok, bounds = row.compute_bounds(list_box)
            if ok:
                self.scrolled_window.get_vadjustment().clamp_page(
                    bounds.get_y(), bounds.get_y() + bounds.get_height(),
                )

    def _append_result(self, row):
        limit = self.config.get("max_results", 7)
        if not self.config.get("scroll_results", True) and self._result_count >= limit:
            return
        self.list_box.append(row)
        self._result_count += 1
        index = row.get_index()
        if row.get_activatable() and 0 <= index <= len(RESULT_SHORTCUTS):
            badge = Gtk.Label(
                label=_("Enter") if index == 0 else f"Alt + {RESULT_SHORTCUTS[index - 1].upper()}",
                valign=Gtk.Align.CENTER,
                css_classes=["shortcut-badge"],
            )
            row.add_suffix(badge)
        if self._result_count <= limit and not self._viewport_tick:
            self._viewport_tick = self.list_box.add_tick_callback(self._update_result_viewport)

    def _update_result_viewport(self, *args):
        self._viewport_tick = 0
        limit = self.config.get("max_results", 7)
        width = max(self.list_box.get_width(), 500)
        height = 0
        for index in range(limit):
            row = self.list_box.get_row_at_index(index)
            if row is None:
                break
            height += row.measure(Gtk.Orientation.VERTICAL, width)[1]
        if height:
            self.scrolled_window.set_max_content_height(height)
        return False

    def _map_rows(self, destination):
        maps = Gio.DesktopAppInfo.new("org.gnome.Maps.desktop")
        if maps:
            row = Adw.ActionRow(title=_("Abrir no GNOME Mapas"),
                                subtitle=GLib.markup_escape_text(destination), activatable=True)
            row.add_prefix(Gtk.Image.new_from_icon_name("org.gnome.Maps"))
            row._maps_app = maps
            row._maps_uri = "geo:0,0?q=" + quote(destination, safe="")
            yield row
        row = Adw.ActionRow(title=_("Abrir mapa no navegador"),
                            subtitle=GLib.markup_escape_text(destination), activatable=True)
        row.add_prefix(Gtk.Image.new_from_icon_name("mark-location-symbolic"))
        row._web_url = map_search("mapa " + destination)
        yield row

    def _web_row(self, result):
        row = Adw.ActionRow(
            title=_("Pesquisar no Google: %s") % GLib.markup_escape_text(result.query),
            subtitle=_("Abrir pesquisa no navegador padrão"),
            activatable=True,
        )
        icon = Gtk.Image.new_from_icon_name("web-browser-symbolic")
        icon.set_pixel_size(32)
        row.add_prefix(icon)
        row._web_url = result.url
        return row

    def _on_active_changed(self, window, param):
        """Only hide after the compositor has actually given this opening focus."""
        if self.is_active():
            self._focus_ready = True
        GLib.idle_add(self._check_focus)

    def _on_row_activated(self, list_box, row):
        if getattr(self, "_closing", False) is True or not row.get_activatable():
            return
        if hasattr(row, "_terminal_command"):
            try:
                terminal = get_default_terminal()
                if not terminal:
                    raise RuntimeError(_("Nenhum terminal encontrado"))
                subprocess.Popen(terminal + [os.environ.get("SHELL") or "/bin/sh", "-c", row._terminal_command],
                                 start_new_session=True)
                self.hide_launcher()
            except (OSError, RuntimeError) as exc:
                self._is_prefs_open = True
                dialog = Adw.MessageDialog.new(self, _("Não foi possível abrir o terminal"), str(exc))
                dialog.add_response("close", _("Fechar"))
                dialog.connect("response", lambda *_: setattr(self, "_is_prefs_open", False))
                dialog.present()
            return
        if getattr(row, "_emoji", False):
            chooser = Gtk.EmojiChooser()
            chooser.set_parent(self.search_entry)
            self._context_open = True
            chooser.connect("emoji-picked", self._on_emoji_picked)
            chooser.connect("closed", self._on_emoji_closed)
            chooser.popup()
            return
        if hasattr(row, "_system_action"):
            self._activate_system_action(row._system_action)
            return
        if hasattr(row, "_search_query"):
            self.search_entry.set_text(row._search_query)
            return
        if hasattr(row, "_launcher_action"):
            row._launcher_action()
            return
        if hasattr(row, "_maps_app"):
            try:
                if row._maps_app.launch_uris([row._maps_uri], None):
                    self.hide_launcher()
            except GLib.Error as exc:
                dialog = Adw.MessageDialog.new(self, _("Não foi possível abrir o mapa"), str(exc))
                dialog.add_response("close", _("Fechar"))
                dialog.present()
            return
        if hasattr(row, "_web_url"):
            try:
                if Gio.AppInfo.launch_default_for_uri(row._web_url, None):
                    self.hide_launcher()
            except GLib.Error as exc:
                dialog = Adw.MessageDialog.new(
                    self, _("Não foi possível abrir o navegador"), str(exc)
                )
                dialog.add_response("close", _("Fechar"))
                dialog.present()
            return
        # Copia qualquer resultado de ferramenta (moeda, unidade, fuso ou calculadora)
        if self._tool_copy_val is not None:
            clipboard = Gdk.Display.get_default().get_clipboard()
            clipboard.set(self._tool_copy_val)
            print(f"[Ferramentas] Copiado para a área de transferência: {self._tool_copy_val}")
            self.hide_launcher()
            return

        if hasattr(row, "_clipboard_text"):
            clipboard = Gdk.Display.get_default().get_clipboard()
            clipboard.set(row._clipboard_text)
            self.hide_launcher()
            return

        if getattr(row, "_settings", False):
            self.open_preferences()
            return

        # Se for um arquivo ou pasta
        if hasattr(row, "_file_entry"):
            print(f"[Launcher] Abrindo: {row._file_entry.path}")
            self.files.open_item(row._file_entry)
            self.hide_launcher()
            return

        # Se for um aplicativo
        if hasattr(row, "_app_entry"):
            app = row._app_entry
            print(f"[Launcher] Executando: {app.name}")
            if self.indexer.launch(app):
                self.history.record_launch(app.id, self.search_entry.get_text())
            self.hide_launcher()
            return

    def _on_emoji_picked(self, chooser, emoji):
        self.clipboard.set(emoji)
        self.hide_launcher()

    def _on_emoji_closed(self, chooser):
        chooser.unparent()
        self._context_closed(chooser)

    def _activate_system_action(self, action):
        def complete(error):
            if error:
                self._is_prefs_open = True
                dialog = Adw.MessageDialog.new(self, _("Não foi possível executar a ação"), error)
                dialog.add_response("close", _("Fechar"))
                dialog.connect("response", lambda *_: setattr(self, "_is_prefs_open", False))
                dialog.present()
            else:
                self.hide_launcher()

        if not action.confirm:
            execute_action(action, complete)
            return
        self._is_prefs_open = True
        dialog = Adw.MessageDialog.new(self, action.title + "?",
                                      _("Salve seu trabalho antes de continuar. Aplicativos abertos podem ser fechados."))
        dialog.add_response("cancel", _("Cancelar"))
        dialog.add_response("execute", action.title)
        dialog.set_response_appearance("execute", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")

        def respond(dialog, response):
            self._is_prefs_open = False
            if response == "execute":
                execute_action(action, complete)

        dialog.connect("response", respond)
        dialog.present()

    def open_preferences(self):
        if self.preferences_window is None:
            self.preferences_window = PreferencesWindow(self, self.config)
            self.preferences_window.connect("close-request", self._preferences_closed)
        self._is_prefs_open = True
        self.preferences_window.present()

    def _preferences_closed(self, *args):
        self.preferences_window = None
        self._is_prefs_open = False

    def _cancel_fade(self):
        if self._fade_tick:
            self.scaled_content.remove_tick_callback(self._fade_tick)
            self._fade_tick = 0

    def _finish_fade(self, opacity):
        self.scaled_content.set_opacity(opacity)
        if opacity == 0:
            self.set_visible(False)
            self._clear_results()

    def _fade_to(self, opacity):
        self._cancel_fade()
        initial = self.scaled_content.get_opacity()
        if not self.get_settings().get_property("gtk-enable-animations") or initial == opacity:
            self._finish_fade(opacity)
            return
        duration = 120_000 if opacity else 90_000
        clock = self.get_frame_clock()
        started = clock.get_frame_time() if clock else None

        def tick(widget, clock):
            nonlocal started
            now = clock.get_frame_time()
            if started is None:
                started = now
            progress = min(1.0, (now - started) / duration)
            if not self.get_settings().get_property("gtk-enable-animations"):
                progress = 1.0
            eased = 1 - (1 - progress) ** 3
            widget.set_opacity(initial + (opacity - initial) * eased)
            if progress >= 1:
                self._fade_tick = 0
                self._finish_fade(opacity)
                return False
            return True

        self._fade_tick = self.scaled_content.add_tick_callback(tick)

    def show_launcher(self):
        self._closing = False
        self.scaled_content.set_sensitive(True)
        if not self.is_visible():
            self.scaled_content.set_opacity(0)
        if self.preferences_window is not None:
            self.preferences_window.close()
        if self.config.get("clear_on_hide", True):
            self.search_entry.set_text("")
        self._on_search_changed(self.search_entry)
        self._focus_ready = self.is_active()
        self.set_visible(True)
        self.present()
        self.search_entry.grab_focus()
        self._fade_to(1)
        self._on_clipboard_changed(self.clipboard)
        self._show_update_prompt()
        if time.monotonic() - self._last_update_check >= 300:
            self.check_updates()

    def _on_clipboard_changed(self, clipboard):
        self._clipboard_generation += 1
        generation = self._clipboard_generation
        clipboard.read_text_async(None, self._on_clipboard_read, generation)

    def _on_clipboard_read(self, clipboard, result, generation):
        try:
            text = clipboard.read_text_finish(result)
            if text and generation == self._clipboard_generation:
                self.tools.record_clipboard(text)
        except Exception:
            pass

    def hide_launcher(self):
        if getattr(self, "_closing", False):
            return
        self._closing = True
        self.scaled_content.set_sensitive(False)
        if hasattr(self, "context_menu"):
            self.context_menu.set_visible(False)
        self._cancel_pending_search()
        self._fade_to(0)

    def toggle_launcher(self):
        if self.is_visible() and not getattr(self, "_closing", False) and self.preferences_window is None:
            self.hide_launcher()
        else:
            self.show_launcher()
