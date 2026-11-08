import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

from src.translation import translate
from src.web import dictionary_search, translation_search
from src.window import LauncherWindow


class TranslationTests(unittest.TestCase):
    def setUp(self):
        translate.cache_clear()
        self.addCleanup(translate.cache_clear)

    def response(self, data):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = json.dumps(data).encode()
        return response

    def test_commands_keep_text_and_use_explicit_or_interface_source(self):
        with patch('src.LANGUAGE', 'pt'):
            for query, expected in (
                ('traduza en: bom dia', ('bom dia', 'pt', 'en')),
                ('traduza bom dia para inglês', ('bom dia', 'pt', 'en')),
                ('translate olá to English', ('olá', 'pt', 'en')),
                ('traduz inglês:português: Good morning', ('Good morning', 'en', 'pt')),
                ('traduza para casa para francês', ('para casa', 'pt', 'fr')),
                ('traduza olá\n mundo para espanhol', ('olá\n mundo', 'pt', 'es')),
                ('TRANSLATE EN:PT: Good morning & café', ('Good morning & café', 'en', 'pt')),
                ('traduire fr: bonjour\nmonde', ('bonjour\nmonde', 'pt', 'fr')),
            ):
                self.assertEqual(translation_search(query), expected)
        for query in ('traduza', 'translate en:', 'traduza xx: oi', 'translate en:pt: ', 'Firefox', 'traduza para inglês'):
            self.assertIsNone(translation_search(query), query)

    def test_natural_translation_queries_and_other_languages(self):
        with patch('src.LANGUAGE', 'pt'):
            for query, expected in (
                ('bom dia em ingles', ('bom dia', 'pt', 'en')),
                ('traduza mesa para russo', ('mesa', 'pt', 'ru')),
                ('como se diz mesa em russo?', ('mesa', 'pt', 'ru')),
                ('como se diz mesa em russo', ('mesa', 'pt', 'ru')),
                ('how do you say good morning in Japanese?', ('good morning', 'pt', 'ja')),
                ('traduza para alemão: bom dia', ('bom dia', 'pt', 'de')),
                ('traduza mesa de português para russo', ('mesa', 'pt', 'ru')),
                ('translate ru:pt: стол', ('стол', 'ru', 'pt')),
                ('traduza café para chinês', ('café', 'pt', 'zh')),
                ('traduire bonjour en arabe', ('bonjour', 'pt', 'ar')),
                ('traducir hola en coreano', ('hola', 'pt', 'ko')),
                ('traduza olá para alemão', ('olá', 'pt', 'de')),
            ):
                with self.subTest(query=query):
                    self.assertEqual(translation_search(query), expected)
        for query in ('arquivo em downloads', 'viajar para Roma', 'música em',
                      'traduza ru:pt: ', 'traduza para russo:', 'Firefox'):
            self.assertIsNone(translation_search(query), query)

    def test_every_recognized_language_reaches_service(self):
        from src.translation import LANGUAGE_ALIASES
        data = {'responseStatus': 200, 'responseData': {'translatedText': 'result'}}
        with patch('src.LANGUAGE', 'pt'), patch('src.translation.urlopen', return_value=self.response(data)):
            for alias, code in LANGUAGE_ALIASES.items():
                with self.subTest(alias=alias):
                    self.assertEqual(translation_search('traduza teste para ' + alias), ('teste', 'pt', code))
                    self.assertTrue(translate('teste', 'pt', code))

    def test_screenshot_queries_schedule_translation_instead_of_local_search(self):
        for query, expected in (('bom dia em ingles', ('bom dia', 'pt', 'en')),
                                ('traduza mesa para russo', ('mesa', 'pt', 'ru'))):
            window = Mock()
            with patch('src.LANGUAGE', 'pt'), patch('src.window.translate', return_value='result') as network:
                LauncherWindow._do_search(window, query)
                _, task, callback, _, _ = window._schedule_search.call_args.args
                callback(task())
                network.assert_called_once_with(*expected)
            window._search_local.assert_not_called()

    def test_natural_dictionary_questions_choose_the_question_language(self):
        with patch('src.LANGUAGE', 'fr'):
            for query, word, language in (
                ('O que significa saudade?', 'saudade', 'pt'),
                ('qual é o significado de casa?', 'casa', 'pt'),
                ('significado de paz', 'paz', 'pt'),
                ('What does brain mean?', 'brain', 'en'),
            ):
                result = dictionary_search(query)
                self.assertEqual(result[0], word)
                self.assertEqual(urlsplit(result[1]).netloc, language + '.wiktionary.org')

    def test_translation_encodes_text_decodes_entities_and_caches_success(self):
        data = {'responseStatus': 200, 'responseData': {'translatedText': 'Hello &amp; goodbye'}}
        with patch('src.translation.urlopen', return_value=self.response(data)) as network:
            self.assertEqual(translate('Olá & adeus', 'pt', 'en'), 'Hello & goodbye')
            self.assertEqual(translate('Olá & adeus', 'pt', 'en'), 'Hello & goodbye')
        network.assert_called_once()
        self.assertEqual(parse_qs(urlsplit(network.call_args.args[0].full_url).query),
                         {'q': ['Olá & adeus'], 'langpair': ['pt|en']})
        self.assertEqual(network.call_args.kwargs['timeout'], 5)

    def test_validation_checks_utf8_bytes_before_network(self):
        with patch('src.translation.urlopen') as network:
            for args in (('', 'pt', 'en'), ('é' * 251, 'pt', 'en'), ('hi', 'xx', 'en')):
                with self.assertRaises(ValueError):
                    translate(*args)
            self.assertEqual(translate('oi', 'pt', 'pt'), 'oi')
        network.assert_not_called()

    def test_errors_are_not_results_or_cached(self):
        for data in (None, [], {'responseStatus': 200, 'responseData': None},
                     {'responseStatus': 200, 'responseData': []},
                     {'responseStatus': 200, 'responseData': {'translatedText': '&nbsp;'}},
                     {'responseStatus': 429}, {'responseStatus': 200, 'quotaFinished': True},
                     {'responseStatus': 200, 'responseData': {'translatedText': ''}},
                     {'responseStatus': 200, 'responseData': {'translatedText': 42}}):
            with patch('src.translation.urlopen', return_value=self.response(data)) as network:
                for _ in range(2):
                    with self.assertRaises(ValueError):
                        translate('olá', 'pt', 'en')
                self.assertEqual(network.call_count, 2)
        with patch('src.translation.urlopen', side_effect=TimeoutError):
            with self.assertRaises(TimeoutError):
                translate('olá', 'pt', 'en')

    def test_search_schedules_translation_without_blocking_or_local_search(self):
        window = Mock()
        with patch('src.window.translate', return_value='hello') as network:
            LauncherWindow._do_search(window, 'traduza pt:en: olá')
            network.assert_not_called()
            worker, task, callback, label, delay = window._schedule_search.call_args.args
            self.assertIs(worker, window._tools_worker)
            self.assertEqual(delay, 400)
            callback(task())
            window._show_translation.assert_called_once_with(('olá', 'pt', 'en'), 'hello')
        window._search_local.assert_not_called()
        window.reset_mock()
        LauncherWindow._do_search(window, 'traduza en: ' + 'é' * 251)
        window._schedule_search.assert_not_called()
        window._show_notice.assert_called_once()

    def test_result_is_escaped_and_activates_existing_copy_path(self):
        window = Mock(_tool_copy_val=None)
        row = SimpleNamespace(get_activatable=lambda: True)
        with patch('src.window.Adw.ActionRow', return_value=row) as constructor:
            LauncherWindow._show_translation(window, ('olá', 'pt', 'en'), '<Hello> & goodbye')
        self.assertEqual(constructor.call_args.kwargs['title'], '&lt;Hello&gt; &amp; goodbye')
        self.assertEqual(row._clipboard_text, '<Hello> & goodbye')
        window.list_box.select_row.assert_called_once_with(row)
        with patch('src.window.Gdk.Display.get_default') as display:
            LauncherWindow._on_row_activated(window, None, row)
            display.return_value.get_clipboard.return_value.set.assert_called_once_with('<Hello> & goodbye')
        window.hide_launcher.assert_called_once()
        window.reset_mock()
        LauncherWindow._show_translation(window, ('olá', 'pt', 'en'), None)
        window._show_notice.assert_called_once()
        window._append_result.assert_not_called()

    def test_dictionary_missing_entry_retries_lowercase_then_labeled_suggestion(self):
        from src.dictionary import lookup
        replies = [self.response(data) for data in (
            {'error': {'code': 'missingtitle'}},
            {'error': {'code': 'missingtitle'}},
            {'query': {'searchinfo': {'suggestion': 'brain'}}},
            {'parse': {'text': '<ol><li>An organ.</li></ol>'}},
        )]
        with patch('src.dictionary.urlopen', side_effect=replies) as network:
            self.assertEqual(lookup('BRAINN', 'https://en.wiktionary.org/w/index.php'),
                             ['brain — An organ.'])
        queries = [parse_qs(urlsplit(call.args[0].full_url).query) for call in network.call_args_list]
        self.assertEqual(queries[1]['page'], ['brainn'])
        self.assertEqual(queries[2]['srinfo'], ['suggestion'])
        self.assertEqual(queries[3]['page'], ['brain'])

    def test_dictionary_missing_entry_without_suggestion_stays_empty(self):
        from src.dictionary import lookup
        replies = [self.response({'error': {'code': 'missingtitle'}}),
                   self.response({'query': {'searchinfo': {}, 'search': [{'title': 'Unrelated'}]}})]
        with patch('src.dictionary.urlopen', side_effect=replies):
            self.assertEqual(lookup('zzzxq', 'https://en.wiktionary.org/w/index.php'), [])
