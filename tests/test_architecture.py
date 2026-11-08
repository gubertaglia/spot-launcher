import gettext
import json
import locale
from pathlib import Path
from queue import Queue
from tempfile import TemporaryDirectory
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import time

from src.calculator import CalculatorPlugin
from src.files import FileSearchEngine
from src.storage import write_json
from src.tools import ToolsEngine
from src.worker import LatestRequestWorker


class ToolsTests(unittest.TestCase):
    def setUp(self):
        # These expectations exercise the Portuguese source messages on every desktop.
        portuguese = patch("src.tools._", gettext.NullTranslations().gettext)
        portuguese.start()
        self.addCleanup(portuguese.stop)
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.cache = patch("src.tools.GLib.get_user_cache_dir", return_value=self.directory.name)
        self.cache.start()
        self.addCleanup(self.cache.stop)

    def engine(self):
        return ToolsEngine()

    def rates(self, engine, timestamp):
        write_json(engine.rates_file, {"fetched_at": timestamp, "rates": {"USD": 1, "BRL": 5}})

    def test_constructor_never_calls_network_or_loads_pint(self):
        with patch("urllib.request.urlopen", side_effect=AssertionError("rede no startup")):
            engine = self.engine()
        self.assertFalse(engine._pint_loaded)
        self.assertEqual(engine._rates, {})

    def test_reopening_with_same_clipboard_does_not_rewrite_history(self):
        engine = self.engine()
        engine.record_clipboard("copiado")
        with patch("src.tools.write_json") as write:
            engine.record_clipboard("copiado")
            write.assert_not_called()
        self.assertEqual(engine.get_clipboard_history(), ["copiado"])

    def test_clipboard_change_reads_and_ignores_outdated_results(self):
        from src.window import LauncherWindow
        engine = self.engine()
        window = SimpleNamespace(_clipboard_generation=0, tools=engine)
        window._on_clipboard_read = lambda *args: LauncherWindow._on_clipboard_read(window, *args)
        clipboard = Mock()
        LauncherWindow._on_clipboard_changed(window, clipboard)
        LauncherWindow._on_clipboard_changed(window, clipboard)
        clipboard.read_text_finish.return_value = "antigo"
        window._on_clipboard_read(clipboard, object(), 1)
        clipboard.read_text_finish.return_value = "novo"
        window._on_clipboard_read(clipboard, object(), 2)
        from src.storage import flush_writes
        flush_writes()
        self.assertEqual(engine.get_clipboard_history(), ["novo"])

    def test_timezone_cache_works_offline(self):
        engine = self.engine()
        engine._geo_cache["sao paulo"] = {"tz": "America/Sao_Paulo", "display": "São Paulo"}
        with patch("urllib.request.urlopen", side_effect=AssertionError("rede para cache")):
            result = engine.search("hora em São Paulo")
        self.assertIn("São Paulo", result["title"])
        self.assertRegex(result["copy"], r"^\d{2}:\d{2}$")

    def test_weather_query_and_cached_result(self):
        engine = self.engine()
        engine._geo_cache["sao paulo"] = {
            "tz": "America/Sao_Paulo", "display": "São Paulo (Brasil)",
            "latitude": -23.55, "longitude": -46.63,
        }
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = json.dumps({"current": {
            "temperature_2m": 23.5, "apparent_temperature": 25,
            "relative_humidity_2m": 70, "weather_code": 3,
            "is_day": 1, "wind_speed_10m": 12, "time": "2026-11-07T14:00",
        }}).encode()
        self.assertTrue(engine.supports_query("Clima em São Paulo"))
        with patch("urllib.request.urlopen", return_value=response) as network:
            result = engine.search("Clima em São Paulo")
            self.assertEqual(engine.search("clima em São Paulo"), result)
        network.assert_called_once()
        self.assertIn(locale.format_string("%g", 23.5) + " °C", result["title"])
        self.assertIn("Nublado", result["title"])
        self.assertIn("Sensação: 25 °C", result["sub"])
        self.assertIn("Open-Meteo", result["sub"])
        self.assertEqual(result["copy"], result["title"])

    def test_weather_upgrades_old_geocache_and_reports_network_failure(self):
        engine = self.engine()
        engine._geo_cache["paris"] = {"tz": "Europe/Paris", "display": "Paris"}
        with patch.object(engine, "_fetch_geocoding", return_value=None) as geocode:
            result = engine.search("Clima em Paris")
            engine.search("Clima em Paris")
        geocode.assert_called_once_with("paris")
        self.assertIsNone(result["copy"])
        self.assertIn("indisponível", result["title"])

    def test_weather_stale_cache_is_marked_when_refresh_fails(self):
        engine = self.engine()
        engine._weather_cache["paris"] = (time.monotonic() - 700, {
            "title": "20 °C em Paris", "sub": "Open-Meteo", "copy": "20 °C", "icon": "weather-clear-symbolic",
        })
        with patch("urllib.request.urlopen", side_effect=OSError("offline")):
            result = engine.search("clima em Paris")
        self.assertIn("Desatualizado", result["sub"])
        self.assertEqual(result["title"], "20 °C em Paris")

    def test_weather_does_not_capture_other_queries(self):
        engine = self.engine()
        for query in ("clima", "clima em", "clima em a", "g clima em Paris", "hora em Paris"):
            self.assertIsNone(engine.check_weather(query))

    def test_timezone_network_failure_has_no_copyable_result(self):
        engine = self.engine()
        with patch("urllib.request.urlopen", side_effect=OSError("offline")):
            result = engine.search("hora em lisboa")
        self.assertIsNone(result["copy"])
        self.assertIn("indisponível", result["title"])

    def test_fresh_cache_avoids_network(self):
        engine = self.engine()
        self.rates(engine, time.time())
        engine = self.engine()
        with patch("urllib.request.urlopen") as network:
            result = engine.convert_currency("10 usd para brl")
        network.assert_not_called()
        self.assertEqual(result["copy"], "50.00")
        self.assertNotIn("desatualizada", result["sub"])

    def test_stale_cache_survives_failure_and_retry_is_limited(self):
        engine = self.engine()
        self.rates(engine, time.time() - 7200)
        engine = self.engine()
        with patch("urllib.request.urlopen", side_effect=OSError("offline")) as network:
            result = engine.convert_currency("10 usd para brl")
            engine.convert_currency("11 usd para brl")
        self.assertEqual(network.call_count, 1)
        self.assertIn("desatualizada", result["sub"])
        self.assertEqual(result["copy"], "50.00")

    def test_offline_has_no_fabricated_rates(self):
        engine = self.engine()
        with patch("urllib.request.urlopen", side_effect=OSError("offline")):
            result = engine.convert_currency("10 dolar para real")
        self.assertIsNone(result["copy"])
        self.assertEqual(engine._rates, {})

    def test_successful_refresh_is_persisted_with_timestamp(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b'{"data":{"rates":{"USD":"1","BRL":"6"}}}'
        engine = self.engine()
        with patch("urllib.request.urlopen", return_value=response):
            result = engine.convert_currency("10 usd para brl")
        self.assertEqual(result["copy"], "60.00")
        cache = json.loads(Path(engine.rates_file).read_text())
        self.assertGreater(cache["fetched_at"], 0)
        self.assertEqual(cache["rates"]["BRL"], 6)

    def test_legacy_cache_is_stale_and_invalid_rates_are_rejected(self):
        engine = self.engine()
        write_json(engine.rates_file, {"USD": 1, "BRL": 5})
        self.assertEqual(self.engine()._rates_timestamp, 0)
        for value in (0, -1, "nan", "inf"):
            with self.assertRaises(ValueError):
                ToolsEngine._validated_rates({"USD": value})

    def test_units_run_without_network_and_preserve_symbols(self):
        engine = self.engine()
        with patch("urllib.request.urlopen", side_effect=AssertionError("rede para unidade")):
            self.assertEqual(engine.search("10 km para m")["copy"], "10000.0")
            self.assertAlmostEqual(float(engine.search("0 celsius para fahrenheit")["copy"]), 32)
            self.assertEqual(float(engine.search("10 ms para s")["copy"]), 0.01)

    def test_temperature_scales_signs_and_aliases_work_offline(self):
        engine = self.engine()
        cases = (
            ("-40 C para F", -40), ("-40 °F para °C", -40),
            ("273,15 K para C", 0), ("0 celsius para kelvin", 273.15),
            ("32 fahrenheit to K", 273.15), ("273.15 kelvin in F", 32),
            ("100 degC para degF", 212), ("+36,5 ℃ para ℉", 97.7),
            (".5 c para f", 32.9), ("0 K para K", 0),
            ("-273.15 C para K", 0), ("-459.67 F para K", 0),
        )
        with patch("urllib.request.urlopen", side_effect=AssertionError("rede para temperatura")):
            for query, expected in cases:
                with self.subTest(query=query):
                    self.assertTrue(engine.supports_query(query))
                    self.assertAlmostEqual(float(engine.search(query)["copy"]), expected)
        registry = engine._ureg
        engine.search("0 C para F")
        self.assertIs(engine._ureg, registry)

    def test_invalid_temperature_queries_never_fetch_currency_rates(self):
        engine = self.engine()
        with patch("urllib.request.urlopen", side_effect=AssertionError("rede para temperatura")) as network:
            for query in ("20 C para m", "20 kelvin para desconhecida",
                          "1.2.3 C para F", "--10 C para F", "1,2.3 C para F",
                          "9" * 400 + " C para F"):
                with self.subTest(query=query):
                    self.assertIsNone(engine.search(query))
        network.assert_not_called()

    def test_unit_conversion_rejects_nonfinite_output(self):
        engine = self.engine()
        converted = Mock(magnitude=float("inf"))
        registry = Mock()
        registry.Quantity.return_value.to.return_value = converted
        with patch.object(engine, "_unit_registry", return_value=registry):
            self.assertIsNone(engine.convert_units("10 C para F"))


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.dispatched = Queue()
        self.worker = LatestRequestWorker(lambda *args: self.dispatched.put(args))
        self.addCleanup(lambda: self.worker._thread.is_alive() and self.worker._thread.join(1))
        self.addCleanup(self.worker.close)

    def deliver(self):
        callback, *args = self.dispatched.get(timeout=2)
        callback(*args)

    def test_worker_runs_off_main_thread(self):
        self.assertIsNone(self.worker._thread.ident)
        results = []
        self.worker.submit(threading.get_ident, results.append)
        self.deliver()
        self.assertNotEqual(results[0], threading.get_ident())

    def test_invalidation_also_discards_already_dispatched_results(self):
        results = []
        self.worker.submit(lambda: "antiga", results.append)
        args = self.dispatched.get(timeout=2)
        self.worker.invalidate()
        args[0](*args[1:])
        self.assertEqual(results, [])

    def test_slow_request_does_not_build_queue_of_obsolete_queries(self):
        started, release = threading.Event(), threading.Event()
        results, executed = [], []

        def slow():
            started.set()
            release.wait(2)
            return "antiga"

        self.worker.submit(slow, results.append)
        self.assertTrue(started.wait(1))
        self.worker.submit(lambda: executed.append("descartada"), results.append)
        self.worker.submit(lambda: "nova", results.append)
        release.set()
        self.deliver()
        self.deliver()
        self.assertEqual(executed, [])
        self.assertEqual(results, ["nova"])

    def test_close_prevents_delivery(self):
        results = []
        self.worker.submit(lambda: "resultado", results.append)
        args = self.dispatched.get(timeout=2)
        self.worker.close()
        args[0](*args[1:])
        self.assertEqual(results, [])

    def test_glib_stays_responsive_and_delivers_on_main_thread(self):
        from gi.repository import GLib
        loop = GLib.MainLoop()
        release = threading.Event()
        results = []
        worker = LatestRequestWorker(GLib.idle_add)
        main_thread = threading.get_ident()

        def task():
            release.wait(1)
            return threading.get_ident()

        def delivered(result):
            results.append((result, threading.get_ident()))
            loop.quit()

        def tick():
            release.set()
            return False

        worker.submit(task, delivered)
        GLib.timeout_add(10, tick)
        watchdog = GLib.timeout_add(2000, lambda: loop.quit() or False)
        try:
            loop.run()
        finally:
            worker.close()
            worker._thread.join(1)
            if results:
                GLib.source_remove(watchdog)
        self.assertEqual(len(results), 1)
        self.assertNotEqual(results[0][0], main_thread)
        self.assertEqual(results[0][1], main_thread)


class FileIndexTests(unittest.TestCase):
    def test_limit_refresh_and_previous_snapshot_remain_consistent(self):
        with TemporaryDirectory() as directory:
            for i in range(20):
                Path(directory, f"arquivo-{i}").touch()
            engine = FileSearchEngine(directory)
            engine.MAX_FILES = 7
            engine._publish(engine._scan())
            old = engine._indexed_files
            self.assertEqual(len(old), 7)
            self.assertEqual(len(engine.search("arquivo", limit=20)), 7)
            for child in Path(directory).iterdir():
                child.unlink()
            Path(directory, "novo-arquivo").touch()
            engine._publish(engine._scan())
            self.assertEqual(len(old), 7)
            self.assertEqual([r.name for r in engine.search("novo")], ["novo-arquivo"])

    def test_refresh_reuses_files_but_reclassifies_replaced_paths(self):
        with TemporaryDirectory() as directory:
            path = Path(directory, "photo.jpg")
            path.touch()
            engine = FileSearchEngine(directory, refresh_seconds=0)
            first, = engine.search_current("photos", 1)
            unchanged, = engine.search_current("photos", 1)
            self.assertIs(first, unchanged)
            path.unlink()
            path.mkdir()
            self.assertEqual(engine.search_current("photos", 1), [])
            self.assertEqual(engine.search("photo.jpg")[0].kind, "folder")

    def test_excluded_directories_and_symlink_cycles_are_not_traversed(self):
        with TemporaryDirectory() as directory:
            for folder in (".private", "node_modules", "Documents"):
                Path(directory, folder).mkdir()
                Path(directory, folder, "conteudo.txt").touch()
            Path(directory, "Documents", "loop").symlink_to(directory, target_is_directory=True)
            engine = FileSearchEngine(directory)
            names = [entry.path for entry in engine._scan()]
            self.assertEqual(sum(path.endswith("conteudo.txt") for path in names), 1)


class StorageAndCalculatorTests(unittest.TestCase):
    def test_autostart_uses_current_interpreter_and_absolute_entrypoint(self):
        import sys
        from gi.repository import GLib
        from src.preferences import autostart_entry
        entry = GLib.KeyFile()
        data = autostart_entry()
        entry.load_from_data(data, len(data.encode("utf-8")), GLib.KeyFileFlags.NONE)
        success, arguments = GLib.shell_parse_argv(entry.get_string("Desktop Entry", "Exec"))
        self.assertTrue(success)
        self.assertEqual(arguments[0], sys.executable)
        self.assertTrue(Path(arguments[1]).is_absolute())
        self.assertTrue(Path(arguments[1]).is_file())
        self.assertEqual(arguments[2], "--daemon")

    def test_failed_replace_keeps_existing_json_and_removes_temporary_file(self):
        with TemporaryDirectory() as directory:
            path = Path(directory, "history.json")
            write_json(path, {"app": 1})
            with patch("src.storage.os.replace", side_effect=OSError("falha")):
                with self.assertRaises(OSError):
                    write_json(path, {"app": 2})
            self.assertEqual(json.loads(path.read_text()), {"app": 1})
            self.assertEqual(list(Path(directory).iterdir()), [path])
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_calculator_preserves_basic_operations_and_bounds_work(self):
        calc = CalculatorPlugin()
        for query, expected in (("2+3*4", "14"), ("2^8", "256"),
                                ("sqrt(9)", "3"), ("1,5+2", "3.5"), ("-4+1", "-3")):
            self.assertEqual(calc.evaluate(query), expected)
        for query in ("9^9^9", "2**10000000", "1/0", "sin.__call__(2)", "1+" * 200):
            self.assertIsNone(calc.evaluate(query))


class WindowFlowTests(unittest.TestCase):
    def test_hide_cancels_timeout_and_invalidates_results(self):
        from src.window import LauncherWindow
        window = SimpleNamespace(scaled_content=Mock(), _fade_to=Mock(), loading_spinner=Mock(), loading_status=Mock(), _search_timeout_id=42, _tools_worker=Mock(), _file_worker=Mock(), _clear_results=Mock(), set_visible=Mock())
        window._cancel_pending_search = lambda: LauncherWindow._cancel_pending_search(window)
        with patch("src.window.GLib.source_remove") as remove:
            LauncherWindow.hide_launcher(window)
        remove.assert_called_once_with(42)
        self.assertEqual(window._search_timeout_id, 0)
        window._tools_worker.invalidate.assert_called_once()
        window._file_worker.invalidate.assert_called_once()
        window._fade_to.assert_called_once_with(0)
        window.set_visible.assert_not_called()

    def test_scrolling_builds_one_page_and_keeps_distant_shortcuts(self):
        from src.window import LauncherWindow, Gdk
        window = SimpleNamespace(_context_open=False, calendar_panel=Mock(),
                                 _result_count=0, _remaining_rows=iter(range(80)),
                                 config={"max_results": 7, "scroll_results": True},
                                 list_box=Mock(), _on_row_activated=Mock())
        rows = []
        def append(row):
            rows.append(row)
            window._result_count += 1
        window._append_result = append
        window._append_page = lambda: LauncherWindow._append_page(window)
        window.list_box.get_row_at_index.side_effect = rows.__getitem__
        window.calendar_panel.get_visible.return_value = False
        window._append_page()
        self.assertEqual(rows, list(range(8)))
        LauncherWindow._on_key_pressed(window, None, Gdk.KEY_z, 0, Gdk.ModifierType.ALT_MASK)
        window._on_row_activated.assert_called_once_with(window.list_box, 35)
        self.assertEqual(len(rows), 40)

    def test_tool_loading_wraps_debounced_query(self):
        from src.window import LauncherWindow
        window = SimpleNamespace(
            _clear_results=Mock(), calendar_panel=Mock(), scrolled_window=Mock(),
            loading_spinner=Mock(), loading_status=Mock(), loading_label=Mock(),
            tools=Mock(), _tools_worker=Mock(), _show_tool_result=Mock(),
        )
        window._schedule_search = lambda *args: LauncherWindow._schedule_search(window, *args)
        with patch("src.window.GLib.timeout_add", return_value=42) as timer:
            LauncherWindow._do_search(window, "10 km para m")
        window.loading_status.set_visible.assert_called_once_with(True)
        window.loading_spinner.start.assert_called_once()
        window.tools.search.assert_not_called()
        window._tools_worker.submit.assert_not_called()
        self.assertEqual(window._search_timeout_id, 42)
        timer.call_args.args[1]()
        task, deliver = window._tools_worker.submit.call_args.args
        task()
        window.tools.search.assert_called_once_with("10 km para m")
        deliver({"title": "resultado"})
        window.loading_status.set_visible.assert_called_with(False)
        window.loading_spinner.stop.assert_called_once()
        window._show_tool_result.assert_called_once_with({"title": "resultado"})


if __name__ == "__main__":
    unittest.main()
