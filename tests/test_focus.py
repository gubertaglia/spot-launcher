from types import SimpleNamespace
import time
import unittest
from unittest.mock import Mock, patch

from src.window import Gdk, LauncherWindow


class FocusTests(unittest.TestCase):
    def window(self, **changes):
        window = SimpleNamespace(
            _focus_ready=False, _is_prefs_open=False, _moving=False, _context_open=False,
            config={"hide_on_focus_loss": True}, is_visible=Mock(return_value=True),
            is_active=Mock(return_value=False), hide_launcher=Mock(),
        )
        window._check_focus = lambda: LauncherWindow._check_focus(window)
        window.__dict__.update(changes)
        return window

    def check(self, window, children=()):
        with patch('src.window.Gtk.Window.list_toplevels', return_value=children):
            self.assertFalse(window._check_focus())

    def test_focus_loss_before_activation_does_not_hide(self):
        window = self.window()
        self.check(window)
        window.hide_launcher.assert_not_called()

    def test_rapid_focus_loss_after_activation_hides(self):
        window = self.window()
        with patch('src.window.GLib.idle_add') as idle:
            window.is_active.return_value = True
            LauncherWindow._on_active_changed(window, None, None)
            window.is_active.return_value = False
            LauncherWindow._on_active_changed(window, None, None)
        self.assertTrue(window._focus_ready)
        with patch('src.window.Gtk.Window.list_toplevels', return_value=[]):
            idle.call_args.args[0]()
        window.hide_launcher.assert_called_once()

    def test_disabled_hidden_active_or_protected_window_stays_open(self):
        for state in (
            {"config": {"hide_on_focus_loss": False}},
            {"is_visible": Mock(return_value=False)},
            {"is_active": Mock(return_value=True)},
            {"_is_prefs_open": True}, {"_moving": True}, {"_context_open": True},
        ):
            with self.subTest(state=state):
                window = self.window(_focus_ready=True, **state)
                self.check(window)
                window.hide_launcher.assert_not_called()

    def test_visible_dialog_protects_parent_even_without_preferences_flag(self):
        window = self.window(_focus_ready=True)
        dialog = Mock()
        dialog.get_transient_for.return_value = window
        dialog.is_visible.return_value = True
        self.check(window, [dialog])
        window.hide_launcher.assert_not_called()
        dialog.is_visible.return_value = False
        self.check(window, [dialog])
        window.hide_launcher.assert_called_once()

    def test_reopening_waits_for_new_focus_without_a_timer(self):
        window = self.window(
            _focus_ready=True, preferences_window=None, search_entry=Mock(),
            scaled_content=Mock(), _fade_to=Mock(),
            _on_search_changed=Mock(), set_visible=Mock(), present=Mock(),
            _on_clipboard_changed=Mock(), clipboard=Mock(), _show_update_prompt=Mock(),
            _last_update_check=time.monotonic(),
        )
        with patch('src.window.GLib.timeout_add') as timeout:
            LauncherWindow.show_launcher(window)
            self.assertFalse(window._focus_ready)
            window.is_active.return_value = True
            LauncherWindow.show_launcher(window)
            self.assertTrue(window._focus_ready)
        timeout.assert_not_called()

    def test_closing_emoji_picker_rechecks_focus(self):
        window = self.window(_context_closed=Mock())
        chooser = Mock()
        LauncherWindow._on_emoji_closed(window, chooser)
        chooser.unparent.assert_called_once()
        window._context_closed.assert_called_once_with(chooser)

    def test_disabled_focus_hiding_keeps_explicit_close_and_result_actions(self):
        for action in ("escape", "shortcut", "result"):
            with self.subTest(action=action):
                window = self.window(
                    config={"hide_on_focus_loss": False}, calendar_panel=None,
                    preferences_window=None, _tool_copy_val=None, clipboard=Mock(),
                )
                if action == "escape":
                    LauncherWindow._on_key_pressed(window, None, Gdk.KEY_Escape, 0, 0)
                elif action == "shortcut":
                    LauncherWindow.toggle_launcher(window)
                else:
                    row = SimpleNamespace(get_activatable=lambda: True, _clipboard_text="copiado")
                    with patch("src.window.Gdk.Display.get_default") as display:
                        display.return_value.get_clipboard.return_value = window.clipboard
                        LauncherWindow._on_row_activated(window, None, row)
                    window.clipboard.set.assert_called_once_with("copiado")
                window.hide_launcher.assert_called_once()


class ContextMenuTests(unittest.TestCase):
    def test_menu_hides_and_restores_search_content(self):
        window = SimpleNamespace(search_content=Mock(), search_entry=Mock(), _check_focus=Mock())
        menu = Mock()
        with patch("src.window.GLib.idle_add"):
            for visible in (True, False):
                menu.get_visible.return_value = visible
                LauncherWindow._context_visibility_changed(window, menu, None)
                window.search_content.set_visible.assert_called_with(not visible)

    def test_menu_shortcuts_activate_only_menu_actions(self):
        row = SimpleNamespace(_context_action=Mock())
        window = SimpleNamespace(_context_open=True, context_menu=Mock())
        window.context_menu.get_row_at_index.return_value = row
        self.assertTrue(LauncherWindow._on_key_pressed(window, None, Gdk.KEY_1, 0, Gdk.ModifierType.ALT_MASK))
        window.context_menu.get_row_at_index.assert_called_once_with(1)
        row._context_action.assert_called_once_with(None)
