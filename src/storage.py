"""Persistência JSON com substituição atômica e arquivos privados."""
import json
import os
from pathlib import Path
import tempfile
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import logging


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as stream:
            temporary = stream.name
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


# One ordered queue: clipboard updates must not overtake each other.
_io = ThreadPoolExecutor(max_workers=1, thread_name_prefix="spot-storage")


def submit_io(function, *args):
    future = _io.submit(function, *args)
    def completed(result):
        if result.exception() is not None:
            logging.error("Falha ao persistir dados: %s", result.exception())
    future.add_done_callback(completed)
    return future


def write_json_ui(path, value):
    from gi.repository import GLib
    if GLib.main_depth():
        submit_io(write_json, path, deepcopy(value))
    else:
        write_json(path, value)


def flush_writes():
    # Drain before restart/exit; the executor remains usable by a resident app.
    _io.submit(lambda: None).result()
