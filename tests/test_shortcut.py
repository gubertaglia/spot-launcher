import unittest
from unittest.mock import Mock, patch

from src.gnome import SHORTCUT_PATH, set_shortcut


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
