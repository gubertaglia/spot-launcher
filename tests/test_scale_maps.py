from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

from gi.repository import GLib
from src.preferences import DEFAULT_CONFIG, PreferencesWindow, launcher_scale
from src.window import LauncherWindow
from src.web import web_search


class ScaleTests(unittest.TestCase):
    def test_default_and_invalid_config(self):
        self.assertEqual(DEFAULT_CONFIG['scale'], 100)
        for value in (50, 75, 100, 125, 200, 0, 250, 101, '125', None, True):
            config = Mock()
            config.get.return_value = value
            expected = value if type(value) is int and value in range(50, 201, 25) else 100
            self.assertEqual(launcher_scale(config), expected)

    def test_scale_updates_transform_and_window_width(self):
        window = Mock()
        window.get_mapped.return_value = False
        for percent, width in ((75, 435), (100, 580), (125, 725), (200, 1160)):
            window.config.get.return_value = percent
            LauncherWindow.apply_scale(window)
            window.set_default_size.assert_called_with(width, -1)
            self.assertEqual(window.scaled_content.get_layout_manager().scale, percent / 100)
            window.scaled_content.get_layout_manager().layout_changed.assert_called()

    def test_resize_preserves_window_center(self):
        window = Mock()
        window.get_mapped.return_value = True
        window.get_surface.return_value.get_scale_factor.return_value = 2
        window.get_width.return_value = 725
        window.get_height.return_value = 250
        with patch('src.window.position') as move:
            LauncherWindow._center_scaled_window(window, [1000, 400], (580, 200))
        move.assert_called_once_with(window, [855, 350])

    def test_placeholder_saves_arbitrary_text_and_empty_restores_default(self):
        window = SimpleNamespace(config={'search_placeholder': 'Olá <mundo> & você'})
        self.assertEqual(LauncherWindow.search_placeholder(window), 'Olá <mundo> & você')
        window.config['search_placeholder'] = ''
        self.assertTrue(LauncherWindow.search_placeholder(window))
        prefs, row = Mock(), Mock()
        row.get_text.return_value = 'Minha busca'
        PreferencesWindow._on_placeholder_changed(prefs, row)
        prefs.config.set.assert_called_once_with('search_placeholder', 'Minha busca')
        prefs.get_transient_for.return_value.search_entry.set_placeholder_text.assert_called_once()

    def test_preferences_save_and_apply_immediately(self):
        prefs, row = Mock(), Mock()
        row.get_value.return_value = 125
        PreferencesWindow._on_scale_changed(prefs, row, None)
        prefs.config.set.assert_called_once_with('scale', 125)
        prefs.get_transient_for.return_value.apply_scale.assert_called_once_with()


class MapTests(unittest.TestCase):
    def rows(self, destination, maps):
        with patch('src.window.Gio.DesktopAppInfo.new', return_value=maps), \
             patch('src.window.Adw.ActionRow', side_effect=lambda **kwargs: Mock(**kwargs)), \
             patch('src.window.Gtk.Image.new_from_icon_name'):
            return list(LauncherWindow._map_rows(None, destination))

    def test_browser_always_available_native_maps_only_when_installed(self):
        for destination in ('São Paulo', 'Brasil', 'Paris & café #1?'):
            browser, = self.rows(destination, None)
            self.assertEqual(parse_qs(urlsplit(browser._web_url).query)['query'], [destination])
            maps = Mock()
            native, browser = self.rows(destination, maps)
            self.assertIs(native._maps_app, maps)
            self.assertEqual(parse_qs(urlsplit(native._maps_uri).query)['q'], [destination])
            maps.launch_uris.assert_not_called()

    def test_plain_search_keeps_local_results_then_offers_web_and_maps(self):
        window = SimpleNamespace(_clear_results=Mock(), _append_result=Mock(),
                                 _match_row=lambda item: item, _map_rows=Mock(return_value=['maps']),
                                 _web_row=Mock(return_value='web'), scrolled_window=Mock(),
                                 _result_count=3, list_box=Mock())
        window._append_page = lambda: window._append_result(list(window._remaining_rows))
        local = SimpleNamespace(score=10)
        LauncherWindow._render_matches(window, [local], [], False, web_search('São Paulo'))
        window._map_rows.assert_called_once_with('São Paulo')
        window._append_result.assert_called_once_with([local, 'web', 'maps'])

    def test_native_map_launch_and_failure(self):
        window = SimpleNamespace(hide_launcher=Mock())
        maps = Mock()
        row = SimpleNamespace(get_activatable=lambda: True, _maps_app=maps, _maps_uri='geo:0,0?q=Paris')
        LauncherWindow._on_row_activated(window, None, row)
        maps.launch_uris.assert_called_once_with([row._maps_uri], None)
        window.hide_launcher.assert_called_once()
        window.hide_launcher.reset_mock()
        maps.launch_uris.side_effect = GLib.Error('unavailable')
        with patch('src.window.Adw.MessageDialog') as dialog:
            LauncherWindow._on_row_activated(window, None, row)
        window.hide_launcher.assert_not_called()
        dialog.new.return_value.present.assert_called_once()
