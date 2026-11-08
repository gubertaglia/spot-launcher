"""Medições da auditoria, sem abrir GUI, acessar rede ou indexar o home.

Execute na raiz: python3 docs/auditoria/benchmark.py
Saída JSON no stdout. ru_maxrss é pico de RSS no Linux, não memória ociosa.
"""

import importlib.metadata
import json
import math
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time
import threading


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def summary(values):
    ordered = sorted(values)
    return {
        "median_ms": round(statistics.median(values), 3),
        "p95_ms": round(ordered[math.ceil(len(values) * 0.95) - 1], 3),
        "samples": len(values),
    }


def measure(callback, repeats=120):
    for _ in range(5):
        callback()
    times = []
    for _ in range(repeats):
        start = time.perf_counter()
        callback()
        times.append((time.perf_counter() - start) * 1000)
    return summary(times)


def imports():
    # Processos novos, mas cache do SO não é limpo: não mede boot a frio.
    cases = {
        "baseline": "pass",
        "gtk_adw": "import gi; gi.require_version('Gtk', '4.0'); gi.require_version('Adw', '1'); from gi.repository import Gtk, Adw",
        "pint_registry": "import pint; registry = pint.UnitRegistry()",
        "app_module": "import src.app",
    }
    result = {}
    for name, code in cases.items():
        samples = []
        rss = []
        for _ in range(7):
            program = (
                "import time, resource, json\nstart = time.perf_counter()\n"
                + code
                + "\nprint(json.dumps({'ms': (time.perf_counter()-start)*1000, "
                "'peak_mib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024}))"
            )
            completed = subprocess.run(
                [sys.executable, "-B", "-c", program], cwd=ROOT,
                check=True, text=True, capture_output=True,
            )
            row = json.loads(completed.stdout)
            samples.append(row["ms"])
            rss.append(row["peak_mib"])
        result[name] = {
            **summary(samples),
            "median_peak_rss_mib": round(statistics.median(rss), 2),
        }
    return result


def searches():
    from rapidfuzz import fuzz
    from src.files import FileEntry, FileSearchEngine
    from src.history import HistoryManager
    from src.indexer import AppIndexer
    from src.matcher import SearchMatcher

    # Usa as funções originais; evita os construtores com I/O/thread de arquivos.
    history = HistoryManager.__new__(HistoryManager)
    history._usage = {}
    history._queries = {}
    matcher = SearchMatcher(history)
    indexer = AppIndexer()
    apps = indexer.get_apps()
    queries = ["fire", "code", "terminal", "arquivos", "zzzxq"]
    app_result = {
        "entries": len(apps),
        "searches": {q: measure(lambda q=q: matcher.search(q, apps)) for q in queries},
        "reload": measure(indexer.reload, repeats=20),
    }
    file_result = {}
    for size in (1000, 10000, 50000):
        engine = FileSearchEngine.__new__(FileSearchEngine)
        engine._lock = threading.Lock()
        engine._indexed_files = [
            FileEntry(
                name=f"{('relatorio', 'codigo', 'imagem', 'documento', 'arquivo')[i % 5]}-{i:06d}.txt",
                path=f"/synthetic/{i}", is_dir=False, icon_name="text-x-generic-symbolic",
            )
            for i in range(size)
        ]
        file_result[str(size)] = {
            q: measure(lambda q=q: engine.search(q, limit=3))
            for q in ("relatorio", "doc", "zzzxq")
        }
    return {"rapidfuzz_backend": fuzz.ratio.__module__, "apps": app_result, "files_synthetic": file_result}


if __name__ == "__main__":
    report = {
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "packages": {name: importlib.metadata.version(name) for name in ("PyGObject", "RapidFuzz", "Pint")},
        },
        "imports": imports(),
        "search": searches(),
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
