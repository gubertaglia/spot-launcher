from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch, call

from src.preferences import DEFAULT_CONFIG, PreferencesWindow
from src.window import LauncherWindow


class BlurCompatibilityTests(unittest.TestCase):
    def test_compatibility_is_opt_in_and_can_be_removed(self):
        self.assertFalse(DEFAULT_CONFIG['blur_my_shell'])
        window = Mock()
        window.config.get.return_value = True
        LauncherWindow.set_blur_compatibility(window)
        window.add_css_class.assert_called_once_with('blur-my-shell')
        window.remove_css_class.assert_not_called()
        window.config.get.return_value = False
        LauncherWindow.set_blur_compatibility(window)
        window.remove_css_class.assert_called_once_with('blur-my-shell')

    def test_preferences_save_and_refresh_parent_immediately(self):
        prefs, row = Mock(), Mock()
        row.get_active.return_value = True
        PreferencesWindow._on_blur_changed(prefs, row, None)
        prefs.config.set.assert_called_once_with('blur_my_shell', True)
        prefs.get_transient_for.return_value.set_blur_compatibility.assert_called_once_with()

    def test_blur_does_not_modify_external_settings(self):
        prefs, row = Mock(), Mock()
        with patch('src.preferences.Gio.Settings.new_full') as settings:
            for enabled in (True, False):
                row.get_active.return_value = enabled
                PreferencesWindow._on_blur_changed(prefs, row, None)
            settings.assert_not_called()



class FadeTests(unittest.TestCase):
    def window(self, opacity=1, animations=True):
        content = Mock()
        content.get_opacity.side_effect = lambda: content.opacity
        content.set_opacity.side_effect = lambda value: setattr(content, "opacity", value)
        content.opacity = opacity
        content.add_tick_callback.return_value = 7
        clock = Mock()
        clock.get_frame_time.return_value = 1_000_000
        settings = Mock()
        settings.get_property.return_value = animations
        window = SimpleNamespace(
            scaled_content=content, _fade_tick=0, _closing=False,
            get_settings=lambda: settings, get_frame_clock=lambda: clock,
            set_visible=Mock(), _clear_results=Mock(), _cancel_pending_search=Mock(),
            is_visible=lambda: True, preferences_window=None, show_launcher=Mock(),
        )
        for name in ("_cancel_fade", "_finish_fade", "_fade_to", "hide_launcher"):
            setattr(window, name, lambda *args, name=name: getattr(LauncherWindow, name)(window, *args))
        return window, clock, settings

    def tick(self, window, clock, elapsed):
        callback = window.scaled_content.add_tick_callback.call_args.args[0]
        clock.get_frame_time.return_value += elapsed
        return callback(window.scaled_content, clock)

    def test_open_and_close_durations(self):
        for initial, target, duration in ((0, 1, 120_000), (1, 0, 90_000)):
            with self.subTest(target=target):
                window, clock, _ = self.window(initial)
                window._fade_to(target)
                self.assertTrue(self.tick(window, clock, duration // 2))
                self.assertGreater(window.scaled_content.opacity, 0)
                self.assertLess(window.scaled_content.opacity, 1)
                window.set_visible.assert_not_called()
                self.assertFalse(self.tick(window, clock, duration // 2))
                self.assertEqual(window.scaled_content.opacity, target)
                self.assertEqual(window._fade_tick, 0)
                if target == 0:
                    window.set_visible.assert_called_once_with(False)
                    window._clear_results.assert_called_once()
                else:
                    window._clear_results.assert_not_called()

    def test_reverse_preserves_current_opacity_and_cancels_old_tick(self):
        window, clock, _ = self.window()
        window.hide_launcher()
        self.tick(window, clock, 30_000)
        opacity = window.scaled_content.opacity
        window._fade_to(1)
        window.scaled_content.remove_tick_callback.assert_called_once_with(7)
        self.assertEqual(window.scaled_content.opacity, opacity)
        self.assertFalse(self.tick(window, clock, 120_000))
        self.assertEqual(window.scaled_content.opacity, 1)
        window.set_visible.assert_not_called()
        window._clear_results.assert_not_called()

    def test_repeated_close_does_not_restart_or_activate_results(self):
        window, clock, _ = self.window()
        window.hide_launcher()
        window.hide_launcher()
        window._cancel_pending_search.assert_called_once()
        window.scaled_content.set_sensitive.assert_called_once_with(False)
        window.scaled_content.add_tick_callback.assert_called_once()
        row = Mock()
        LauncherWindow._on_row_activated(window, None, row)
        row.get_activatable.assert_not_called()
        self.assertTrue(LauncherWindow._on_key_pressed(window, None, None, None, None))
        self.tick(window, clock, 90_000)
        window._clear_results.assert_called_once()

    def test_toggle_during_exit_reopens(self):
        window, _, _ = self.window()
        window.hide_launcher()
        LauncherWindow.toggle_launcher(window)
        window.show_launcher.assert_called_once()

    def test_disabled_animations_complete_immediately(self):
        window, _, _ = self.window(animations=False)
        window.hide_launcher()
        window.scaled_content.add_tick_callback.assert_not_called()
        window.set_visible.assert_called_once_with(False)
        window._clear_results.assert_called_once()
        self.assertEqual(window.scaled_content.opacity, 0)

    def test_disabling_animations_mid_fade_completes_next_frame(self):
        window, clock, settings = self.window()
        window.hide_launcher()
        settings.get_property.return_value = False
        self.assertFalse(self.tick(window, clock, 1_000))
        self.assertEqual(window.scaled_content.opacity, 0)
        window.set_visible.assert_called_once_with(False)

    def test_cancel_removes_callback(self):
        window, _, _ = self.window()
        window._fade_to(0)
        window._cancel_fade()
        window.scaled_content.remove_tick_callback.assert_called_once_with(7)
        self.assertEqual(window._fade_tick, 0)


    def test_reopening_restores_input_and_focus_before_fading(self):
        window, _, _ = self.window(.4)
        calls = Mock()
        window._closing = True
        window.config = {"clear_on_hide": False}
        window.search_entry = calls.search_entry
        window._on_search_changed = Mock()
        window._focus_ready = False
        window.is_active = lambda: False
        window.present = Mock()
        window._fade_to = calls.fade
        window._on_clipboard_changed = Mock()
        window.clipboard = Mock()
        window._show_update_prompt = Mock()
        window._last_update_check = float("inf")
        LauncherWindow.show_launcher(window)
        self.assertFalse(window._closing)
        window.scaled_content.set_sensitive.assert_called_once_with(True)
        self.assertEqual(window.scaled_content.opacity, .4)
        self.assertEqual(calls.mock_calls, [
            call.search_entry.grab_focus(), call.fade(1),
        ])
        window.search_entry.set_text.assert_not_called()
