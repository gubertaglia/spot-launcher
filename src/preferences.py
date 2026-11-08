from src.storage import write_json
import json
import os
import subprocess
import sys
from pathlib import Path
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("GLib", "2.0")
gi.require_version("Gdk", "4.0")

from gi.repository import Adw, Gdk, GLib, Gtk
from src import VERSION, _
from src.placement import hide_from_dock
from src.gnome import enable_integration, shortcut_settings, set_shortcut
from src.worker import LatestRequestWorker

CONFIG_DIR = os.path.join(GLib.get_user_config_dir(), "spot-launcher")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
AUTOSTART_DIR = os.path.join(GLib.get_user_config_dir(), "autostart")
AUTOSTART_FILE = os.path.join(AUTOSTART_DIR, "spot-launcher.desktop")

def autostart_entry():
    # Desktop Exec tem regras próprias; não executa um shell nem depende do cwd.
    def quote(argument):
        escaped = "".join("\\" + char if char in '\\"`$' else char for char in argument)
        return '"' + escaped.replace("%", "%%") + '"'

    command = " ".join(quote(argument) for argument in (
        sys.executable, str(Path(__file__).resolve().parents[1] / "run.py"), "--daemon"
    ))
    entry = GLib.KeyFile()
    for key, value in {
        "Type": "Application", "Name": "Spot Launcher",
        "Comment": _("Iniciador de aplicativos rápido e nativo"), "Exec": command,
        "Icon": "system-search", "Terminal": "false", "Categories": "Utility;",
        "X-GNOME-Autostart-enabled": "true",
    }.items():
        entry.set_string("Desktop Entry", key, value)
    return entry.to_data()[0]


THEMES = {
    "system": Adw.ColorScheme.DEFAULT,
    "light": Adw.ColorScheme.FORCE_LIGHT,
    "dark": Adw.ColorScheme.FORCE_DARK,
}


def apply_theme(theme):
    Adw.StyleManager.get_default().set_color_scheme(THEMES.get(theme, Adw.ColorScheme.DEFAULT))


DEFAULT_CONFIG = {
    "theme": "system",
    "allow_move": False,
    "remember_position": False,
    "language": "system",
    "max_results": 7,
    "scroll_results": True,
    "clear_on_hide": True,
    "super_launcher": False,
    "disable_overview": False,
}


