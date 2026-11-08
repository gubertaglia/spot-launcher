import gettext
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from urllib.parse import urlsplit

from gi.repository import Gio

from src import APP_ID, LOCALE_DIR
from src.files import FileEntry, FileSearchEngine
from src.indexer import AppIndexer
from src.matcher import MatchResult
from src.search import search_score, word_distance, result_key
from src.search_commands import command_query, command_suggestion
from src.system_actions import system_actions
from src.tools import ToolsEngine
from src.web import dictionary_search, translation_search, map_destination, web_search
from src.window import LauncherWindow
from tests.test_search import app
from tests import test_search


class SmartSearchTests(unittest.TestCase):
    def test_shared_bands_and_short_word_limits(self):
        scores = [search_score('editor', 'Editor'), search_score('editor', 'Editor Pro'),
                  search_score('pro editor', 'Editor Pro'),
                  search_score('editor', 'Alpha', 'editor'), search_score('edtior', 'Editor')]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertTrue(all(scores))
        for term, candidate, expected in [('som', 'son', None), ('code', 'cdoe', 1),
                                           ('microfone', 'micrfne', 2), ('code', 'cxxe', None),
                                           ('microfone', 'mcxfne', None)]:
            self.assertEqual(word_distance(term, candidate), expected)
        for query in ('zzzxq', 'pdf xyz', 'code; touch unsafe'):
            self.assertEqual(search_score(query, 'Code Editor'), 0)

    def test_files_share_tokens_accents_hyphens_and_typos(self):
        engine = FileSearchEngine('/unused')
        wanted = FileEntry('Relatório-financeiro.pdf', '/wanted', False, '', kind='document')
        other = FileEntry('Fotos.png', '/other', False, '')
        engine._publish([other, wanted])
        for query in ('relatorio financeiro', 'financeiro relatorio', 'relatotio',
                      'DOCUMENTOS: financeiro relatorio'):
            with self.subTest(query=query):
                self.assertEqual(engine.search(query)[0].path, '/wanted')
        self.assertEqual(engine.search('zzzxq'), [])
        self.assertEqual(search_score('C++', 'C'), 0)
        self.assertEqual(search_score('no shutdown', 'shutdown'), 0)
        self.assertEqual(engine.search('financeiro', 0), [])

    def test_sort_is_stable_and_app_wins_equal_file_match(self):
        local_app = MatchResult(app('Code'), search_score('code', 'Code'))
        file = FileEntry('Code', '/code', False, '', score=search_score('code', 'Code'))
        self.assertEqual(sorted([file, local_app], key=result_key), [local_app, file])
        engine = FileSearchEngine('/unused')
        entries = [FileEntry('Report', path, False, '') for path in ('/z', '/a')]
        engine._publish(entries)
        self.assertEqual(engine.search('report', 1)[0].path, '/a')

    def test_multilingual_intents_and_high_usage_stay_in_their_band(self):
        fixture = test_search.SearchTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        browser = app('Firefox', ['Web Browser'])
        editor = app('Code', ['Text Editor'])
        sound = app('Som', ['audio'])
        network = app('Wi-Fi', ['Network'])
        files = app('Nautilus', ['File Manager'])
        settings = app('Control Center', ['Settings'])
        apps = [browser, editor, sound, network, files, settings]
        for query, wanted in (
            ('navegar na internet', browser), ('browse the internet', browser),
            ('navegar por internet', browser), ('naviguer sur internet', browser),
            ('editar texto', editor), ('edit text', editor), ('editer du texte', editor),
            ('ajustar o audio', sound), ('change sound', sound), ('ajustar el sonido', sound),
            ('regler le son', sound), ('rede', network), ('reseau', network),
            ('arquivos', files), ('archivos', files), ('fichiers', files),
            ('configuracoes', settings), ('parametres', settings),
        ):
            with self.subTest(query=query):
                self.assertIs(fixture.matcher.search(query, apps)[0].entry, wanted)
        fuzzy, literal = app('Edtior'), app('Editor Pro')
        for _ in range(25):
            fixture.history.record_launch(fuzzy.id, 'editor')
        self.assertIs(fixture.matcher.search('editor', [fuzzy, literal])[0].entry, literal)

    def test_adjustment_intent_favors_relevant_settings_panel(self):
        fixture = test_search.SearchTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        sound = app('Sound', ['audio', 'volume'], setting=True)
        player = app('Audio Player', ['audio'])
        about = app('About', ['audio', 'system'], setting=True)
        for query in ('ajustar o audio', 'change sound', 'cambiar el sonido', 'regler le son'):
            with self.subTest(query=query):
                self.assertIs(fixture.matcher.search(query, [about, player, sound])[0].entry, sound)

    def test_indexes_all_available_supported_translations(self):
        with TemporaryDirectory() as folder:
            path = Path(folder, 'sample.desktop')
            path.write_text('[Desktop Entry]\nType=Application\nName=Sample\nExec=/bin/true\n'
                            'Name[pt_BR]=Exemplo\nName[es]=Ejemplo\nName[fr]=Exemple\n'
                            'GenericName[en]=Text Editor\nKeywords[fr]=ecrire;texte;\n'
                            'Keywords[de]=schreiben;\n')
            desktop = Gio.DesktopAppInfo.new_from_filename(str(path))
            indexer = AppIndexer.__new__(AppIndexer)
            with patch('src.indexer.Gio.AppInfo.get_all', return_value=[desktop]):
                indexer.reload()
            entry, = indexer.get_apps()
            self.assertEqual(entry.name, desktop.get_name())
            for word in ('exemplo', 'ejemplo', 'exemple', 'text editor', 'ecrire'):
                self.assertGreater(search_score(word, entry.search_name, entry.search_metadata), 0)
            self.assertNotIn('schreiben', entry.search_metadata)

    def test_command_arguments_stay_unchanged(self):
        for query, expected in (
            ('map of São Paulo & café #1?', 'mapa São Paulo & café #1?'),
            ('traduisez EN:PT: Good morning & café\nWorld', 'traduza EN:PT: Good morning & café\nWorld'),
            ('convertir -40 °C en °F', '-40 °C en °F'),
            ('prévision du temps à Paris', 'clima em Paris'),
            ('> echo "mapa Paris"', None),
            ('mapas.com', None), ('website', None),
            ('defina ação & reação?', 'defina ação & reação?'),
            ('open calendar', 'calendar'), ('ouvrir le calendrier', 'calendar'),
        ):
            with self.subTest(query=query):
                self.assertEqual(command_query(query), expected)
        for query in ('hora em Roma', 'weather in London', 'que hora es en Madrid', 'heure à Paris'):
            self.assertTrue(ToolsEngine.supports_query(query))

    def test_dictionary_and_translation_questions_in_four_languages(self):
        for query, expected, language in (
            ('O que significa saudade?', 'saudade', 'pt'),
            ('What does brain mean?', 'brain', 'en'),
            ('¿Qué significa corazón?', 'corazón', 'es'),
            ('Que veut dire cœur ?', 'cœur', 'fr'),
            ('définir cerveau', 'cerveau', 'fr'), ('dicionario cerebro', 'cerebro', 'pt'),
        ):
            word, url = dictionary_search(query)
            self.assertEqual(word, expected)
            self.assertEqual(urlsplit(url).netloc, language + '.wiktionary.org')
        for query, text in (
            ('como se diz Bom dia em ingles?', 'Bom dia'),
            ('how do you say Good morning in French?', 'Good morning'),
            ('¿Cómo se dice Buenos días en inglés?', 'Buenos días'),
            ('Comment dit-on Bonjour en anglais ?', 'Bonjour'),
        ):
            self.assertEqual(translation_search(query)[0], text)
        self.assertEqual(map_destination('carte de Paris & café'), 'Paris & café')

    def test_fuzzy_commands_are_suggestions_and_do_not_run_tools(self):
        for query, corrected in (
            ('calendrio', 'calendar'), ('clmia em São Paulo', 'clima em São Paulo'),
            ('traduzza en: Bom dia & café', 'traduza en: Bom dia & café'),
            ('mapaa São Paulo', 'mapa São Paulo'),
            ('documntos: Relatório-Final.pdf', 'documentos: Relatório-Final.pdf'),
            ('fotoss', 'fotos'),
            ('restatr spot', 'reiniciar spotlauncher'),
            ('femer spot', 'fechar spotlauncher'),
        ):
            with self.subTest(query=query):
                self.assertIsNone(command_query(query))
                self.assertEqual(command_suggestion(query).query, corrected)
                window = Mock()
                window.calculator.evaluate.return_value = None
                window.tools.supports_query = ToolsEngine.supports_query
                LauncherWindow._do_search(window, query)
                window._schedule_search.assert_not_called()
                window._search_local.assert_called_once()
        for query in ('cal', 'zzzxq', 'Firefox', '> calendrio', 'mapa Paris'):
            self.assertIsNone(command_suggestion(query))
        window = SimpleNamespace(search_entry=Mock())
        row = SimpleNamespace(get_activatable=lambda: True, _search_query='calendar')
        LauncherWindow._on_row_activated(window, None, row)
        window.search_entry.set_text.assert_called_once_with('calendar')

    def test_actions_accept_typos_without_executing_and_keep_confirmation(self):
        with patch('src.system_actions.shutil.which', return_value='/bin/true'), \
             patch('src.system_actions.Gio.Subprocess.new') as spawn:
            for query in ('reinicair', 'restatr', 'redemarrer', 'apagar', 'eteindre'):
                with self.subTest(query=query):
                    actions = system_actions(query)
                    self.assertTrue(actions)
                    self.assertTrue(actions[0].confirm)
            for query in ('zzzxq', 'desligar; touch /tmp/unsafe'):
                self.assertEqual(system_actions(query), [])
            spawn.assert_not_called()

    def test_render_combines_settings_actions_apps_files_and_web(self):
        local_app = MatchResult(app('Code'), 5000)
        file = FileEntry('Code Report', '/code', False, '', score=4090)
        suggestion = command_suggestion('calendrio')
        window = SimpleNamespace(_clear_results=Mock(), _show_notice=Mock(),
                                 _match_row=lambda item: item, _append_page=Mock(),
                                 _web_row=lambda result: 'web', _map_rows=lambda query: ['maps'],
                                 scrolled_window=Mock(), list_box=Mock(), _result_count=1)
        with patch('src.window.Adw.ActionRow', side_effect=lambda **kwargs: SimpleNamespace(**kwargs, add_prefix=Mock())), \
             patch('src.window.Gtk.Image.new_from_icon_name'):
            LauncherWindow._render_matches(window, [local_app], [file], 2090,
                                           web_search('code'), actions=[suggestion])
            rows = list(window._remaining_rows)
        self.assertIs(rows[0], local_app)
        self.assertIs(rows[1], file)
        self.assertTrue(rows[2]._settings)
        self.assertEqual(rows[3]._search_query, 'calendar')
        self.assertEqual(rows[-2:], ['web', 'maps'])

    def test_query_acceptance_is_independent_of_interface_language(self):
        for language in ('pt', 'en', 'es', 'fr'):
            catalog = gettext.translation(APP_ID, LOCALE_DIR, languages=[language], fallback=True)
            with patch('src.window._', catalog.gettext), patch('src.LANGUAGE', language):
                window = Mock()
                LauncherWindow._do_search(window, 'ouvrir le calendrier')
                window._search_local.assert_not_called()
                self.assertTrue(ToolsEngine.supports_query('¿Qué hora es en Madrid?'))
                self.assertEqual(dictionary_search('Que signifie cœur?')[0], 'cœur')
