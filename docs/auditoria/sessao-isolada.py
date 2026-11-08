"""Executa medições em GNOME headless com HOME/XDG, clipboard e D-Bus próprios.

python3 -B docs/auditoria/sessao-isolada.py latency|stress|gnome|functional DIRETORIO_DE_SAIDA
Requer gnome-shell, dbus-run-session e a pilha gráfica já instalada. Não instala pacotes.
Controle do Shell verificado em GNOME 51.1; versões anteriores não foram validadas.
"""
import json
import math
import os
from pathlib import Path
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def summary(samples):
    ordered = sorted(samples)
    assert ordered
    return {"samples": len(samples), "median_ms": round(statistics.median(samples), 3),
            "p95_ms": round(ordered[math.ceil(len(samples) * .95) - 1], 3)}


def session(mode, base, output):
    env = dict(os.environ)
    shell_log = output / (mode + "-shell.log")
    if mode == "gnome":
        destination = Path(env["XDG_DATA_HOME"]) / "gnome-shell/extensions/spot-launcher@spot.local"
        shutil.copytree(ROOT / "data/gnome-extension", destination)
        hook = destination.parent / "audit-hook@spot.invalid"
        hook.mkdir()
        (hook / "metadata.json").write_text(json.dumps({"uuid": hook.name, "name": "Audit hook",
            "description": "Disposable overview override fixture", "shell-version": ["51"]}))
        (hook / "extension.js").write_text('''
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
export default class AuditHook extends Extension {
    enable() {
        this.original = Main.overview.show;
        const original = this.original;
        this.wrapper = function (...args) {
            global.__spotAuditOtherCalls = (global.__spotAuditOtherCalls || 0) + 1;
            return original.apply(this, args);
        };
        Main.overview.show = this.wrapper;
    }
    disable() { Main.overview.show = this.original; }
}
''')
        subprocess.run(["gsettings", "set", "org.gnome.shell", "enabled-extensions",
                        "['spot-launcher@spot.local']"], env=env, check=True)
        env["SPOT_AUDIT_OUTPUT"] = str(output / "gnome-51.json")
        env["SPOT_AUDIT_ROOT"] = str(ROOT)
    command = ["gnome-shell", "--headless", "--virtual-monitor", "1280x900",
               "--wayland-display", "spot-audit"]
    if mode == "gnome":
        command.extend(["--automation-script", str(HERE / "auditar-gnome.js")])
    else:
        env["SPOT_AUDIT_READY"] = str(base / "ready")
        command.extend(["--automation-script", str(HERE / "preparar-sessao.js")])
    with shell_log.open("w") as log:
        shell = subprocess.Popen(command, env=env, stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + 30
            socket = Path(env["XDG_RUNTIME_DIR"]) / "spot-audit"
            while not socket.exists() and shell.poll() is None and time.monotonic() < deadline:
                time.sleep(.1)
            if not socket.exists() or shell.poll() is not None:
                raise RuntimeError("GNOME headless não iniciou; consulte " + str(shell_log))
            env["WAYLAND_DISPLAY"] = "spot-audit"
            if mode == "gnome":
                code = shell.wait(timeout=240)
                if code:
                    raise RuntimeError(f"Teste GNOME terminou com {code}; consulte {shell_log}")
                return
            while not (base / "ready").exists() and shell.poll() is None and time.monotonic() < deadline:
                time.sleep(.1)
            if not (base / "ready").exists():
                raise RuntimeError("Panorama não preparado; consulte " + str(shell_log))
            if mode in ("stress", "functional", "regression"):
                with (output / ("interface-" + mode + ".log")).open("w") as app_log:
                    subprocess.run([sys.executable, "-B", str(HERE / "medir-interface.py"), mode,
                                    str(output / ("interface-" + mode + "-wayland.json"))],
                                   env=dict(env, GDK_BACKEND="wayland"), check=True,
                                   stdout=app_log, stderr=app_log, timeout=4200)
                return
            result = {"method": "30 fresh processes per startup/daemon; 30 reopens excluding initial opening; usable=100% opacity; startup includes private D-Bus launch; OS cache not cleared",
                      "results": {}, "raw": {}}
            for backend in ("wayland", "x11", "auto"):
                display = re.search(r"Using public X11 display (:\d+)", shell_log.read_text())
                authority = list(Path(env["XDG_RUNTIME_DIR"]).glob(".mutter-Xwaylandauth.*"))
                if backend != "wayland" and (not display or not authority):
                    result["results"][backend] = {"status": "blocked", "reason": "isolated XWayland DISPLAY/auth not available"}
                    continue
                for case in ("startup", "daemon", "reopen"):
                    rows = []
                    for i in range(1 if case == "reopen" else 30):
                        with tempfile.TemporaryDirectory(dir=base, prefix="client-") as temporary:
                            client = Path(temporary)
                            client_env = dict(env, GDK_BACKEND=backend)
                            if backend != "wayland":
                                client_env["DISPLAY"] = display[1]
                                client_env["XAUTHORITY"] = str(authority[0])
                            if backend == "auto":
                                client_env.pop("GDK_BACKEND", None)
                            for key, name in (("HOME", "home"), ("XDG_CONFIG_HOME", "config"),
                                              ("XDG_CACHE_HOME", "cache"), ("XDG_DATA_HOME", "data")):
                                (client / name).mkdir(mode=0o700)
                                client_env[key] = str(client / name)
                            config = client / "config/spot-launcher"
                            config.mkdir()
                            (config / "config.json").write_text(json.dumps({"hide_on_focus_loss": False, "hide_updates": True}))
                            sample = client / "sample.json"
                            command = ["dbus-run-session", "--", sys.executable, "-B",
                                       str(HERE / "medir-interface.py"), case, str(sample)]
                            started = time.perf_counter()
                            client_env["SPOT_AUDIT_PROCESS_STARTED"] = str(started)
                            completed = subprocess.run(command, env=client_env, capture_output=True,
                                                       text=True, timeout=45)
                            if completed.returncode:
                                raise RuntimeError(completed.stderr[-3000:])
                            data = json.loads(sample.read_text())
                            rows.extend(data["samples"][1:] if case == "reopen" else data["samples"])
                            rows[-1]["parent_total_ms"] = round((time.perf_counter() - started) * 1000, 3)
                    key = backend + "_" + case
                    result["raw"][key] = rows
                    field = "process_to_usable_ms" if case == "startup" else "trigger_to_usable_ms"
                    result["results"][key] = summary([row[field] for row in rows])
                    (output / "interface-latency.json").write_text(json.dumps(result, indent=2) + "\n")
                    print(key, result["results"][key], flush=True)
            (output / "interface-latency.json").write_text(json.dumps(result, indent=2) + "\n")
        finally:
            if shell.poll() is None:
                shell.terminate()
                try:
                    shell.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    shell.kill()
                    shell.wait()


if __name__ == "__main__":
    if len(sys.argv) == 5 and sys.argv[1] == "_session":
        session(sys.argv[2], Path(os.environ["HOME"]).parent, Path(sys.argv[3]))
    else:
        mode = sys.argv[1]
        fixed = mode == "gnome-regression"
        if fixed:
            mode = "gnome"
        assert mode in ("latency", "stress", "gnome", "functional", "regression")
        output = Path(sys.argv[2]).resolve()
        output.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="spot-audit-gnome-") as temporary:
            base = Path(temporary)
            env = dict(os.environ, SPOT_AUDIT_ISOLATED="1", GSETTINGS_BACKEND="keyfile",
                       LIBGL_ALWAYS_SOFTWARE="1", GNOME_SHELL_SESSION_MODE="user", LANGUAGE="pt_BR:pt",
                       GSK_RENDERER="cairo", GIO_USE_VFS="local")
            if fixed:
                env["SPOT_AUDIT_FIXED"] = "1"
            env["PYTHONPATH"] = os.pathsep.join(str(Path(p or os.getcwd()).resolve()) for p in sys.path)
            for key, name in (("HOME", "home"), ("XDG_CONFIG_HOME", "config"),
                              ("XDG_CACHE_HOME", "cache"), ("XDG_DATA_HOME", "data"),
                              ("XDG_RUNTIME_DIR", "runtime")):
                (base / name).mkdir(mode=0o700)
                env[key] = str(base / name)
            for key in ("DISPLAY", "WAYLAND_DISPLAY", "DBUS_SESSION_BUS_ADDRESS", "SESSION_MANAGER"):
                env.pop(key, None)
            try:
                subprocess.run(["dbus-run-session", "--", sys.executable, "-B", str(Path(__file__).resolve()),
                                "_session", mode, str(output), "isolated"], env=env, check=True)
            finally:
                # Portais podem deixar mounts FUSE mortos após o D-Bus privado encerrar.
                if shutil.which("fusermount3"):
                    for name in ("doc", "gvfs"):
                        subprocess.run(["fusermount3", "-u", "-z", str(base / "runtime" / name)],
                                       capture_output=True, timeout=5)
