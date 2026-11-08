from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from gi.repository import GLib
from src.system_actions import system_actions, execute_action
from src.window import LauncherWindow


class SystemActionTests(unittest.TestCase):
    def actions(self, query):
        with patch('src.system_actions.shutil.which', side_effect=lambda name: '/usr/bin/' + name):
            return system_actions(query)

    def test_search_aliases_accents_and_confirmation(self):
        for query, binary, confirm in (
            ('configurações do sistema', 'gnome-control-center', False),
            ('force quit', 'gnome-system-monitor', False),
            ('tela de bloqueio', 'loginctl', False),
            ('sleep', 'systemctl', False),
            ('reiniciar', 'systemctl', True),
            ('desligar', 'systemctl', True),
            ('sair da sessão', 'gnome-session-quit', True),
            ('redémarrer', 'systemctl', True),
        ):
            with self.subTest(query=query), patch.dict('os.environ', {'XDG_CURRENT_DESKTOP': 'GNOME'}):
                action, = self.actions(query)
                self.assertEqual(action.command[0], binary)
                self.assertEqual(action.confirm, confirm)
        self.assertEqual(len(self.actions('sistema')), 7)
        self.assertEqual(self.actions(''), [])
        self.assertEqual(self.actions('desligar; touch /tmp/unsafe'), [])

    def test_missing_commands_are_hidden_and_desktop_is_preferred(self):
        with patch('src.system_actions.shutil.which', return_value=None):
            self.assertEqual(system_actions('sistema'), [])
        with patch.dict('os.environ', {'XDG_CURRENT_DESKTOP': 'KDE'}):
            self.assertEqual(self.actions('system settings')[0].command, ('systemsettings',))
            self.assertEqual(self.actions('logout')[0].command[0], 'qdbus6')

    def test_execute_reports_async_command_failure_and_spawn_failure(self):
        action = self.actions('reiniciar')[0]
        complete = Mock()
        process = Mock()
        process.communicate_utf8_finish.return_value = (True, None, 'Permission denied')
        process.get_successful.return_value = False
        with patch('src.system_actions.Gio.Subprocess.new', return_value=process) as spawn:
            execute_action(action, complete)
        self.assertEqual(spawn.call_args.args[0], ('systemctl', 'reboot'))
        complete.assert_not_called()
        process.communicate_utf8_async.call_args.args[2](process, Mock())
        complete.assert_called_once_with('Permission denied')
        complete.reset_mock()
        with patch('src.system_actions.Gio.Subprocess.new', side_effect=GLib.Error('unavailable')):
            execute_action(action, complete)
        self.assertIn('unavailable', complete.call_args.args[0])

    def test_monitor_launch_does_not_wait_for_monitor_to_close(self):
        complete = Mock()
        with patch('src.system_actions.Gio.Subprocess.new') as spawn:
            execute_action(self.actions('force quit')[0], complete)
        complete.assert_called_once_with(None)
        spawn.return_value.communicate_utf8_async.assert_not_called()

    def test_confirmation_cancel_and_accept(self):
        action = self.actions('desligar')[0]
        for response in ('cancel', 'execute'):
            window = SimpleNamespace(hide_launcher=Mock())
            with patch('src.window.Adw.MessageDialog') as dialogs, patch('src.window.execute_action') as execute:
                LauncherWindow._activate_system_action(window, action)
                dialog = dialogs.new.return_value
                execute.assert_not_called()
                self.assertTrue(window._is_prefs_open)
                dialog.set_default_response.assert_called_once_with('cancel')
                dialog.connect.call_args.args[1](dialog, response)
                self.assertFalse(window._is_prefs_open)
                self.assertEqual(execute.call_count, int(response == 'execute'))
                if response == 'execute':
                    execute.call_args.args[1](None)
                    window.hide_launcher.assert_called_once()

    def test_row_activation_and_rendering(self):
        action = self.actions('bloquear')[0]
        window = SimpleNamespace(_activate_system_action=Mock())
        row = SimpleNamespace(get_activatable=lambda: True, _system_action=action)
        LauncherWindow._on_row_activated(window, None, row)
        window._activate_system_action.assert_called_once_with(action)
        window = SimpleNamespace(_clear_results=Mock(), _append_page=Mock(),
                                 scrolled_window=Mock(), list_box=Mock(), _result_count=1)
        with patch('src.window.Adw.ActionRow') as rows, patch('src.window.Gtk.Image.new_from_icon_name'):
            LauncherWindow._render_matches(window, [], [], False, None, actions=[action])
            result, = list(window._remaining_rows)
        self.assertIs(result._system_action, action)
        rows.assert_called_once_with(title=action.title, subtitle=action.subtitle, activatable=True)


if __name__ == '__main__':
    unittest.main()
