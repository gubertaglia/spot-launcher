from dataclasses import dataclass
import time
from typing import List

from rapidfuzz import fuzz
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
        query = query.strip().lower()

        # SE A BUSCA ESTIVER VAZIA: Mostra os mais usados (MRU) ou os primeiros da lista
        if not query:
            return self._get_default_results(apps, limit)

        results: List[MatchResult] = []

        for app in apps:
            name_lower = app.name.lower()
            id_lower = app.id.lower()

            # 1. Correspondência exata no início do nome ganha prioridade máxima
            if name_lower.startswith(query):
                base_score = 100.0 + (len(query) / len(name_lower)) * 30.0
            # 2. Substring direta no nome
            elif query in name_lower:
                base_score = 75.0 + (len(query) / len(name_lower)) * 20.0
            # 3. Correspondência difusa (Fuzzy) no nome
            else:
                fuzzy_ratio = fuzz.ratio(query, name_lower)
                partial_ratio = fuzz.partial_ratio(query, name_lower)
                base_score = max(fuzzy_ratio, partial_ratio * 0.8)

            # 4. Bônus por correspondência em palavras-chave (ex: digitar "editor" acha o VSCode)
            keyword_bonus = 0.0
            for kw in app.keywords:
                if query in kw.lower():
                    keyword_bonus = 35.0
                    break

            # 5. Bônus por correspondência no comando ou ID (ex: digitar "code" acha o VSCode)
            id_bonus = 25.0 if query in id_lower else 0.0

            # 6. Bônus por frequência de uso (Histórico MRU)
            usage_count = self.history.get_count(app.id)
            history_bonus = min(usage_count * 5.0, 40.0)

            # Pontuação final
            total_score = max(base_score, keyword_bonus, id_bonus) + history_bonus

            # Apenas resultados com relevância mínima aceitável entram
            if total_score > 45.0:
                results.append(MatchResult(entry=app, score=total_score))

        # Ordena do mais relevante para o menos relevante
        results.sort(key=lambda r: r.score, reverse=True)
        return results if limit is None else results[:limit]

    def _get_default_results(
        self, apps: List[AppEntry], limit: int
    ) -> List[MatchResult]:
        """Retorna os programas favoritos/mais usados quando nada foi digitado ainda."""
        most_used_ids = self.history.get_most_used_ids(limit)
        app_dict = {app.id: app for app in apps}

        results: List[MatchResult] = []

        # Adiciona primeiro os mais usados
        for app_id in most_used_ids:
            if app_id in app_dict:
                results.append(MatchResult(entry=app_dict[app_id], score=100.0))

        # Completa com apps da lista padrão se não houver histórico suficiente
        for app in apps:
            if len(results) >= limit:
                break
            if app not in [r.entry for r in results]:
                results.append(MatchResult(entry=app, score=50.0))

        return results
