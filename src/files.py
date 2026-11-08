from dataclasses import dataclass, field, replace
from heapq import nlargest
from itertools import islice
from operator import itemgetter
import os
import threading
import time
from typing import List

import gi

gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")
from gi.repository import Gio, GLib
from rapidfuzz import fuzz
from src.tools import normalize_text


@dataclass(frozen=True, slots=True)
class FileEntry:
    name: str
    path: str
    is_dir: bool
    icon_name: str
    score: float = 100.0
    kind: str = "file"
    normalized_name: str = field(default="", repr=False, compare=False)

    def __post_init__(self):
        if not self.normalized_name:
            object.__setattr__(self, "normalized_name", normalize_text(self.name))


FILE_FILTERS = {
    alias: kind for kind, aliases in {
        "image": "foto fotos fotografia fotografias imagem imagens imagen imagenes photo photos image images picture pictures photographie photographies",
        "video": "video videos filme filmes pelicula peliculas movie movies film films",
        "document": "documento documentos document documents",
        "audio": "audio audios musica musicas music musique musiques sonido sonidos son sons sound sounds",
        "file": "arquivo arquivos archivo archivos file files fichier fichiers",
    }.items() for alias in aliases.split()
}


def file_query(query):
    text = normalize_text(query)
    prefix, _, remainder = text.partition(":")
    kind = FILE_FILTERS.get(prefix.strip())
    return (kind, remainder.strip()) if kind else (None, text)


def file_kind(name, is_dir):
    if is_dir:
        return "folder"
    content_type, _ = Gio.content_type_guess(name, None)
    mime = Gio.content_type_get_mime_type(content_type) or ""
    for prefix, kind in (("image/", "image"), ("video/", "video"), ("audio/", "audio")):
        if mime.startswith(prefix):
            return kind
    if mime.startswith("text/") or mime in (
        "application/pdf", "application/rtf", "application/msword",
        "application/vnd.ms-excel", "application/vnd.ms-powerpoint",
    ) or mime.startswith(("application/vnd.oasis.opendocument.",
                          "application/vnd.openxmlformats-officedocument.")):
        return "document"
    return "file"


FILE_ICONS = {
    "folder": "folder-symbolic", "image": "image-x-generic-symbolic",
    "video": "video-x-generic-symbolic", "audio": "audio-x-generic-symbolic",
    "document": "x-office-document-symbolic", "file": "text-x-generic-symbolic",
}


class FileSearchEngine:

    MAX_FILES = 10000
    EXCLUDED = {"node_modules", "venv", ".venv", "__pycache__"}

    def __init__(self, home_dir=None, refresh_seconds=60):
        self.home_dir = home_dir or os.path.expanduser("~")
        self._indexed_files = ()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._refresh_seconds = refresh_seconds
        self._refreshed_at = None

    def close(self):
        self._stop.set()

    def _publish(self, entries):
        with self._lock:
            self._indexed_files = tuple(entries)

    def _scan(self, deep=True):
        known = {item.path: item for item in self._indexed_files}
        entries = {}
        # Use the desktop's actual localized/custom user directories first.
        roots = []
        if self.home_dir == os.path.expanduser("~"):
            for special in (
                GLib.UserDirectory.DIRECTORY_DOCUMENTS, GLib.UserDirectory.DIRECTORY_PICTURES,
                GLib.UserDirectory.DIRECTORY_VIDEOS, GLib.UserDirectory.DIRECTORY_MUSIC,
                GLib.UserDirectory.DIRECTORY_DESKTOP, GLib.UserDirectory.DIRECTORY_DOWNLOAD,
            ):
                folder = GLib.get_user_special_dir(special)
                if folder and folder != self.home_dir:
                    roots.append(folder)
        roots.extend(os.path.join(self.home_dir, name) for name in (
            "Documentos", "Documents", "Imagens", "Pictures", "Vídeos", "Videos",
            "Músicas", "Music", "Downloads", "Projetos", "Projects",
        ))
        roots.append(self.home_dir)
        visited = set()
        stack = list(reversed(roots))
        while stack and len(entries) < self.MAX_FILES and not self._stop.is_set():
            root = stack.pop()
            if root in visited or os.path.islink(root):
                continue
            visited.add(root)
            try:
                with os.scandir(root) as children:
                    for child in children:
                        if self._stop.is_set() or len(entries) >= self.MAX_FILES:
                            break
                        if child.name.startswith(".") or child.name in self.EXCLUDED:
                            continue
                        try:
                            is_dir = child.is_dir(follow_symlinks=False)
                        except OSError:
                            continue
                        item = known.get(child.path)
                        if item is None or item.is_dir != is_dir:
                            kind = file_kind(child.name, is_dir)
                            item = FileEntry(child.name, child.path, is_dir, FILE_ICONS[kind], kind=kind)
                        entries[child.path] = item
                        if deep and is_dir:
                            stack.append(child.path)
            except OSError:
                continue
        return tuple(entries.values())

    def search_current(self, query, limit):
        """Called by the file worker. Refresh only when a search needs the index."""
        if self._refreshed_at is None or time.monotonic() - self._refreshed_at >= self._refresh_seconds:
            entries = self._scan()
            if self._stop.is_set():
                return []
            self._publish(entries)
            self._refreshed_at = time.monotonic()
        return self.search(query, limit)

    def search(self, query: str, limit: int = 4) -> List[FileEntry]:
        kind, text = file_query(query)
        if not kind and len(text) < 2:
            return []
        with self._lock:
            snapshot = self._indexed_files
        if kind == "file":
            entries = (item for item in snapshot if not item.is_dir)
        elif kind:
            entries = (item for item in snapshot if item.kind == kind)
        else:
            entries = snapshot
        if not text:
            return list(islice(entries, limit))

        def ranked():
            for item in entries:
                name = item.normalized_name
                if name == text:
                    score = 140.0
                elif name.startswith(text):
                    score = 110.0 + len(text) / len(name) * 20.0
                elif text in name:
                    score = 80.0 + len(text) / len(name) * 15.0
                else:
                    score = fuzz.ratio(text, name, score_cutoff=50)
                if score > 50:
                    yield score, item

        if limit is None:
            matches = sorted(ranked(), key=itemgetter(0), reverse=True)
        else:
            matches = nlargest(limit, ranked(), key=itemgetter(0))
        return [replace(item, score=score) for score, item in matches]

    def open_item(self, item: FileEntry) -> bool:
        try:
            file_uri = GLib.filename_to_uri(item.path)
            return Gio.AppInfo.launch_default_for_uri(file_uri, None)
        except Exception as e:
            print(f"[FileEngine] Erro ao abrir: {e}")
            return False
