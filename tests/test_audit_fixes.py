"""Regression checks for the technical audit findings."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from src.preferences import ConfigManager
from src.storage import flush_writes, write_json_ui
from src.tools import ToolsEngine
from src.window import LauncherWindow
from src.worker import LatestRequestWorker
from src.dictionary import lookup


class AuditFixTests(unittest.TestCase):
    def test_config_rejects_invalid_values_and_preserves_position(self):
        with TemporaryDirectory() as directory:
            path = Path(directory)/'config.json'
            with patch('src.preferences.CONFIG_FILE', str(path)):
                for value in ('7', None, [], -1, 1.5, True):
                    path.write_text(json.dumps({'max_results': value, 'window_position': [20, 30]}))
                    config = ConfigManager()
                    self.assertEqual(config.get('max_results'), 7)
                    self.assertEqual(config.get('window_position'), [20, 30])

    def test_currency_copy_and_overflow(self):
        with TemporaryDirectory() as directory, patch('src.tools.GLib.get_user_cache_dir', return_value=directory):
            engine = ToolsEngine()
            engine._rates = {'USD': 1, 'BTC': .000014, 'BRL': 5}
            engine._rates_timestamp = time.time()
            self.assertEqual(engine.convert_currency('1 USD em BTC')['copy'], '0.000014')
            self.assertIsNone(engine.convert_currency('1'+'0'*308+' USD em BRL')['copy'])

    def test_case_sensitive_units(self):
        with TemporaryDirectory() as directory, patch('src.tools.GLib.get_user_cache_dir', return_value=directory):
            engine = ToolsEngine()
            for query, expected in [('1 Mm em m', 1000000), ('1 mm em m', .001), ('1 MW em W', 1000000)]:
                self.assertEqual(float(engine.convert_units(query)['copy']), expected)

    def test_sensitive_clipboard_invalidates_without_reading(self):
        clipboard = Mock()
        clipboard.get_formats.return_value.contain_mime_type.return_value = True
        window = SimpleNamespace(_clipboard_generation=2)
        LauncherWindow._on_clipboard_changed(window, clipboard)
        self.assertEqual(window._clipboard_generation, 3)
        clipboard.read_text_async.assert_not_called()

    def test_failed_file_launch_preserves_window(self):
        window = SimpleNamespace(_tool_copy_val=None, files=Mock(), hide_launcher=Mock(), _launch_failed=Mock())
        window.files.open_item.return_value = False
        row = SimpleNamespace(get_activatable=lambda: True, _file_entry=SimpleNamespace(path='/missing'))
        LauncherWindow._on_row_activated(window, None, row)
        window.hide_launcher.assert_not_called()
        window._launch_failed.assert_called_once()

    def test_background_writes_snapshot_and_drain(self):
        entered, release = threading.Event(), threading.Event()
        calls = []
        threads = []
        def slow_write(path, value):
            threads.append(threading.get_ident())
            entered.set()
            release.wait(2)
            calls.append(value)
        with patch('gi.repository.GLib.main_depth', return_value=1), patch('src.storage.write_json', side_effect=slow_write):
            value = {'value': 1}
            write_json_ui('/unused', value)
            self.assertTrue(entered.wait(2))
            value['value'] = 2
            write_json_ui('/unused', value)
            self.assertEqual(calls, [])
            release.set()
            flush_writes()
        self.assertEqual(calls, [{'value': 1}, {'value': 2}])
        self.assertTrue(all(identity != threading.get_ident() for identity in threads))

    def test_obsolete_dictionary_stops_before_next_fetch(self):
        import io
        entered, release, done = threading.Event(), threading.Event(), threading.Event()
        worker = LatestRequestWorker(lambda function, *args: function(*args))
        old_callback = Mock()
        def fetch(*args, **kwargs):
            entered.set()
            release.wait(2)
            return io.BytesIO(b'{"error":{"code":"missingtitle"}}')
        try:
            with patch('src.dictionary.urlopen', side_effect=fetch) as network:
                worker.submit(lambda: lookup('Synthetic', 'https://en.wiktionary.org/wiki/Synthetic'), old_callback)
                self.assertTrue(entered.wait(2))
                worker.invalidate()
                worker.submit(lambda: None, lambda result: done.set())
                release.set()
                self.assertTrue(done.wait(2))
                self.assertEqual(network.call_count, 1)
                old_callback.assert_not_called()
        finally:
            release.set()
            worker.close()
            worker._thread.join(2)

    def test_terminal_honors_desktop_working_directory(self):
        from gi.repository import Gio
        from src.indexer import AppIndexer, AppEntry
        import time
        with TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / 'cwd'
            terminal = root / 'terminal'
            terminal.write_text('#!/bin/sh\npwd > "' + str(output) + '"\n')
            terminal.chmod(0o700)
            cwd = root / 'working directory'
            cwd.mkdir()
            desktop = root / 'audit.desktop'
            desktop.write_text(f'[Desktop Entry]\nType=Application\nName=Audit\nExec=/bin/true\nTerminal=true\nPath={cwd}\n')
            info = Gio.DesktopAppInfo.new_from_filename(str(desktop))
            entry = AppEntry('audit.desktop', 'Audit', '', '', True, info)
            with patch('src.indexer.get_default_terminal', return_value=[str(terminal)]):
                self.assertTrue(AppIndexer.__new__(AppIndexer).launch(entry))
            deadline = time.monotonic() + 3
            while not output.exists() and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertEqual(output.read_text().strip(), str(cwd))
