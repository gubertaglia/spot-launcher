from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from src.placement import default_position
from src.window import LauncherWindow


class TerminalPlacementTests(unittest.TestCase):
    def test_default_position_centers_above_middle_on_scaled_monitor(self):
        monitor = Mock()
        monitor.get_geometry.return_value = SimpleNamespace(x=1920, y=0, width=1920, height=1080)
        monitor.get_scale_factor.return_value = 2
        surface = Mock()
        surface.get_display.return_value.get_monitor_at_surface.return_value = monitor
        window = Mock(get_surface=Mock(return_value=surface), get_width=Mock(return_value=580),
                      get_height=Mock(return_value=100))
        with patch('src.placement._x11') as x11:
            x11.return_value.XOpenDisplay.return_value = None
            self.assertEqual(default_position(window), [5180, 656])

    def test_pointer_monitor_wins_over_current_monitor_and_connection_closes(self):
        primary, left = Mock(), Mock()
        primary.get_geometry.return_value = SimpleNamespace(x=0, y=0, width=1920, height=1080)
        primary.get_scale_factor.return_value = 1
        left.get_geometry.return_value = SimpleNamespace(x=-1920, y=0, width=1920, height=1080)
        left.get_scale_factor.return_value = 2
        display = Mock()
        display.get_name.return_value = ':0'
        display.get_monitor_at_surface.return_value = primary
        display.get_monitors.return_value = [primary, left]
        surface = Mock()
        surface.get_display.return_value = display
        window = Mock(get_surface=Mock(return_value=surface), get_width=Mock(return_value=580),
                      get_height=Mock(return_value=100))
        def pointer(*args):
            args[4]._obj.value = -2000
            args[5]._obj.value = 100
            return 1
        with patch('src.placement._x11') as x11:
            lib = x11.return_value
            lib.XQueryPointer.side_effect = pointer
            self.assertEqual(default_position(window, [100, 100]), [-2500, 656])
            lib.XCloseDisplay.assert_called_once_with(lib.XOpenDisplay.return_value)
            self.assertEqual(default_position(window, [-2300, 400]), [-2300, 400])

    def test_native_wayland_does_not_open_x11(self):
        surface = SimpleNamespace()
        with patch('src.placement._x11') as x11:
            self.assertIsNone(default_position(SimpleNamespace(get_surface=lambda: surface)))
            x11.assert_not_called()

    def test_saved_position_requires_moving_enabled(self):
        window = Mock()
        window.get_mapped.return_value = True
        window.config = {"allow_move": False, "remember_position": True, "window_position": [2656, 369]}
        with patch('src.window.default_position', return_value=[670, 328]) as default, \
             patch('src.window.position') as move:
            LauncherWindow._restore_position(window, None, None)
            default.assert_called_once_with(window, None)
            move.assert_called_once_with(window, [670, 328])
        window.config['allow_move'] = True
        with patch('src.window.default_position', return_value=[2656, 369]) as default, \
             patch('src.window.position'):
            LauncherWindow._restore_position(window, None, None)
            default.assert_called_once_with(window, [2656, 369])

    def test_terminal_command_runs_only_on_activation(self):
        window = SimpleNamespace(hide_launcher=Mock())
        row = SimpleNamespace(get_activatable=lambda: True, _terminal_command='printf "hello" | cat')
        with patch('src.window.get_default_terminal', return_value=['xterm', '-e']), \
             patch('src.window.subprocess.Popen') as launch, \
             patch.dict('os.environ', {'SHELL': '/bin/sh'}):
            LauncherWindow._on_row_activated(window, None, row)
        launch.assert_called_once_with(['xterm', '-e', '/bin/sh', '-c', 'printf "hello" | cat'],
                                       start_new_session=True)
        window.hide_launcher.assert_called_once()

    def test_missing_terminal_shows_error(self):
        window = SimpleNamespace(hide_launcher=Mock())
        row = SimpleNamespace(get_activatable=lambda: True, _terminal_command='ls')
        with patch('src.window.get_default_terminal', return_value=None), \
             patch('src.window.Adw.MessageDialog') as dialog:
            LauncherWindow._on_row_activated(window, None, row)
        dialog.new.return_value.present.assert_called_once()
        window.hide_launcher.assert_not_called()

class GnomeIntegrationTests(unittest.TestCase):
    def test_installation_requires_new_session_without_trying_to_enable(self):
        from src.gnome import enable_integration, UUID
        failure = SimpleNamespace(returncode=1, stderr='', stdout='')
        success = SimpleNamespace(returncode=0, stderr='', stdout='')
        with patch.dict('os.environ', {'XDG_CURRENT_DESKTOP': 'GNOME'}), \
             patch('src.gnome.subprocess.run', side_effect=[failure, success, success]) as run:
            self.assertFalse(enable_integration())
        self.assertEqual(run.call_args_list[1].args[0][1:3], ('install', '--force'))
        self.assertEqual(run.call_count, 2)

    def test_known_extension_is_enabled(self):
        from src.gnome import enable_integration, UUID
        success = SimpleNamespace(returncode=0, stderr='', stdout='')
        with patch.dict('os.environ', {'XDG_CURRENT_DESKTOP': 'GNOME'}), \
             patch('src.gnome.Path.read_bytes', return_value=b'current'), \
             patch('src.gnome.subprocess.run', return_value=success) as run:
            self.assertTrue(enable_integration())
        self.assertEqual(run.call_args.args[0], ('gnome-extensions', 'enable', UUID))

    def test_outdated_extension_is_reinstalled_and_requires_new_session(self):
        from src.gnome import enable_integration
        success = SimpleNamespace(returncode=0, stderr='', stdout='')
        with patch.dict('os.environ', {'XDG_CURRENT_DESKTOP': 'GNOME'}), \
             patch('src.gnome.Path.read_bytes', side_effect=FileNotFoundError), \
             patch('src.gnome.subprocess.run', return_value=success) as run:
            self.assertFalse(enable_integration())
        self.assertEqual(run.call_args.args[0][1:3], ('install', '--force'))

    def test_preferences_defer_installation_and_recover_after_failure(self):
        from src.preferences import PreferencesWindow
        prefs = Mock()
        prefs._enable_gnome.side_effect = lambda callback: PreferencesWindow._enable_gnome(prefs, callback)
        row = Mock()
        row.get_active.return_value = True
        with patch('src.preferences.enable_integration', side_effect=RuntimeError('failed')) as install:
            PreferencesWindow._on_gnome_changed(prefs, row, None, 'disable_overview')
            install.assert_not_called()
            prefs.row_shortcut.set_sensitive.assert_called_with(False)
            task, complete = prefs._gnome_worker.submit.call_args.args
            result = task()
            complete(result)
        prefs.row_shortcut.set_sensitive.assert_called_with(True)
        prefs.row_overview.set_sensitive.assert_called_with(True)
        row.set_active.assert_called_once_with(False)
        prefs.config.set.assert_called_once_with('disable_overview', False)
        row.set_subtitle.assert_called_once_with('failed')

    def test_rejects_other_desktops(self):
        from src.gnome import enable_integration
        with patch.dict('os.environ', {'XDG_CURRENT_DESKTOP': 'KDE'}), \
             self.assertRaises(RuntimeError):
            enable_integration()
