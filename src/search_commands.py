"""Recognize command heads without rewriting their arguments."""
from dataclasses import dataclass
import re

from src.search import search_text, word_distance


# Each alias replaces only the command head. The remainder keeps its original bytes.
COMMANDS = {
    "calendar": ("calendario", "calendar", "calendrier", "agenda", "abrir calendario", "open calendar", "ouvrir le calendrier", "abrir el calendario"),
    "clipboard": ("clipboard", "clipboard history", "historico da area de transferencia", "area de transferencia", "historial del portapapeles", "portapapeles", "historique du presse-papiers", "presse-papiers"),
    "emoji": ("emoji", "emojis"),
    "reiniciar spotlauncher": tuple(f"{verb} {name}" for verb in ("reiniciar", "restart", "reboot", "reset", "redemarrer") for name in ("spot", "spotlauncher", "launcher")),
    "fechar spotlauncher": tuple(f"{verb} {name}" for verb in ("fechar", "close", "encerrar", "sair", "quit", "cerrar", "fermer", "quitter") for name in ("spot", "spotlauncher", "launcher")),
    "mapa": ("mapa", "mapas", "map", "maps", "carte", "cartes", "mapa de", "map of", "carte de", "buscar no mapa", "buscar en el mapa", "show map of"),
    "defina": ("defina", "dicionario", "o que significa", "qual e o significado de", "significado de"),
    "define": ("define", "dictionary"),
    "dict": ("dict",),
    "definir": ("definir",),
    "definición": ("definicion", "diccionario", "que significa", "cual es el significado de"),
    "définition": ("definition", "définir", "definir en francais", "dictionnaire", "que signifie", "que veut dire"),
    "traduza": ("traduza", "traduzir", "traduz", "traducao", "translate", "traducir", "traduire", "traduce", "traduisez"),
    "como se diz": ("como se diz", "como dizer", "como falar", "como se dice", "comment dit on", "comment dire"),
    "clima em": ("clima em", "tempo em", "previsao do tempo em", "weather in", "weather for", "what is the weather in", "what's the weather like in", "clima en", "tiempo en", "que tiempo hace en", "meteo a", "meteo en", "prevision du temps a", "quel temps fait il a"),
    "hora em": ("hora em", "horas em", "que horas sao em", "time in", "what time is it in", "hora en", "que hora es en", "heure a", "quelle heure est il a"),
    "": ("converter", "convert", "convertir", "convertissez"),
    "google": ("google", "web", "pesquisar na web", "search the web for", "buscar en internet", "rechercher sur internet"),
}
FILE_COMMANDS = {
    "fotos": "foto fotos fotografia fotografias imagem imagens imagen imagenes photo photos image images picture pictures photographie photographies",
    "videos": "video videos filme filmes pelicula peliculas movie movies film films",
    "documentos": "documento documentos document documents",
    "audios": "audio audios musica musicas music musique musiques sonido sonidos son sons sound sounds",
    "arquivos": "arquivo arquivos archivo archivos file files fichier fichiers",
}
COMMANDS.update({target: tuple(aliases.split()) for target, aliases in FILE_COMMANDS.items()})
HEADS = tuple((alias, search_text(alias), target) for target, aliases in COMMANDS.items() for alias in aliases)
WHOLE_COMMANDS = frozenset(("calendar", "clipboard", "emoji", "reiniciar spotlauncher", "fechar spotlauncher"))


@dataclass(frozen=True)
class CommandSuggestion:
    query: str
    score: float = 1099


def command_query(query, fuzzy=False):
    """Return an exact query or a fuzzy suggestion that requires activation."""
    if query.lstrip().startswith(">"):
        return None
    words = list(re.finditer(r"[^\W_]+", query, re.UNICODE))
    if not words:
        return None
    candidates = []
    for original_alias, alias, target in HEADS:
        count = len(alias.split())
        if count > len(words):
            continue
        end = words[count - 1].end()
        head = search_text(query[:end])
        if len(head.split()) != count:
            continue
        remainder = query[end:]
        if target in FILE_COMMANDS:
            if remainder.strip() and not remainder.lstrip().startswith(":"):
                continue
        elif remainder and not remainder[0].isspace() and remainder.strip(" ?!"):
            continue
        if target in WHOLE_COMMANDS and remainder.strip():
            continue
        if target not in WHOLE_COMMANDS and target not in FILE_COMMANDS and not remainder.strip():
            continue
        if head == alias:
            distance = 0
        elif fuzzy:
            distances = [word_distance(left, right) for left, right in zip(head.split(), alias.split())]
            if any(value is None for value in distances):
                continue
            distance = sum(distances)
            if distance > (2 if len(alias) >= 8 else 1):
                continue
        else:
            continue
        # Numeric conversion commands must not consume a normal app/file query.
        if not target and not re.match(r"\s*[+-]?(?:\d|[.,]\d)", remainder):
            continue
        corrected = (target + remainder).strip()
        if len(alias.split()) > 1 and target in ("defina", "define", "dict", "definición", "définition"):
            corrected = corrected.rstrip("?").rstrip()
        candidates.append((distance, -count, query[:end].strip().casefold() != original_alias.casefold(), corrected))
    if not candidates:
        return None
    candidates.sort()
    best = candidates[0][:3]
    choices = {candidate[3] for candidate in candidates if candidate[:3] == best}
    if len(choices) != 1:
        return None
    corrected = choices.pop()
    return CommandSuggestion(corrected, 1099 - best[0]) if fuzzy else corrected


def command_suggestion(query):
    if command_query(query) is not None:
        return None
    return command_query(query, fuzzy=True)
