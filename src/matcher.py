from dataclasses import dataclass
from typing import List

from src.search import search_score, result_key, intent_metadata, search_text
from src.tools import normalize_text
from src.history import HistoryManager
from src.indexer import AppEntry


@dataclass
class MatchResult:
    entry: AppEntry
    score: float


class SearchMatcher:

    def __init__(self, history: HistoryManager):
        self.history = history

    def search(
        self, query: str, apps: List[AppEntry], limit: int = 8
    ) -> List[MatchResult]:
        """Filtra e classifica os aplicativos por relevância com alta performance."""
        query = " ".join(normalize_text(query).split())

        # SE A BUSCA ESTIVER VAZIA: Mostra os mais usados (MRU) ou os primeiros da lista
        if not query:
            return self._get_default_results(apps, limit)

        results: List[MatchResult] = []
        for app in apps:
            base_score = search_score(query, app.search_name, app.search_metadata,
                                      app.search_description, app.search_aliases)
            if not base_score:
                continue
            # Adjustment requests favor the matching settings panel over media players.
            if (2000 <= base_score < 3000 and app.is_setting
                    and set(search_text(query).split()) & {"ajustar", "mudar", "configurar", "alterar",
                                                          "adjust", "change", "configure", "regler", "changer", "cambiar"}
                    and search_score(query, app.search_name, aliases=intent_metadata(app.name)) >= 2000):
                base_score = 2099

            # Usage orders relevant matches; it cannot admit an unrelated app.
            history_bonus = min(self.history.get_count(app.id), 100) / 1000
            learned_bonus = min(self.history.get_query_count(app.id, query), 20) / 40
            results.append(MatchResult(app, base_score + history_bonus + learned_bonus))

        # Ordena do mais relevante para o menos relevante
        results.sort(key=result_key)
        return results if limit is None else results[:limit]

    def _get_default_results(
        self, apps: List[AppEntry], limit: int
    ) -> List[MatchResult]:
        """Retorna os programas favoritos/mais usados quando nada foi digitado ainda."""
        apps = [app for app in apps if not app.is_setting]
        app_dict = {app.id: app for app in apps}
        most_used_ids = [app_id for app_id in self.history.get_most_used_ids(None)
                         if app_id in app_dict][:limit]

        results: List[MatchResult] = []

        # Adiciona primeiro os mais usados
        for app_id in most_used_ids:
            if app_id in app_dict:
                results.append(MatchResult(entry=app_dict[app_id], score=100.0))

        # Completa com apps da lista padrão se não houver histórico suficiente
        for app in apps:
            if limit is not None and len(results) >= limit:
                break
            if app not in [r.entry for r in results]:
                results.append(MatchResult(entry=app, score=50.0))

        return results