class ConfigManager:

    def __init__(self):
        self.config = DEFAULT_CONFIG.copy()
        self._load()

    def _load(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    self.config.update(json.load(f))
            except Exception as e:
                print(f"[Config] Erro ao carregar: {e}")

    def save(self):
        try:
            write_json(CONFIG_FILE, self.config)
            return True
        except Exception as e:
            print(f"[Config] Erro ao salvar: {e}")

    def get(self, key, default=None):
        return self.config.get(key, default)

    def set(self, key, value):
        self.config[key] = value
        return self.save()


class PreferencesWindow(Adw.PreferencesWindow):

    def __init__(self, parent_window, config_manager: ConfigManager):
        super().__init__(transient_for=parent_window, modal=True)
        self.connect("realize", hide_from_dock)
        self.config = config_manager
        self._gnome_worker = LatestRequestWorker(GLib.idle_add)
        self.connect("close-request", lambda *_: self._gnome_worker.close())
        self.set_title(_("Configurações do Spot"))
        self.set_default_size(500, 540)

        page = Adw.PreferencesPage()
        self.add(page)

        # Grupo: Comportamento
        group_general = Adw.PreferencesGroup(title=_("Comportamento"))
        page.add(group_general)

        self.language_codes = ("system", "pt", "en", "es", "fr")
        selected_language = self.config.get("language", "system")
        if selected_language not in self.language_codes:
            selected_language = "system"
        self.row_language = Adw.ComboRow(
            title=_("Idioma"),
            model=Gtk.StringList.new([
                _("Idioma do sistema"), "Português (Brasil)", "English",
                "Español", "Français",
            ]),
            selected=self.language_codes.index(selected_language),
        )
        self.row_language.connect("notify::selected", self._on_language_changed)
        group_general.add(self.row_language)

        theme = self.config.get("theme")
        self.row_theme = Adw.ComboRow(
            title=_("Tema"),
            model=Gtk.StringList.new([_("Tema do sistema"), _("Claro"), _("Escuro")]),
            selected=list(THEMES).index(theme) if theme in THEMES else 0,
        )
        self.row_theme.connect("notify::selected", self._on_theme_changed)
        group_general.add(self.row_theme)

        self.row_move = Adw.SwitchRow(
            title=_("Permitir mover a janela"),
            subtitle=_("Arraste o Spot para reposicioná-lo"),
            active=self.config.get("allow_move", False),
        )
        self.row_move.connect("notify::active", self._on_move_changed)
        group_general.add(self.row_move)

        can_restore = hasattr(parent_window.get_surface(), "get_xid")
        self.row_remember = Adw.SwitchRow(
            title=_("Lembrar a posição"),
            subtitle=None if can_restore else _("Restaurar a posição requer X11 ou XWayland"),
            sensitive=can_restore,
            visible=self.row_move.get_active(),
            active=self.config.get("remember_position", False),
        )
        self.row_remember.connect("notify::active", self._on_remember_changed)
        group_general.add(self.row_remember)

        # 1. Quantidade de Resultados
        adj = Gtk.Adjustment(
            value=self.config.get("max_results", 7),
            lower=3,
            upper=15,
            step_increment=1,
            page_increment=1,
        )
        self.row_results = Adw.SpinRow(
            title=_("Máximo de Resultados"),
            subtitle=_("Quantidade de itens exibidos simultaneamente"),
            adjustment=adj,
        )
        self.row_results.connect(
            "notify::value", self._on_results_changed
        )
        group_general.add(self.row_results)

        self.row_scroll = Adw.SwitchRow(
            title=_("Permitir rolagem nos resultados"),
            subtitle=_("Role para ver os resultados além do limite visível"),
            active=self.config.get("scroll_results", True),
        )
        self.row_scroll.connect("notify::active", self._on_scroll_changed)
        group_general.add(self.row_scroll)

        # 2. Limpar busca ao fechar
        self.row_clear = Adw.SwitchRow(
            title=_("Limpar busca ao fechar"),
            subtitle=_(
                "Apaga o que foi digitado sempre que a janela for ocultada"
            ),
            active=self.config.get("clear_on_hide", True),
        )
        self.row_clear.connect("notify::active", self._on_clear_changed)
        group_general.add(self.row_clear)

        # 3. Iniciar com o Sistema (Autostart)
        is_autostart = os.path.exists(AUTOSTART_FILE)
        self.row_autostart = Adw.SwitchRow(
            title=_("Iniciar com o sistema"),
            subtitle=_("Abre o Spot Launcher em segundo plano ao ligar o computador"),
            active=is_autostart,
        )
        self.row_autostart.connect("notify::active", self._on_autostart_changed)
        group_general.add(self.row_autostart)

        settings, shortcut = shortcut_settings()
        if settings and "GNOME" in os.environ.get("XDG_CURRENT_DESKTOP", "").upper():
            binding = shortcut.get_string("binding") if shortcut else ""
            self.row_shortcut = Adw.ActionRow(title=_("Atalho para abrir o Spot"),
                subtitle=Gtk.accelerator_get_label(*Gtk.accelerator_parse(binding)[1:]) if binding else _("Nenhum"))
            button = Gtk.Button(label=_("Alterar"), valign=Gtk.Align.CENTER)
            button.connect("clicked", self._choose_shortcut)
            self.row_shortcut.add_suffix(button)
            group_general.add(self.row_shortcut)

        self.row_super = Adw.SwitchRow(
            title=_("Abrir o Spot com Super"),
            subtitle=_("Usa a tecla Super sozinha no GNOME Shell"),
            active=self.config.get("super_launcher", False),
        )
        self.row_super.connect("notify::active", self._on_gnome_changed, "super_launcher")
        group_general.add(self.row_super)

        self.row_overview = Adw.SwitchRow(
            title=_("Desabilitar o panorama"),
            subtitle=_("Desativa o panorama do GNOME Shell"),
            active=self.config.get("disable_overview", False),
        )
        self.row_overview.connect("notify::active", self._on_gnome_changed, "disable_overview")
        group_general.add(self.row_overview)

        # Grupo: Sobre
        group_about = Adw.PreferencesGroup(title=_("Sobre"))
        page.add(group_about)

        row_about = Adw.ActionRow(
            title=_("Spot Launcher"),
            subtitle=_("Versão {version} · Launcher de aplicativos, arquivos e ferramentas para Linux").format(version=VERSION),
        )
        group_about.add(row_about)
        self._set_header_drag(self, self.row_move.get_active())

    def _set_header_drag(self, widget, enabled):
        if isinstance(widget, Gtk.WindowHandle):
            for controller in widget.observe_controllers():
                if isinstance(controller, (Gtk.GestureClick, Gtk.GestureDrag)):
                    controller.set_propagation_phase(
                        Gtk.PropagationPhase.BUBBLE if enabled else Gtk.PropagationPhase.NONE
                    )
        child = widget.get_first_child()
        while child:
            self._set_header_drag(child, enabled)
            child = child.get_next_sibling()

    def _on_language_changed(self, row, param):
        selected = row.get_selected()
        if selected < len(self.language_codes):
            if self.config.set("language", self.language_codes[selected]):
                app = self.get_transient_for().get_application()
                app.reopen_preferences = True
                app.quit()

    def _on_theme_changed(self, row, param):
        theme = list(THEMES)[row.get_selected()]
        self.config.set("theme", theme)
        apply_theme(theme)

    def _on_move_changed(self, row, param):
        enabled = row.get_active()
        self.config.set("allow_move", enabled)
        self.row_remember.set_visible(enabled)
        self._set_header_drag(self, enabled)

    def _on_remember_changed(self, row, param):
        self.config.set("remember_position", row.get_active())
        if row.get_active():
            self.get_transient_for()._save_position()

    def _on_results_changed(self, row, param):
        self.config.set("max_results", int(row.get_value()))
        parent = self.get_transient_for()
        parent._on_search_changed(parent.search_entry)

    def _on_scroll_changed(self, row, param):
        self.config.set("scroll_results", row.get_active())
        parent = self.get_transient_for()
        parent._on_search_changed(parent.search_entry)

    def _on_clear_changed(self, row, param):
        self.config.set("clear_on_hide", row.get_active())

    def _choose_shortcut(self, button):
        dialog = Adw.MessageDialog.new(self, _("Pressione o atalho desejado"),
                                       _("Escape cancela; Backspace remove o atalho."))
        dialog.add_response("cancel", _("Cancelar"))
        controller = Gtk.EventControllerKey()
        def pressed(controller, keyval, keycode, state):
            if keyval == Gdk.KEY_Escape:
                dialog.close()
                return True
            if keyval == Gdk.KEY_BackSpace:
                binding = ""
            else:
                modifiers = state & Gtk.accelerator_get_default_mod_mask()
                if not Gtk.accelerator_valid(keyval, modifiers):
                    return True
                binding = Gtk.accelerator_name(keyval, modifiers)
            try:
                set_shortcut(binding)
            except (ValueError, RuntimeError):
                dialog.set_body(_("Atalho indisponível ou já utilizado."))
                return True
            self.row_shortcut.set_subtitle(Gtk.accelerator_get_label(keyval, modifiers) if binding else _("Nenhum"))
            dialog.close()
            return True
        controller.connect("key-pressed", pressed)
        dialog.add_controller(controller)
        dialog.present()

    def _on_gnome_changed(self, row, param, key):
        enabled = row.get_active()
        if not enabled:
            self.config.set(key, False)
            return
        self.row_super.set_sensitive(False)
        self.row_overview.set_sensitive(False)

        def install():
            try:
                return enable_integration(), None
            except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
                return False, str(exc)

        def complete(result):
            active, error = result or (False, _("Não foi possível ativar a integração com GNOME"))
            self.row_super.set_sensitive(True)
            self.row_overview.set_sensitive(True)
            if not active:
                row.handler_block_by_func(self._on_gnome_changed)
                row.set_active(False)
                row.handler_unblock_by_func(self._on_gnome_changed)
                message = error or _("Extensão instalada. Saia da sessão e entre novamente; depois ative esta opção.")
                row.set_subtitle(GLib.markup_escape_text(message))
            self.config.set(key, active)

        self._gnome_worker.submit(install, complete)

    def _on_autostart_changed(self, row, param):
        enabled = row.get_active()
        try:
            if enabled:
                os.makedirs(AUTOSTART_DIR, exist_ok=True)
                with open(AUTOSTART_FILE, "w", encoding="utf-8") as f:
                    f.write(autostart_entry())
                print("[Autostart] Ativado com sucesso.")
            else:
                if os.path.exists(AUTOSTART_FILE):
                    os.remove(AUTOSTART_FILE)
                print("[Autostart] Desativado com sucesso.")
        except Exception as e:
            print(f"[Autostart] Erro ao alterar: {e}")
