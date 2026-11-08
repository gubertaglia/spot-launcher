"""Instrumenta a aplicação real; exige sessão gráfica DESCARTÁVEL e D-Bus privado.

Uso dentro da sessão isolada: python3 -B medir-interface.py stress saida.json
Modos: startup, daemon, reopen, stress, functional. SPOT_AUDIT_IDLE_SECONDS: 3600.
Não executar na sessão pessoal: a aplicação acessa o clipboard do display.
"""
import gc
import json
import os
from pathlib import Path
import resource
import sys
import time
import tracemalloc
from unittest.mock import patch

STARTED = float(os.environ.get("SPOT_AUDIT_PROCESS_STARTED", time.perf_counter()))
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
MODE, OUTPUT = sys.argv[1:3]
assert MODE in ("startup", "daemon", "reopen", "stress", "functional", "regression")
assert os.environ.get("SPOT_AUDIT_ISOLATED") == "1", "Use uma sessão descartável"
OUTPUT = Path(OUTPUT).resolve()
OUTPUT.parent.mkdir(parents=True, exist_ok=True)

import gi
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk
# Aplicar a escolha da entrada antes que a própria instrumentação importe GTK.
if os.getenv("DISPLAY") and not os.getenv("GDK_BACKEND"):
    Gdk.set_allowed_backends("x11,wayland")
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import GLib, Gtk
from src.app import SpotApplication
from src.files import FileEntry

REPORT = {"mode": MODE, "pid": os.getpid(), "samples": [], "memory": [], "checks": {}}
CURRENT_APP = None
ORIGINAL_EXCEPTHOOK = sys.excepthook


def callback_error(kind, value, traceback):
    ORIGINAL_EXCEPTHOOK(kind, value, traceback)
    REPORT["callback_error"] = f"{kind.__name__}: {value}"
    if CURRENT_APP:
        CURRENT_APP.quit()


sys.excepthook = callback_error


def memory(label):
    gc.collect()
    fields = {}
    for line in Path("/proc/self/smaps_rollup").read_text().splitlines():
        key, _, value = line.partition(":")
        if key in ("Rss", "Pss", "Private_Clean", "Private_Dirty", "Swap", "SwapPss"):
            fields[key + "_kib"] = int(value.split()[0])
    fields.update(label=label, elapsed_s=round(time.perf_counter() - STARTED, 3),
                  cpu_s=round(time.process_time(), 4),
                  threads=len(list(Path("/proc/self/task").iterdir())),
                  fds=len(list(Path("/proc/self/fd").iterdir())))
    if tracemalloc.is_tracing():
        fields["python_current_bytes"], fields["python_peak_bytes"] = tracemalloc.get_traced_memory()
    REPORT["memory"].append(fields)
    save()


def save():
    OUTPUT.write_text(json.dumps(REPORT, indent=2, ensure_ascii=False) + "\n")


