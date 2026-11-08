from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

from src.web import map_search, web_search
from src.window import LauncherWindow


class WebSearchTests(unittest.TestCase):
    def test_preserves_query_and_encodes_special_characters(self):
        query = 'São Paulo & C++ #1? "GTK"'
        result = web_search(query)
        self.assertFalse(result.explicit)
        url = urlsplit(result.url)
        self.assertEqual((url.scheme, url.netloc, url.path),
                         ("https", "www.google.com", "/search"))
        self.assertEqual(parse_qs(url.query), {"q": [query]})

    def test_map_search_encodes_destination_and_requires_a_query(self):
        url = urlsplit(map_search("mapa São Paulo & café"))
        self.assertEqual((url.netloc, url.path), ("www.google.com", "/maps/search/"))
        self.assertEqual(parse_qs(url.query), {"api": ["1"], "query": ["São Paulo & café"]})
        for query in ("mapa", "maps ", "mapas.com"):
            self.assertIsNone(map_search(query))

    def test_prefixes_require_word_boundary_and_nonempty_query(self):
        for prefix in ("g", "GOOGLE", "Web"):
            result = web_search(f"  {prefix}\tPrevisão do Tempo  ")
            self.assertTrue(result.explicit)
            self.assertEqual(result.query, "Previsão do Tempo")
        for query in ("", "  ", "g ", "google", "web\t"):
            self.assertIsNone(web_search(query))
        for query in ("git", "google.com", "website"):
            self.assertFalse(web_search(query).explicit)

    def window(self):
        window = SimpleNamespace(
            calendar_panel=Mock(), list_box=Mock(), scrolled_window=Mock(), calculator=Mock(),
            matcher=Mock(), indexer=Mock(), config=Mock(), files=Mock(),
            _web_row=Mock(), _append_result=Mock(), _clear_results=Mock(), tools=Mock(),
            _schedule_search=Mock(), _file_worker=Mock(), _render_matches=Mock(),
        )
        window.list_box.get_first_child.return_value = None
        window.calculator.evaluate.return_value = None
        window.matcher.search.return_value = []
        window.tools.supports_query.return_value = False
        window._search_local = lambda *args: LauncherWindow._search_local(window, *args)
        window.files.search_current.return_value = []
        window.config.get.return_value = 7
        return window

    def test_explicit_search_bypasses_local_providers(self):
        window = self.window()
        LauncherWindow._do_search(window, "g 2+2")
        self.assertEqual(window._web_row.call_args.args[0].query, "2+2")
        window.calculator.evaluate.assert_not_called()
        window.matcher.search.assert_not_called()
        window._schedule_search.assert_not_called()
        window.scrolled_window.set_visible.assert_called_once_with(True)

    def test_no_local_results_still_offers_google(self):
        window = self.window()
        LauncherWindow._do_search(window, "uma pesquisa sem resultados locais")
        _, task, complete, _, _ = window._schedule_search.call_args.args
        self.assertIsNone(window._render_matches.call_args.args[3])
        complete(task())
        self.assertEqual(window._render_matches.call_args.args[3].query,
                         "uma pesquisa sem resultados locais")

    def test_search_opens_only_when_activated_and_hides_on_success(self):
        result = web_search("g São Paulo & café")
        window = SimpleNamespace(hide_launcher=Mock())
        row = SimpleNamespace(get_activatable=lambda: True, _web_url=result.url)
        with patch("src.window.Gio.AppInfo.launch_default_for_uri", return_value=True) as launch:
            launch.assert_not_called()
            LauncherWindow._on_row_activated(window, None, row)
        launch.assert_called_once_with(result.url, None)
        window.hide_launcher.assert_called_once()

    def test_browser_failure_keeps_launcher_open_and_shows_error(self):
        from gi.repository import GLib
        window = SimpleNamespace(hide_launcher=Mock())
        row = SimpleNamespace(get_activatable=lambda: True, _web_url=web_search("café").url)
        with patch("src.window.Gio.AppInfo.launch_default_for_uri", side_effect=GLib.Error("sem navegador")), \
                patch("src.window.Adw.MessageDialog") as dialog:
            LauncherWindow._on_row_activated(window, None, row)
        window.hide_launcher.assert_not_called()
        dialog.new.return_value.present.assert_called_once()


if __name__ == "__main__":
    unittest.main()
