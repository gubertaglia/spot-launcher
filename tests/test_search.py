import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from gi.repository import Gio
from src.history import HistoryManager
from src.indexer import AppEntry, AppIndexer
from src.matcher import SearchMatcher
from src.window import LauncherWindow


def app(name, keywords=(), description="", setting=False):
    return AppEntry(name + ".desktop", name, description, "", False, None,
                    list(keywords), setting)


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        with patch("src.history.GLib.get_user_cache_dir", return_value=self.directory.name):
            self.history = HistoryManager()
        self.matcher = SearchMatcher(self.history)

    def test_metadata_accents_phrases_and_typos(self):
        sound = app("Som", ["volume", "microfone", "saída de áudio"])
        editor = app("Visual Studio Code", ["editor", "desenvolvimento"])
        for query, expected in (("quero mudar o volume", sound), ("microfne", sound), ("som microfne", sound),
                                ("saida audio", sound), ("editor", editor),
                                ("studio visual", editor), ("CODE", editor)):
            with self.subTest(query=query):
                self.assertIs(self.matcher.search(query, [sound, editor])[0].entry, expected)
        browser = app("Navegador", description="Navegue pela internet")
        self.assertIs(self.matcher.search("internet", [browser])[0].entry, browser)

    def test_usage_cannot_admit_irrelevant_results_or_displace_exact_name(self):
        exact, other, unrelated = app("Code"), app("Code Editor"), app("Fotos")
        for _ in range(10):
            self.history.record_launch(other.id, "code")
            self.history.record_launch(unrelated.id, "code")
        results = self.matcher.search("code", [other, unrelated, exact])
        self.assertEqual([result.entry for result in results], [exact, other])
        self.assertEqual(self.matcher.search("zzzxq", [other, unrelated, exact]), [])

    def test_learns_choice_for_query_and_preserves_it_on_reload(self):
        first, second = app("Alpha", ["editor"]), app("Beta", ["editor"])
        self.assertIs(self.matcher.search("editor", [first, second])[0].entry, first)
        self.history.record_launch(second.id, "  EDITOR  ")
        with patch("src.history.GLib.get_user_cache_dir", return_value=self.directory.name):
            loaded = HistoryManager()
        self.assertEqual(loaded.get_query_count(second.id, "editor"), 1)
        self.assertIs(SearchMatcher(loaded).search("editor", [first, second])[0].entry, second)
        self.assertEqual(loaded.get_query_count(second.id, "internet"), 0)

    def test_empty_query_unlimited_and_settings_hidden_from_defaults(self):
        normal, setting = app("Editor"), app("Wi-Fi", setting=True)
        self.history.record_launch(setting.id, "wifi")
        self.assertEqual([r.entry for r in self.matcher.search("", [normal, setting], None)], [normal])
        self.assertIs(self.matcher.search("wi-fi", [normal, setting])[0].entry, setting)
        self.assertEqual(self.matcher.search("", [normal], 0), [])
        favorite = app("Favorite")
        self.history.record_launch(favorite.id)
        self.history.record_launch(setting.id)
        self.assertIs(self.matcher.search("", [normal, favorite, setting], 1)[0].entry, favorite)

    def test_short_prefixes_use_history_instead_of_name_length(self):
        short, long = app("Boxes"), app("Bluetooth Preferences")
        hidden_match = app("Editor", ["boxes"], "Bluetooth tool")
        results = self.matcher.search("B", [short, hidden_match, long])
        self.assertEqual([result.entry for result in results], [long, short])
        self.assertEqual(results[0].score, results[1].score)
        self.history.record_launch(short.id, "b")
        self.assertIs(self.matcher.search("b", [long, short])[0].entry, short)
        self.history.record_launch(long.id, "bl")
        self.assertIs(self.matcher.search("bl", [short, long])[0].entry, long)
        self.assertEqual(self.matcher.search("ox", [short, hidden_match, long]), [])

    def test_legacy_history_validation_and_bounded_learning(self):
        path = Path(self.history.file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"old.desktop": 3, "bad": True, "negative": -1}))
        self.history._load()
        self.assertEqual(self.history._usage, {"old.desktop": 3})
        for i in range(205):
            self.history.record_launch("new.desktop", f"query {i}")
        self.assertEqual(len(self.history._queries), 200)
        self.assertNotIn("query 0", self.history._queries)
        self.assertEqual(self.history.get_count("old.desktop"), 3)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        for value in ([], {"usage": [], "queries": {}}, {"usage": {}, "queries": {"x": []}}):
            path.write_text(json.dumps(value))
            self.history._load()

    def test_only_successful_launches_are_learned(self):
        entry = app("Editor")
        for successful in (False, True):
            window = SimpleNamespace(indexer=Mock(), history=Mock(), search_entry=Mock(), hide_launcher=Mock(), _tool_copy_val=None)
            window.indexer.launch.return_value = successful
            window.search_entry.get_text.return_value = "editor"
            row = SimpleNamespace(get_activatable=lambda: True, _app_entry=entry)
            LauncherWindow._on_row_activated(window, None, row)
            if successful:
                window.history.record_launch.assert_called_once_with(entry.id, "editor")
            else:
                window.history.record_launch.assert_not_called()

    def test_indexes_installed_settings_without_other_hidden_apps(self):
        with TemporaryDirectory() as directory:
            entries = []
            for name, extra in (("wifi", "Categories=Settings;X-GNOME-Settings-Panel;\n"),
                                ("hidden", "Categories=Settings;X-GNOME-Settings-Panel;\nHidden=true\n"),
                                ("helper", ""),
                                ("foreign", "Categories=Settings;X-GNOME-Settings-Panel;\nOnlyShowIn=Other;\n")):
                path = Path(directory, name + ".desktop")
                path.write_text("[Desktop Entry]\nType=Application\nName=" + name +
                                "\nExec=/bin/true\nNoDisplay=true\n" + extra)
                entries.append(Gio.DesktopAppInfo.new_from_filename(str(path)))
            indexer = AppIndexer.__new__(AppIndexer)
            with patch("src.indexer.Gio.AppInfo.get_all", return_value=entries):
                indexer.reload()
            self.assertEqual([entry.name for entry in indexer.get_apps()], ["wifi"])
            self.assertTrue(indexer.get_apps()[0].is_setting)
