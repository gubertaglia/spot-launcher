"""Reproduções da auditoria 1.8.0, sem alterar produto ou dados pessoais.

python3 -B docs/auditoria/reproducoes.py [arquivo.json]
Os testes de defeitos esperam o comportamento defeituoso da versão auditada.
Um teste aprovado significa reprodução bem-sucedida, NÃO defeito corrigido.
"""
import contextlib
import io
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
EVIDENCE = {}


class AuditReproductions(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="spot-audit-repro-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        from src import preferences
        self.config_file = self.root / "config.json"
        for target, value in (("src.preferences.CONFIG_FILE", str(self.config_file)),
                              ("src.tools.GLib.get_user_cache_dir", lambda: str(self.root)),
                              ("src.history.GLib.get_user_cache_dir", lambda: str(self.root))):
            p = patch(target, value)
            p.start()
            self.addCleanup(p.stop)
        p = patch("urllib.request.urlopen", side_effect=AssertionError("Rede não autorizada no teste"))
        p.start()
        self.addCleanup(p.stop)

    def test_config_wrong_types_reach_pagination(self):
        from src.preferences import ConfigManager
        from src.window import LauncherWindow
        observations = []
        for value in ("7", -2, 1.5, None, []):
            self.config_file.write_text(json.dumps({"max_results": value}))
            config = ConfigManager()
            window = SimpleNamespace(config=config, _remaining_rows=iter(()), _result_count=0)
            with self.assertRaises((TypeError, ValueError)) as error:
                LauncherWindow._append_page(window)
            observations.append({"value": value, "error": type(error.exception).__name__})
        EVIDENCE["config_types"] = observations

    def test_config_truncated_falls_back_and_scale_is_validated(self):
        from src.preferences import ConfigManager, launcher_scale
        self.config_file.write_text('{"max_results":')
        with contextlib.redirect_stdout(io.StringIO()):
            config = ConfigManager()
        self.assertEqual(config.get("max_results"), 7)
        self.assertEqual(launcher_scale({"scale": True}), 100)
        self.assertEqual(launcher_scale({"scale": 300}), 100)
        EVIDENCE["config_truncated_and_scale"] = "approved"

    def test_json_atomic_failure_permissions_and_symlink(self):
        from src.storage import write_json
        target = self.root / "history.json"
        write_json(target, ["old"])
        with patch("src.storage.os.replace", side_effect=OSError("synthetic disk full")):
            with self.assertRaises(OSError):
                write_json(target, ["new"])
        self.assertEqual(json.loads(target.read_text()), ["old"])
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        linked = self.root / "link.json"
        linked.symlink_to(target)
        write_json(linked, ["replacement"])
        self.assertFalse(linked.is_symlink())
        self.assertEqual(json.loads(target.read_text()), ["old"])
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ["history.json", "link.json"])
        EVIDENCE["storage"] = "atomic failure preserved old data; mode 0600; final symlink replaced"

    def test_clipboard_has_count_limit_but_no_byte_limit(self):
        from src.tools import ToolsEngine
        engine = ToolsEngine()
        payload = "synthetic-" + "x" * (2 * 1024 * 1024)
        engine.record_clipboard(payload)
        self.assertEqual(engine.get_clipboard_history(), [payload])
        EVIDENCE["clipboard_large"] = {"input_bytes": len(payload),
                                         "file_bytes": Path(engine.clipboard_file).stat().st_size}

    def test_clipboard_io_blocks_glib_main_thread(self):
        from gi.repository import GLib
        from src.tools import ToolsEngine
        from src.window import LauncherWindow
        engine = ToolsEngine()
        clipboard = Mock()
        clipboard.read_text_finish.return_value = "synthetic-secret"
        window = SimpleNamespace(_clipboard_generation=1, tools=engine)
        loop = GLib.MainLoop()
        thread_ids = []
        timings = {}
        real_fsync = os.fsync

        def slow_fsync(fd):
            thread_ids.append(threading.get_ident())
            time.sleep(.15)
            return real_fsync(fd)

        def receive():
            timings["started"] = time.perf_counter()
            LauncherWindow._on_clipboard_read(window, clipboard, object(), 1)
            timings["finished"] = time.perf_counter()
            return False

        def heartbeat():
            timings["heartbeat"] = time.perf_counter()
            loop.quit()
            return False

        with patch("src.storage.os.fsync", side_effect=slow_fsync):
            GLib.idle_add(receive, priority=GLib.PRIORITY_HIGH)
            GLib.timeout_add(10, heartbeat)
            loop.run()
        blocked = (timings["heartbeat"] - timings["started"]) * 1000
        self.assertEqual(thread_ids, [threading.get_ident()])
        self.assertGreaterEqual(blocked, 140)
        EVIDENCE["clipboard_main_thread"] = {"injected_fsync_ms": 150,
                                              "heartbeat_after_ms": round(blocked, 3)}

    def test_history_io_is_synchronous_on_caller(self):
        from src.history import HistoryManager
        history = HistoryManager()
        with patch("src.history.write_json") as write:
            history.record_launch("synthetic.desktop", "synthetic query")
        write.assert_called_once()
        EVIDENCE["history_sync"] = "record_launch writes before returning; called by GTK row activation"

    def test_currency_copy_loses_small_values_and_overflows(self):
        from src.tools import ToolsEngine
        engine = ToolsEngine()
        engine._rates = {"USD": 1.0, "BTC": .000014, "BRL": 5.0}
        engine._rates_timestamp = time.time()
        result = engine.convert_currency("1 usd em btc")
        self.assertIn("0", result["title"])
        self.assertEqual(result["copy"], "0.00")
        overflow = engine.convert_currency("1" + "0" * 308 + " usd em brl")
        self.assertEqual(overflow["copy"], "inf")
        EVIDENCE["currency"] = {"small": result, "overflow": overflow}

    def test_unit_prefix_case_changes_physical_value(self):
        from src.tools import ToolsEngine
        engine = ToolsEngine()
        observed = engine.convert_units("1 Mm em m")
        expected = engine._unit_registry().Quantity(1, "Mm").to("m").magnitude
        self.assertEqual(expected, 1000000)
        self.assertEqual(float(observed["copy"]), .001)
        EVIDENCE["unit_case"] = {"query": "1 Mm em m", "expected": expected,
                                  "observed": observed, "error_factor": expected / float(observed["copy"])}

    def test_file_failure_hides_launcher(self):
        from src.window import LauncherWindow
        row = SimpleNamespace(_file_entry=SimpleNamespace(path="/synthetic/deleted"),
                              get_activatable=lambda: True)
        window = SimpleNamespace(_tool_copy_val=None, files=Mock(), hide_launcher=Mock())
        window.files.open_item.return_value = False
        with contextlib.redirect_stdout(io.StringIO()):
            LauncherWindow._on_row_activated(window, None, row)
        window.hide_launcher.assert_called_once()
        EVIDENCE["open_failure"] = "open_item=False still calls hide_launcher; no user-visible error"

    def test_index_limit_refresh_and_permission_errors(self):
        from src.files import FileSearchEngine
        files = self.root / "files"
        files.mkdir()
        for i in range(10020):
            (files / f"document-{i:05}.txt").touch()
        engine = FileSearchEngine(home_dir=str(files), refresh_seconds=0)
        engine.search_current("document", 3)
        self.assertEqual(len(engine._indexed_files), 10000)
        snapshot = engine._indexed_files
        victim = next(item for item in snapshot if not item.is_dir)
        Path(victim.path).unlink()
        engine.search_current("document", 3)
        self.assertNotIn(victim.path, {item.path for item in engine._indexed_files})
        with patch("src.files.os.scandir", side_effect=PermissionError("synthetic EACCES")):
            self.assertEqual(engine._scan(), ())
        EVIDENCE["index_limit_refresh_eacces"] = "approved; 10020 files capped at 10000; deletion refreshed"

    def test_http_limits_and_malformed_responses(self):
        from src.tools import ToolsEngine
        from src.translation import translate
        from src.dictionary import lookup
        observations = []
        for function, target in (
            (lambda: ToolsEngine()._fetch_geocoding("synthetic"), "urllib.request.urlopen"),
            (lambda: ToolsEngine()._load_rates(), "urllib.request.urlopen"),
            (lambda: translate("synthetic-audit", "en", "pt"), "src.translation.urlopen"),
            (lambda: lookup("synthetic", "https://en.wiktionary.org/wiki/synthetic"), "src.dictionary.urlopen"),
        ):
            response = Mock()
            response.__enter__ = Mock(return_value=response)
            response.__exit__ = Mock(return_value=False)
            response.read.return_value = b"invalid-json"
            with patch(target, return_value=response), contextlib.redirect_stdout(io.StringIO()):
                try:
                    function()
                    outcome = "handled"
                except ValueError:
                    outcome = "raises to worker"
            observations.append({"target": target, "read_args": list(response.read.call_args.args), "outcome": outcome})
        self.assertEqual([r["read_args"] for r in observations], [[], [], [2000000], [2000000]])
        EVIDENCE["http_reads"] = observations

    def test_geocoding_and_weather_attempt_caches_grow(self):
        from src.tools import ToolsEngine
        engine = ToolsEngine()
        body = {"results": [{"name": "Synthetic", "timezone": "UTC", "country": "Test"}]}
        with patch("urllib.request.urlopen", side_effect=lambda *a, **kw: io.BytesIO(json.dumps(body).encode())):
            for i in range(1000):
                engine.check_timezone(f"hora em syntheticcity{i}")
        with patch.object(engine, "_fetch_geocoding", return_value=None):
            for i in range(1000):
                engine.check_weather(f"clima em syntheticcity{i}")
        self.assertEqual(len(engine._geo_cache), 1000)
        self.assertEqual(len(engine._weather_attempts), 1000)
        EVIDENCE["unbounded_caches"] = {"geocoding": len(engine._geo_cache),
                                          "weather_attempts": len(engine._weather_attempts),
                                          "persisted_bytes": Path(engine.geo_cache_file).stat().st_size}

    def test_blur_removes_preexisting_user_entry(self):
        from src.preferences import configure_blur
        settings = Mock()
        settings.get_strv.return_value = ["SpotLauncher", "OtherApp"]
        config = Mock()
        config.get.return_value = False
        schema = Mock()
        schema.list_keys.return_value = ["blur", "whitelist"]
        source = Mock()
        source.lookup.return_value = schema
        with patch("src.preferences.Path.exists", return_value=True), \
             patch("src.preferences.Gio.SettingsSchemaSource.new_from_directory", return_value=source), \
             patch("src.preferences.Gio.Settings.new_full", return_value=settings):
            configure_blur(False, config)
        settings.set_strv.assert_called_once_with("whitelist", ["OtherApp"])
        EVIDENCE["blur_ownership"] = "preexisting SpotLauncher whitelist entry removed even when Spot did not add it"

    def test_shutdown_worker_suppresses_delivery(self):
        from src.worker import LatestRequestWorker
        pending = []
        gate = threading.Event()
        started = threading.Event()
        ended = threading.Event()
        worker = LatestRequestWorker(lambda *args: (pending.append(args), ended.set()))
        callback = Mock()

        def task():
            started.set()
            gate.wait(2)
            return "old"

        worker.submit(task, callback)
        self.assertTrue(started.wait(2))
        worker.close()
        gate.set()
        self.assertTrue(ended.wait(2))
        worker._thread.join(2)
        function, *args = pending[0]
        function(*args)
        callback.assert_not_called()
        self.assertFalse(worker._thread.is_alive())
        EVIDENCE["worker_shutdown"] = "approved; active task completes, old result suppressed, thread exits"

    def test_obsolete_dictionary_keeps_fetching_before_latest_task(self):
        from src.dictionary import lookup
        from src.worker import LatestRequestWorker
        first_request = threading.Event()
        release = threading.Event()
        done = threading.Event()
        calls = []
        bodies = iter(({"error": {"code": "missingtitle"}},
                       {"error": {"code": "missingtitle"}},
                       {"query": {"searchinfo": {"suggestion": "synthetic-fix"}}},
                       {"parse": {"text": "<ol><li>Synthetic definition</li></ol>"}}))
        callback = Mock()
        worker = LatestRequestWorker(lambda function, *args: function(*args))

        def fetch(*args, **kwargs):
            calls.append(time.perf_counter())
            if len(calls) == 1:
                first_request.set()
                release.wait(2)
            time.sleep(.06)
            return io.BytesIO(json.dumps(next(bodies)).encode())

        latest = []
        with patch("src.dictionary.urlopen", side_effect=fetch):
            worker.submit(lambda: lookup("Synthetic", "https://en.wiktionary.org/wiki/Synthetic"), callback)
            self.assertTrue(first_request.wait(2))
            cancelled = time.perf_counter()
            worker.invalidate()
            worker.submit(lambda: latest.append(time.perf_counter()), lambda result: done.set())
            release.set()
            self.assertTrue(done.wait(3))
        worker.close()
        worker._thread.join(2)
        callback.assert_not_called()
        self.assertEqual(len(calls), 4)
        delay = (latest[0] - cancelled) * 1000
        self.assertGreater(delay, 200)
        EVIDENCE["obsolete_dictionary"] = {"requests_after_invalidation": sum(t > cancelled for t in calls),
                                              "latest_task_wait_ms": round(delay, 3),
                                              "synthetic_delay_per_request_ms": 60}

    def test_updater_divergence_untracked_and_ignored_data_loss(self):
        from src import updater
        remote, clone = self.root / "remote", self.root / "clone"

        def git(directory, *args):
            return subprocess.run(["git", "-C", str(directory), *args], check=True,
                                  capture_output=True, text=True, timeout=10).stdout.strip()

        subprocess.run(["git", "init", "-q", "-b", "main", str(remote)], check=True, capture_output=True)
        git(remote, "config", "user.name", "Audit")
        git(remote, "config", "user.email", "audit@example.invalid")
        (remote / ".gitignore").write_text("private-cache\n")
        (remote / "file").write_text("v1")
        git(remote, "add", ".")
        git(remote, "commit", "-qm", "initial")
        subprocess.run(["git", "clone", "-q", str(remote), str(clone)], check=True, capture_output=True)
        (remote / "private-cache").write_text("new upstream")
        git(remote, "add", "-f", "private-cache")
        git(remote, "commit", "-qm", "track formerly ignored path")
        (clone / "private-cache").write_text("LOCAL SYNTHETIC DATA")
        with patch.object(updater, "ROOT", clone):
            commit = updater.check_update()
            self.assertTrue(commit)
            result = updater.install_update(commit)
        self.assertTrue(result)
        self.assertEqual((clone / "private-cache").read_text(), "new upstream")
        EVIDENCE["updater_ignored"] = {"installed": result, "ignored_local_content_preserved": False}

        # Divergência e colisão de arquivo não ignorado são recusadas pelo Git.
        (remote / "new-file").write_text("upstream")
        git(remote, "add", ".")
        git(remote, "commit", "-qm", "new path")
        (clone / "new-file").write_text("local untracked")
        with patch.object(updater, "ROOT", clone):
            commit = updater.check_update()
            self.assertFalse(updater.install_update(commit))
            self.assertEqual((clone / "new-file").read_text(), "local untracked")
            git(clone, "config", "user.name", "Audit")
            git(clone, "config", "user.email", "audit@example.invalid")
            (clone / "file").write_text("local commit")
            git(clone, "commit", "-qam", "diverge")
            self.assertIsNone(updater.check_update())
        EVIDENCE["updater_diverged_untracked"] = "approved; ordinary untracked collision and divergent history rejected"

    def test_terminal_desktop_path_is_lost(self):
        from gi.repository import Gio
        from src.indexer import AppEntry, AppIndexer
        output = self.root / "cwd.txt"
        terminal = self.root / "terminal"
        # Script controlado, sem comando fornecido pelo usuário.
        terminal.write_text('#!/bin/sh\npwd > "' + str(output) + '"\n')
        terminal.chmod(0o700)
        workdir = self.root / "desired-working-directory"
        workdir.mkdir()
        desktop = self.root / "audit.desktop"
        desktop.write_text(f"[Desktop Entry]\nType=Application\nName=Audit\nExec=/bin/true\nTerminal=true\nPath={workdir}\n")
        info = Gio.DesktopAppInfo.new_from_filename(str(desktop))
        entry = AppEntry("audit.desktop", "Audit", "", "", True, info)
        with patch("src.indexer.get_default_terminal", return_value=[str(terminal)]):
            self.assertTrue(AppIndexer.__new__(AppIndexer).launch(entry))
        deadline = time.monotonic() + 3
        while not output.exists() and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertTrue(output.exists())
        self.assertNotEqual(output.read_text().strip(), str(workdir))
        EVIDENCE["terminal_desktop_path"] = {"honored": False, "observed_cwd": output.read_text().strip()}


