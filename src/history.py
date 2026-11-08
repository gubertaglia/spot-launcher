from src.storage import write_json
from src.tools import normalize_text
import json
import os
from typing import Dict, List

import gi

gi.require_version("GLib", "2.0")
from gi.repository import GLib


class HistoryManager:

    def __init__(self):
        # Salva de acordo com os padrões XDG em ~/.cache/spot-launcher/history.json
        cache_base = GLib.get_user_cache_dir()
        self.cache_dir = os.path.join(cache_base, "spot-launcher")
        self.file_path = os.path.join(self.cache_dir, "history.json")
        self._usage: Dict[str, int] = {}
        self._queries = {}
        self._load()

    def _load(self):
        """Carrega o histórico do disco."""
        if not os.path.exists(self.file_path):
            return
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if not isinstance(data, dict):
                    return
                usage = data.get("usage", data)
                queries = data.get("queries", {})
                if not isinstance(usage, dict) or not isinstance(queries, dict):
                    return
                self._queries = {
                    query: {key: count for key, count in choices.items()
                            if isinstance(key, str) and type(count) is int and 0 < count <= 20}
                    for query, choices in list(queries.items())[-200:]
                    if isinstance(query, str) and len(query) <= 120 and isinstance(choices, dict)
                    and len(choices) <= 8
                }
                self._usage = {
                    key: value for key, value in usage.items()
                    if isinstance(key, str) and type(value) is int and value >= 0
                }
        except Exception as e:
            print(f"[History] Falha ao carregar cache: {e}")
            self._usage = {}

    def _save(self):
        """Salva o histórico de forma atômica."""
        try:
            write_json(self.file_path, {"usage": self._usage, "queries": self._queries})
        except Exception as e:
            print(f"[History] Falha ao salvar cache: {e}")

    def record_launch(self, app_id: str, query: str = ""):
        """Registra que um aplicativo foi aberto (aumenta sua relevância)."""
        if not app_id:
            return
        self._usage[app_id] = self._usage.get(app_id, 0) + 1
        query = " ".join(normalize_text(query).split())
        if query and len(query) <= 120:
            choices = self._queries.pop(query, {})
            if app_id in choices or len(choices) < 8:
                choices[app_id] = min(choices.get(app_id, 0) + 1, 20)
            self._queries[query] = choices
            if len(self._queries) > 200:
                del self._queries[next(iter(self._queries))]
        self._save()

    def get_query_count(self, app_id: str, query: str) -> int:
        return self._queries.get(query, {}).get(app_id, 0)

    def get_count(self, app_id: str) -> int:
        """Retorna quantas vezes um app já foi executado."""
        return self._usage.get(app_id, 0)

    def get_most_used_ids(self, limit: int = 6) -> List[str]:
        """Retorna os IDs dos programas mais utilizados."""
        sorted_items = sorted(
            self._usage.items(), key=lambda item: item[1], reverse=True
        )
        return [app_id for app_id, count in sorted_items[:limit]]