class MeasuredApplication(SpotApplication):
    def __init__(self):
        global CURRENT_APP
        super().__init__()
        CURRENT_APP = self
        self.connect("window-added", self.added)
        self.shows = 0
        self.triggered = STARTED
        self.framed = False
        GLib.timeout_add_seconds(40 if MODE != "stress" else 4200, self.watchdog)

    def watchdog(self):
        window = self.window
        REPORT["watchdog"] = {"shows": self.shows, "visible": bool(window and window.is_visible()),
                                "mapped": bool(window and window.get_mapped()),
                                "closing": getattr(window, "_closing", None),
                                "opacity": window.scaled_content.get_opacity() if window else None}
        save()
        self.quit()
        return False

    def added(self, app, window):
        window.connect("map", self.mapped)
        if MODE == "daemon":
            GLib.timeout_add(100, self.open_first)

    def open_first(self):
        self.triggered = time.perf_counter()
        self.window.show_launcher()
        return False

    def mapped(self, window):
        if self.framed and MODE != "reopen":
            return
        clock = window.get_frame_clock()
        handler = None
        first = None

        def painted(clock):
            nonlocal first
            now = time.perf_counter()
            opacity = window.scaled_content.get_opacity()
            if first is None:
                first = (now, opacity)
            if opacity < 1:
                return
            clock.disconnect(handler)
            REPORT["samples"].append({
                "process_to_frame_ms": round((first[0] - STARTED) * 1000, 3),
                "trigger_to_frame_ms": round((first[0] - self.triggered) * 1000, 3),
                "first_frame_opacity": first[1],
                "process_to_usable_ms": round((now - STARTED) * 1000, 3),
                "trigger_to_usable_ms": round((now - self.triggered) * 1000, 3),
                "mapped": window.get_mapped(), "size": [window.get_width(), window.get_height()],
                "backend": window.get_display().__gtype__.name,
            })
            self.shows += 1
            save()
            if self.framed:
                GLib.timeout_add(160, self.next_reopen)
            else:
                self.framed = True
                GLib.timeout_add(200, self.after_first)

        handler = clock.connect("after-paint", painted)

    def after_first(self):
        import locale
        from datetime import date
        from src import regional_date_format
        REPORT["regional"] = {"LC_ALL": os.environ.get("LC_ALL"), "LANG": os.environ.get("LANG"),
                              "runtime_LC_TIME": locale.setlocale(locale.LC_TIME),
                              "runtime_date_format": locale.nl_langinfo(locale.D_FMT),
                              "stored_date_format": regional_date_format(),
                              "example_2026_11_08": date(2026, 11, 8).strftime(regional_date_format())}
        if MODE in ("startup", "daemon"):
            save()
            self.quit()
        elif MODE == "reopen":
            self.next_reopen()
        elif MODE in ("functional", "regression"):
            self.functional()
        else:
            self.stress()
        return False

    def next_reopen(self):
        if self.shows >= 31:
            save()
            self.quit()
        else:
            self.window.hide_launcher()

            def hidden():
                if self.window.is_visible():
                    return True
                self.open_first()
                return False

            GLib.timeout_add(10, hidden)
        return False

    def functional(self):
        from src.indexer import AppEntry
        from gi.repository import Gdk
        window = self.window
        window.config.config["hide_on_focus_loss"] = False
        window.get_settings().set_property("gtk-enable-animations", False)
        window.indexer._apps = [AppEntry(f"audit-{name}.desktop", f"Audit Editor {name}", "", "", False, None)
                                for name in ("Alpha", "Beta")]
        self.file_patch = patch.object(window.files, "search_current", side_effect=lambda *a: (time.sleep(.35), [])[1])
        self.file_patch.start()
        window.search_entry.set_text("audit editor")

        def select_second():
            window._on_key_pressed(None, Gdk.KEY_Down, 0, 0)
            REPORT["checks"]["selection_before_files"] = window.list_box.get_selected_row()._app_entry.id
            return False

        GLib.timeout_add(150, select_second)
        GLib.timeout_add(800, self.functional_after_files)

    def functional_after_files(self):
        window = self.window
        REPORT["checks"]["selection_after_files"] = window.list_box.get_selected_row()._app_entry.id
        assert (REPORT["checks"]["selection_before_files"] == REPORT["checks"]["selection_after_files"]) == (MODE == "regression")
        self.file_patch.stop()
        REPORT["checks"]["scales"] = []
        self.scale_values = iter((50, 75, 100, 125, 150, 175, 200))
        self.functional_scale()
        return False

    def functional_scale(self):
        value = next(self.scale_values, None)
        if value is None:
            self.preference_refs = []
            memory("functional_before_preferences")
            self.preferences_remaining = 50
            self.functional_preferences()
            return False
        self.window.config.config["scale"] = value
        self.window.apply_scale()

        def allocated():
            REPORT["checks"]["scales"].append({"percent": value, "width": self.window.get_width(),
                                                "height": self.window.get_height()})
            assert abs(self.window.get_width() - round(580 * value / 100)) <= 1
            self.functional_scale()
            return False

        GLib.timeout_add(200, allocated)
        return False

    def functional_preferences(self):
        import weakref
        self.window.open_preferences()
        self.preference_refs.append(weakref.ref(self.window.preferences_window))
        self.window.preferences_window.close()
        self.preferences_remaining -= 1
        if self.preferences_remaining:
            GLib.timeout_add(30, self.functional_preferences)
        else:
            GLib.timeout_add(1000, self.functional_done)
        return False

    def functional_done(self):
        gc.collect()
        count = len(self.preference_refs)
        alive = sum(ref() is not None for ref in self.preference_refs)
        REPORT["checks"][f"preferences_alive_after_{count}_close"] = alive
        REPORT["checks"][f"toplevels_after_{count}_close"] = len(Gtk.Window.list_toplevels())
        REPORT["checks"].setdefault("preference_batches", []).append({"closed": count, "alive": alive})
        memory("preferences_closed_" + str(len(self.preference_refs)))
        if len(self.preference_refs) == 50:
            self.preferences_remaining = 50
            GLib.timeout_add(1000, self.functional_preferences)
            return False
        REPORT["checks"]["preferences_alive_after_100_close"] = sum(ref() is not None for ref in self.preference_refs)
        if MODE == "regression":
            REPORT["checks"]["preferences_distinct_instances"] = len({id(ref()) for ref in self.preference_refs})
            assert REPORT["checks"]["preferences_distinct_instances"] == 1
        preference = self.preference_refs[0]()
        if preference is not None:
            # Só tipos de referências do objeto sintético, sem serializar conteúdo pessoal.
            REPORT["checks"]["preference_referrers"] = [
                type(ref).__name__ + ":" + getattr(ref, "__qualname__", "")
                for ref in gc.get_referrers(preference)]
        REPORT["checks"]["search_accessible_role"] = self.window.search_entry.get_accessible_role().value_nick
        try:
            paintable = Gtk.WidgetPaintable.new(self.window)
            snapshot = Gtk.Snapshot.new()
            paintable.snapshot(snapshot, self.window.get_width(), self.window.get_height())
            node = snapshot.to_node()
            texture = self.window.get_renderer().render_texture(node, None)
            REPORT["checks"]["screenshot_saved"] = texture.save_to_png(str(OUTPUT.with_suffix(".png")))
        except Exception as error:
            REPORT["checks"]["screenshot_blocked"] = type(error).__name__ + ": " + str(error)
        from gi.repository import Gdk
        self.synthetic_secret = "SPOT-AUDIT-SYNTHETIC-SECRET"
        provider = Gdk.ContentProvider.new_union([
            Gdk.ContentProvider.new_for_value(self.synthetic_secret),
            Gdk.ContentProvider.new_for_bytes("x-kde-passwordManagerHint", GLib.Bytes.new(b"secret")),
        ])
        assert self.window.clipboard.set_content(provider)
        REPORT["checks"]["secret_hint_offered"] = self.window.clipboard.get_formats().contain_mime_type("x-kde-passwordManagerHint")
        GLib.timeout_add(300, self.functional_secret)
        return False

    def functional_secret(self):
        REPORT["checks"]["secret_persisted"] = self.synthetic_secret in self.window.tools.get_clipboard_history()
        assert REPORT["checks"]["secret_persisted"] == (MODE != "regression")
        self.window.clipboard.set("")
        GLib.timeout_add(200, self.functional_after_clear)
        return False

    def functional_after_clear(self):
        REPORT["checks"]["secret_persisted_after_clipboard_clear"] = self.synthetic_secret in self.window.tools.get_clipboard_history()
        assert REPORT["checks"]["secret_persisted_after_clipboard_clear"] == (MODE != "regression")
        memory("functional_end")
        save()
        self.quit()
        return False

    def stress(self):
        self.window.get_settings().set_property("gtk-enable-animations", False)
        # A janela é real; dados de busca e rede são sintéticos.
        self.window.files._publish(tuple(
            FileEntry(f"relatorio-{i:05}.txt", f"/synthetic/{i}", False,
                      "text-x-generic-symbolic", kind="document") for i in range(10000)
        ))
        self.window.files._refreshed_at = time.monotonic()
        tracemalloc.start(5)
        memory("warmup")
        self.cycles = 0
        self.cycle()

    def cycle(self):
        for _ in range(10):
            self.window.show_launcher()
            self.window.search_entry.set_text("relatorio")
            self.window.hide_launcher()
            self.cycles += 1
        if self.cycles % 100 == 0:
            memory(f"show_hide_{self.cycles}")
        if self.cycles < 1000:
            GLib.idle_add(self.cycle)
        else:
            self.preferences_count = 0
            GLib.timeout_add(30, self.preferences_cycle)
        return False

    def preferences_cycle(self):
        self.window.show_launcher()
        self.window.open_preferences()
        self.window.preferences_window.close()
        self.preferences_count += 1
        if self.preferences_count < 50:
            GLib.timeout_add(30, self.preferences_cycle)
        else:
            memory("preferences_50")
            GLib.timeout_add(150, self.query_checks)
        return False

    def query_checks(self):
        window = self.window
        # Rede falsa via os mesmos caminhos de produção; não faz 1000 chamadas externas.
        import src.tools
        response = {"results": [{"name": "Synthetic", "country": "Test", "timezone": "UTC",
                                  "latitude": 1, "longitude": 1}]}
        from io import BytesIO
        with patch("urllib.request.urlopen", side_effect=lambda *a, **kw: BytesIO(json.dumps(response).encode())):
            for i in range(1000):
                window.tools.check_timezone(f"hora em auditcity{i}")
        for i in range(1000):
            with patch("urllib.request.urlopen", side_effect=OSError("synthetic offline")):
                # Evita log de rede ao testar o mapa de tentativas de clima.
                with patch.object(window.tools, "_fetch_geocoding", return_value=None):
                    window.tools.check_weather(f"clima em auditcity{i}")
        REPORT["checks"]["cache_entries"] = {
            "geo": len(window.tools._geo_cache), "weather_attempts": len(window.tools._weather_attempts)}
        memory("unique_queries_1000")
        GLib.timeout_add(150, self.visual_checks)
        return False

    def visual_checks(self):
        window = self.window
        for query in ("2+2", "calendario", "emoji", "g synthetic", "> printf synthetic"):
            window.search_entry.set_text(query)
            REPORT["checks"][query] = {"rows": window._result_count,
                                       "calendar_visible": bool(window.calendar_panel and window.calendar_panel.get_visible())}
        window.search_entry.set_text("relatorio")
        GLib.timeout_add(1000, self.after_search)
        return False

    def after_search(self):
        REPORT["checks"]["files"] = {"rows": self.window._result_count,
                                       "selected": self.window.list_box.get_selected_row() is not None}
        self.window.hide_launcher()
        self.idle_started = time.perf_counter()
        self.idle_seconds = float(os.environ.get("SPOT_AUDIT_IDLE_SECONDS", "3600"))
        memory("idle_start")
        GLib.timeout_add_seconds(30, self.idle_sample)
        return False

    def idle_sample(self):
        memory("idle")
        if time.perf_counter() - self.idle_started >= self.idle_seconds:
            REPORT["idle_duration_s"] = round(time.perf_counter() - self.idle_started, 3)
            REPORT["peak_rss_kib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            save()
            self.quit()
            return False
        return True


# O script chama a entrada real, mas impede fetch/merge e rede externa.
with patch("src.app.SpotApplication", MeasuredApplication), \
     patch("src.window.check_update", return_value=None), \
     patch("urllib.request.urlopen", side_effect=OSError("audit offline")), \
     patch("src.dictionary.urlopen", side_effect=OSError("audit offline")), \
     patch("src.translation.urlopen", side_effect=OSError("audit offline")):
    import run
    sys.argv = [str(ROOT / "run.py")] + (["--daemon"] if MODE == "daemon" else [])
    status = run.main()
    status = status or int("watchdog" in REPORT or "callback_error" in REPORT)
    REPORT["exit_status"] = status
    save()
    sys.exit(status)
