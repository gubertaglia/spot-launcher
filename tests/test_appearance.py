import unittest
from unittest.mock import Mock

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
