import json
import unittest
from unittest.mock import Mock, patch
from src.dictionary import Definitions, lookup
from gi.repository import GLib
from src.system_actions import execute_action, system_actions


class DictionaryCaffeineTests(unittest.TestCase):
    def test_definitions_strip_markup_and_nested_examples(self):
        parser = Definitions()
        parser.feed('<ul><li>navigation</li></ul><ol><li>A <b>meaning</b>.<ul><li>example</li></ul></li><li>Another meaning.</li></ol>')
        self.assertEqual(parser.items, ['A meaning.', 'Another meaning.'])

    def test_styles_references_and_examples_never_become_definitions(self):
        parser = Definitions()
        parser.feed('<ol><li><style>.mw-parser-output{color:red}</style>'
                    '<script>bad()</script>A <b>definition</b><sup class="reference">[1]</sup>.'
                    '<dl><dd>A usage example</dd></dl><ul><li>Another example</li></ul></li></ol>'
                    '<ol class="references"><li>A source citation</li></ol>')
        self.assertEqual(parser.items, ['A definition.'])

    def test_spanish_numbered_definition_lists_exclude_etymology_and_examples(self):
        parser = Definitions()
        parser.feed('<dl><dd>Etymology</dd></dl>'
                    '<dl><dt>1 Anatomía</dt><dd>Una <b>definición</b>.</dd></dl>'
                    '<dl><dd><ul><li>Ejemplo</li></ul></dd></dl>'
                    '<dl><dt>2</dt><dd>Otra definición.</dd></dl>')
        self.assertEqual(parser.items, ['Una definición.', 'Otra definición.'])

    def test_dictionary_languages_do_not_depend_on_interface_language(self):
        from src.web import dictionary_search
        from urllib.parse import urlsplit
        cases = [('defina cérebro', 'pt', 'cérebro'), ('define brain', 'en', 'brain'),
                 ('diccionario cerebro', 'es', 'cerebro'), ('définir cerveau', 'fr', 'cerveau'),
                 ('defina en: brain', 'en', 'brain'), ('dict FR: cerveau', 'fr', 'cerveau')]
        with patch('src.LANGUAGE', 'pt'):
            for query, language, word in cases:
                with self.subTest(query=query):
                    result = dictionary_search(query)
                    self.assertEqual(result[0], word)
                    self.assertEqual(urlsplit(result[1]).netloc, language + '.wiktionary.org')
            self.assertIsNone(dictionary_search('defina en: '))
            self.assertEqual(urlsplit(dictionary_search('dict cérebro')[1]).netloc, 'pt.wiktionary.org')

    def test_lookup_encodes_word_and_handles_missing_entry(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        for data, expected in [({'parse': {'text': '<ol><li>Definition</li></ol>'}}, ['Definition']), ({'error': {}}, [])]:
            response.read.return_value = json.dumps(data).encode()
            with patch('src.dictionary.urlopen', return_value=response) as request:
                self.assertEqual(lookup('ação & paz', 'https://pt.wiktionary.org/w/index.php'), expected)
                self.assertIn('page=a%C3%A7%C3%A3o+%26+paz', request.call_args.args[0].full_url)
                self.assertEqual(request.call_args.kwargs['timeout'], 5)

    def test_caffeine_uses_installed_schema_and_does_not_toggle_during_search(self):
        for state in (False, True):
            settings = Mock()
            settings.get_boolean.return_value = state
            with patch('src.system_actions.Path.exists', return_value=True), \
                 patch('src.system_actions.Gio.SettingsSchemaSource.new_from_directory') as source, \
                 patch('src.system_actions.Gio.Settings.new_full', return_value=settings):
                source.return_value.lookup.return_value.has_key.side_effect = lambda key: key == 'cli-toggle'
                action, = system_actions('caffeine')
                self.assertEqual(action.command[-1], 'false' if state else 'true')
                self.assertIn('cli-toggle', action.command)
                settings.set_boolean.assert_not_called()
        with patch('src.system_actions.Path.exists', return_value=False):
            self.assertEqual(system_actions('caffeine'), [])

    def test_caffeine_lists_configured_durations_and_infinite(self):
        settings = Mock()
        settings.get_boolean.return_value = False
        settings.get_value.return_value = GLib.Variant('ai', [900, 1800, 3600])
        with patch('src.system_actions.Path.exists', return_value=True), \
             patch('src.system_actions.Gio.SettingsSchemaSource.new_from_directory') as source, \
             patch('src.system_actions.Gio.Settings.new_full', return_value=settings):
            schema = source.return_value.lookup.return_value
            schema.has_key.return_value = True
            actions = system_actions('caffeine')
        self.assertEqual([action.command[-1] for action in actions[1:]], ['0', '1', '2', '3'])

    def test_caffeine_timer_sets_duration_index(self):
        settings = Mock()
        settings.get_boolean.return_value = False
        with patch('src.system_actions.Path.exists', return_value=True), \
             patch('src.system_actions.Gio.SettingsSchemaSource.new_from_directory') as source, \
             patch('src.system_actions.Gio.Settings.new_full', return_value=settings):
            source.return_value.lookup.return_value.has_key.return_value = True
            settings.get_value.return_value = GLib.Variant('ai', [900, 1800, 3600])
            action = system_actions('caffeine')[-1]
            complete = Mock()
            execute_action(action, complete)
        settings.set_int.assert_called_once_with('duration-timer', 3)
        settings.set_boolean.assert_called_once_with('cli-toggle', True)
        complete.assert_called_once_with(None)
