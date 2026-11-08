"""Local search normalization and relevance shared by all result types."""
from functools import lru_cache
import re
import unicodedata

from rapidfuzz.distance import DamerauLevenshtein


def normalize_text(text):
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


@lru_cache(maxsize=32768)
def search_text(text):
    return " ".join(re.findall(r"(?:[^\W_]|[+#$€£¥°])+", normalize_text(text), re.UNICODE))


STOP_WORDS = frozenset("""
na nos nas por para sur au aux en
abrir abra quero mudar alterar configurar ajustar o a os as de do da dos das meu minha
open change configure adjust i want to the my of in
ouvrir regler ajuster changer je veux le la les mon ma mes du des un une
cambiar abrir ajustar configurar quiero el los las mi mis del una uno
""".split())

# shortcut: curated task vocabulary, extend when a supported task has no metadata match.
INTENTS = (
    "browser|web browser|navegador|navegador web|navegar na internet|browse the internet|navegar por internet|navigateur|naviguer sur internet",
    "editor|text editor|editor de texto|editar texto|edit text|editer du texte|editeur de texte|editeur",
    "files|file manager|arquivos|gerenciador de arquivos|archivos|gestor de archivos|fichiers|gestionnaire de fichiers",
    "audio|sound|volume|som|som do sistema|saida de audio|microfone|microphone|sonido|son|haut parleur",
    "network|wifi|wi fi|rede|internet|red|reseau|wireless",
    "settings|preferences|configuracoes|configuracao|preferencias|ajustes|configuracion|parametres|reglages",
)
INTENTS = tuple(tuple(search_text(alias) for alias in group.split("|")) for group in INTENTS)


@lru_cache(maxsize=8192)
def intent_metadata(text):
    text = search_text(text)
    padded = " " + text + " "
    return "|".join(alias for group in INTENTS
                    if any(" " + alias + " " in padded for alias in group)
                    for alias in group)


# Ignore command words only when there is a subject left to search.
@lru_cache(maxsize=1024)
def query_terms(query):
    words = search_text(query).split()
    return tuple(word for word in words if word not in STOP_WORDS) or tuple(words)


def word_distance(term, candidate):
    if term == candidate:
        return 0
    # Short fragments must match literally; fuzzy short words are noisy.
    allowance = 2 if len(term) >= 8 else 1 if len(term) >= 4 else 0
    if not allowance or abs(len(term) - len(candidate)) > allowance:
        return None
    distance = DamerauLevenshtein.distance(term, candidate, score_cutoff=allowance)
    return distance if distance <= allowance else None


def search_score(query, name, metadata="", description="", aliases=""):
    """Five non-overlapping bands; fractional space is reserved for usage ties."""
    query, name = search_text(query), search_text(name)
    if not query:
        return 0
    if query == name:
        return 5000
    if name.startswith(query):
        return 4000 if len(query) <= 2 else 4000 + min(99, int(100 * len(query) / len(name)))
    if len(query) <= 2:
        return 0
    terms = query_terms(query)
    if terms == tuple(query.split()) and all(term in name for term in terms):
        return 3000 + min(99, int(100 * sum(map(len, terms)) / max(1, len(name))))
    metadata = " ".join((name, search_text(metadata)))
    if all(term in metadata for term in terms):
        return 2090
    if all(term in metadata + " " + search_text(description) for term in terms):
        return 2050
    # Match a complete task phrase, never unrelated words from different aliases.
    if aliases and any(set(query_terms(alias)) == set(terms) for alias in aliases.split("|")):
        return 2020
    candidates = (metadata + " " + search_text(aliases)).split()
    distances = []
    for term in terms:
        if term in metadata:
            distances.append(0)
            continue
        distance = min((value for word in candidates
                        if (value := word_distance(term, word)) is not None), default=None)
        if distance is None:
            return 0
        distances.append(distance)
    return 1000 + max(0, 99 - sum(distances))


def label_score(query, title, aliases=()):
    """Short queries use the visible title; partial aliases stay below name prefixes."""
    score = search_score(query, title)
    query = search_text(query)
    if len(query) <= 2:
        return score
    for alias in aliases:
        alias_score = 5000 if query == search_text(alias) else min(2090, search_score(query, alias))
        score = max(score, alias_score)
    return score


def result_key(item):
    """A deterministic ordering also used when merging different providers."""
    entry = getattr(item, "entry", item)
    name = getattr(entry, "name", getattr(entry, "title", ""))
    identity = getattr(entry, "id", getattr(entry, "path", name))
    return (-item.score, 1 if hasattr(entry, "path") else 0, search_text(name), identity)
