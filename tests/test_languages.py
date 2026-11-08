import ast
import gettext
import json
import os
from pathlib import Path
from string import Formatter
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock, Mock, patch
from urllib.parse import parse_qs, urlsplit

from src import APP_ID, LOCALE_DIR, system_language
from src.tools import ToolsEngine


class LanguageTests(unittest.TestCase):
    def test_session_language_priority_and_fallback(self):
        for env, expected in [
            ({"LANG": "pt_BR.UTF-8"}, "pt"),
            ({"LANG": "pt_BR", "LC_MESSAGES": "fr_CA.UTF-8"}, "fr"),
            ({"LC_ALL": "es_MX", "LC_MESSAGES": "pt_BR"}, "es"),
            ({"LANGUAGE": "de:pt-BR:es", "LC_ALL": "en_US"}, "pt"),
            ({"LANGUAGE": "de:en_GB:fr"}, "en"),
            ({"LC_ALL": "C.UTF-8", "LANG": "pt_BR"}, "pt"),
            ({"LANG": "de_DE"}, "en"),
            ({}, "en"),
        ]:
            with self.subTest(env=env), patch.dict(os.environ, env, clear=True):
                self.assertEqual(system_language(), expected)

    def test_shipped_catalogs_cover_messages_and_preserve_placeholders(self):
        messages = set()
        for path in (Path(__file__).resolve().parents[1] / "src").glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_":
                    self.assertIsInstance(node.args[0], ast.Constant, path)
                    messages.add(node.args[0].value)
        def fields(text):
            return sorted(name for _, name, _, _ in Formatter().parse(text) if name)

        for lang in ("en", "es", "fr"):
            catalog = gettext.translation(APP_ID, LOCALE_DIR, languages=[lang])
            # Distinguish a missing translation from one identical to the source.
            missing = Mock()
            missing.gettext.side_effect = AssertionError(f"Missing {lang} translation")
            catalog.add_fallback(missing)
            for message in messages:
                with self.subTest(language=lang, message=message):
                    translated = catalog.gettext(message)
                    self.assertEqual(fields(message), fields(translated))
                    self.assertEqual(message.count("%s"), translated.count("%s"))

    def test_file_filters_and_loading_labels_in_each_language(self):
        from src.files import FileSearchEngine
        from src.window import LauncherWindow
        filenames = ("viagem.jpg", "viagem.pdf", "viagem.mp3", "viagem.mp4")
        with TemporaryDirectory() as directory:
            for name in filenames:
                Path(directory, name).touch()
            engine = FileSearchEngine(directory)
            cases = {
                "pt": ("fotos documentos áudios vídeos", "Pesquisando fotos…"),
                "en": ("pictures documents audio movies", "Searching photos…"),
                "es": ("imágenes documentos sonidos películas", "Buscando fotos…"),
                "fr": ("photographies documents sons films", "Recherche de photos…"),
            }
            for lang, (aliases, photo_label) in cases.items():
                catalog = gettext.translation(APP_ID, LOCALE_DIR, languages=[lang], fallback=True)
                for alias, name in zip(aliases.split(), filenames):
                    with self.subTest(lang=lang, alias=alias), patch("src.window._", catalog.gettext):
                        window = Mock(files=engine)
                        LauncherWindow._search_local(window, alias + ": viagem", None)
                        _, task, deliver, label, _ = window._schedule_search.call_args.args
                        result, = task()
                        self.assertEqual(result.name, name)
                        if name.endswith(".jpg"):
                            self.assertEqual(label, photo_label)
                        deliver([result])
                        self.assertEqual(window._render_matches.call_args.args[1], [result])

    def test_natural_weather_and_time_phrases(self):
        for query in ("Que horas são em Lisboa?", "What's the weather like in London?",
                      "¿Qué tiempo hace en Madrid?", "Quel temps fait-il à Paris ?"):
            self.assertTrue(ToolsEngine.supports_query(query), query)

    def test_time_queries_use_localized_place_names_and_cache(self):
        cases = [
            ("pt", "hora em Alemanha", "Alemanha", "São "),
            ("en", "what time is it in Germany?", "Germany", "It’s "),
            ("es", "¿Qué hora es en Alemania?", "Alemania", "Hora en "),
            ("fr", "Quelle heure est-il en Allemagne ?", "Allemagne", "Il est "),
        ]
        with TemporaryDirectory() as cache, patch("src.tools.GLib.get_user_cache_dir", return_value=cache):
            for lang, query, country, prefix in cases:
                catalog = gettext.translation(APP_ID, LOCALE_DIR, languages=[lang], fallback=True)
                with self.subTest(lang=lang), patch("src.tools.LANGUAGE", lang), patch("src.tools._", catalog.gettext):
                    reply = MagicMock()
                    reply.__enter__.return_value.read.return_value = json.dumps({"results": [{
                        "timezone": "Europe/Berlin", "name": "Berlin", "country": country,
                        "country_code": "DE",
                    }]}).encode()
                    with patch("urllib.request.urlopen", return_value=reply) as network:
                        engine = ToolsEngine()
                        self.assertTrue(engine.supports_query(query))
                        result = engine.search(query)
                        self.assertTrue(result["title"].startswith(prefix), result)
                        self.assertIn(country, result["title"])
                        self.assertIsNotNone(ToolsEngine().search(query)["copy"])
                    network.assert_called_once()
                    url = network.call_args.args[0].full_url
                    self.assertEqual(parse_qs(urlsplit(url).query)["language"], [lang])
