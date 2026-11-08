import unittest
from unittest.mock import Mock, patch

from src.gnome import SHORTCUT_PATH, set_shortcut
from src.preferences import PreferencesWindow
from gi.repository import Gdk


class ShortcutTests(unittest.TestCase):
    def test_add_and_remove_preserve_other_shortcuts(self):
        settings, own, other = Mock(), Mock(), Mock()
        settings.get_strv.return_value = ['/other/']
        other.get_string.return_value = '<Alt>x'
        with patch('src.gnome.shortcut_settings', return_value=(settings, own)), \
             patch('gi.repository.Gio.Settings.new_with_path', return_value=other):
            set_shortcut('<Control>space')
            settings.set_strv.assert_called_with('custom-keybindings', ['/other/', SHORTCUT_PATH])
            own.set_string.assert_any_call('binding', '<Control>space')
            settings.get_strv.return_value = ['/other/', SHORTCUT_PATH]
            set_shortcut('')
            settings.set_strv.assert_called_with('custom-keybindings', ['/other/'])

    def test_existing_custom_shortcut_is_not_overwritten(self):
        settings, own, other = Mock(), Mock(), Mock()
        settings.get_strv.return_value = ['/other/']
        other.get_string.return_value = '<Control>space'
        with patch('src.gnome.shortcut_settings', return_value=(settings, own)), \
             patch('gi.repository.Gio.Settings.new_with_path', return_value=other):
            with self.assertRaises(ValueError):
                set_shortcut('<Control>space')
        own.set_string.assert_not_called()


class ShortcutPreferencesTests(unittest.TestCase):
    def capture(self):
        prefs, dialog, controller = Mock(), Mock(), Mock()
        with patch('src.preferences.Adw.MessageDialog.new', return_value=dialog), \
             patch('src.preferences.Gtk.EventControllerKey', return_value=controller):
            PreferencesWindow._choose_shortcut(prefs, None)
        callbacks = dict(call.args for call in controller.connect.call_args_list)
        return prefs, dialog, callbacks['key-pressed'], callbacks['key-released']

    def test_super_is_saved_on_release_only(self):
        for key in (Gdk.KEY_Super_L, Gdk.KEY_Super_R):
            prefs, dialog, press, release = self.capture()
            press(None, key, 0, 0)
            prefs._save_shortcut.assert_not_called()
            release(None, key, 0, Gdk.ModifierType.SUPER_MASK)
            prefs._save_shortcut.assert_called_once_with('Super', dialog)

    def test_super_combination_is_not_saved_as_super_alone(self):
        prefs, dialog, press, release = self.capture()
        press(None, Gdk.KEY_Super_L, 0, 0)
        press(None, Gdk.KEY_space, 0, Gdk.ModifierType.SUPER_MASK)
        release(None, Gdk.KEY_Super_L, 0, 0)
        prefs._save_shortcut.assert_called_once_with('<Super>space', dialog)

    def test_modified_super_is_not_saved_as_super_alone(self):
        prefs, dialog, press, release = self.capture()
        press(None, Gdk.KEY_Super_L, 0, Gdk.ModifierType.CONTROL_MASK)
        release(None, Gdk.KEY_Super_L, 0, 0)
        prefs._save_shortcut.assert_not_called()

    def test_backspace_removes_and_escape_cancels(self):
        prefs, dialog, press, release = self.capture()
        press(None, Gdk.KEY_BackSpace, 0, 0)
        prefs._save_shortcut.assert_called_once_with('', dialog)
        prefs._save_shortcut.reset_mock()
        press(None, Gdk.KEY_Escape, 0, 0)
        dialog.close.assert_called_once()
        prefs._save_shortcut.assert_not_called()

    def test_super_waits_for_integration_before_replacing_shortcut(self):
        prefs, dialog = Mock(), Mock()
        with patch('src.preferences.set_shortcut') as save:
            PreferencesWindow._save_shortcut(prefs, 'Super', dialog)
            save.assert_not_called()
            prefs.config.set.assert_not_called()
            prefs._enable_gnome.call_args.args[0](True, '')
        save.assert_called_once_with('')
        prefs.config.set.assert_called_once_with('super_launcher', True)
        prefs.row_shortcut.set_subtitle.assert_called_once_with('Super')
        dialog.close.assert_called_once()

    def test_failed_super_installation_keeps_previous_shortcut(self):
        prefs, dialog = Mock(), Mock()
        with patch('src.preferences.set_shortcut') as save:
            PreferencesWindow._save_shortcut(prefs, 'Super', dialog)
            prefs._enable_gnome.call_args.args[0](False, 'failed')
        save.assert_not_called()
        prefs.config.set.assert_not_called()
        dialog.set_body.assert_called_once_with('failed')
        dialog.close.assert_not_called()

    def test_other_shortcut_or_removal_disables_super(self):
        for binding in ('<Control>space', ''):
            prefs, dialog = Mock(), Mock()
            with patch('src.preferences.set_shortcut') as save:
                PreferencesWindow._save_shortcut(prefs, binding, dialog)
            save.assert_called_once_with(binding)
            prefs.config.set.assert_called_once_with('super_launcher', False)
            prefs._enable_gnome.assert_not_called()
            dialog.close.assert_called_once()

    def test_conflict_keeps_super_enabled(self):
        prefs, dialog = Mock(), Mock()
        with patch('src.preferences.set_shortcut', side_effect=ValueError('conflict')):
            PreferencesWindow._save_shortcut(prefs, '<Control>space', dialog)
        prefs.config.set.assert_not_called()
        dialog.close.assert_not_called()