if __name__ == "__main__":
    if os.environ.get("SPOT_AUDIT_CORE") != "1":
        with tempfile.TemporaryDirectory(prefix="spot-audit-core-") as temporary:
            base = Path(temporary)
            env = dict(os.environ, SPOT_AUDIT_CORE="1", GSETTINGS_BACKEND="memory", GIO_USE_VFS="local")
            # Preserva dependências instaladas no user-site ao isolar HOME/dados.
            env["PYTHONPATH"] = os.pathsep.join(str(Path(p or os.getcwd()).resolve()) for p in sys.path)
            for key, name in (("HOME", "home"), ("XDG_CONFIG_HOME", "config"),
                              ("XDG_CACHE_HOME", "cache"), ("XDG_DATA_HOME", "data"),
                              ("XDG_RUNTIME_DIR", "runtime")):
                (base / name).mkdir(mode=0o700)
                env[key] = str(base / name)
            for key in ("DISPLAY", "WAYLAND_DISPLAY", "DBUS_SESSION_BUS_ADDRESS"):
                env.pop(key, None)
            sys.exit(subprocess.run(["dbus-run-session", "--", sys.executable, "-B", *sys.argv], env=env).returncode)
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(AuditReproductions))
    report = {"commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "tests": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
              "note": "Passing defect tests confirm the defect in 1.8.0, not a fix.",
              "evidence": EVIDENCE, "unittest_log": stream.getvalue()}
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs/auditoria/resultados-1.8.0/reproducoes.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(stream.getvalue())
    sys.exit(not result.wasSuccessful())
