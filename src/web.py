"""Prepara pesquisas sem acessar a rede enquanto o usuário digita."""
from dataclasses import dataclass
import re
from urllib.parse import urlencode
from src.search_commands import command_query


@dataclass(frozen=True)
class WebSearch:
    query: str
    explicit: bool

    @property
    def url(self) -> str:
        return "https://www.google.com/search?" + urlencode({"q": self.query})


def web_search(query: str):
    text = query.strip()
    if not text:
        return None
    command = re.match(r"^(?:g|google|web)(?:\s+(.*)|$)", text, re.IGNORECASE | re.DOTALL)
    if command:
        text = (command.group(1) or "").strip()
        if not text:
            return None
    return WebSearch(text, explicit=command is not None)


def map_destination(query: str):
    query = command_query(query) or query
    match = re.match(r"^(?:mapa|mapas|map|maps|carte|cartes)\s+(.+?)\s*$", query.strip(), re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    return match.group(1)


def map_search(query: str):
    destination = map_destination(query)
    if destination:
        return "https://www.google.com/maps/search/?" + urlencode({"api": 1, "query": destination})


def dictionary_search(query: str):
    query = command_query(query) or query
    query = re.sub(r"^(?:o que significa|qual (?:é|e) o significado de|significado de)\s+(.+?)\?*$",
                   r"defina \1", query.strip(), flags=re.IGNORECASE)
    query = re.sub(r"^what does\s+(.+?)\s+mean\?*$",
                   r"define \1", query, flags=re.IGNORECASE)
    match = re.fullmatch(
        r"(defina|definir|define|dicionário|dicionario|dict|dictionary|diccionario|definición|definicion|dictionnaire|définir|définition)\s+(.+)",
        query.strip(), re.IGNORECASE)
    if match:
        from src import LANGUAGE
        command, word = match.groups()
        languages = {"defina": "pt", "dicionário": "pt", "dicionario": "pt",
                     "define": "en", "dictionary": "en", "diccionario": "es",
                     "definición": "es", "definicion": "es", "dictionnaire": "fr",
                     "définir": "fr", "définition": "fr"}
        language = languages.get(command.lower(), LANGUAGE)
        explicit = re.fullmatch(r"(pt|en|es|fr)\s*:\s*(.*)", word, re.IGNORECASE)
        if explicit:
            language, word = explicit.groups()
        word = word.strip()
        if not word:
            return None
        language = language.lower() if language.lower() in ("pt", "en", "es", "fr") else "en"
        return word, f"https://{language}.wiktionary.org/w/index.php?" + urlencode({"search": word})


def translation_search(query: str):
    from src import LANGUAGE
    from src.translation import LANGUAGE_ALIASES

    flags = re.IGNORECASE | re.DOTALL
    language = "(?:" + "|".join(map(re.escape, LANGUAGE_ALIASES)) + ")"
    body = (command_query(query) or query).strip()
    command = re.fullmatch(
        r"(?:traduza|traduzir|traduz|tradução|traducao|translate|traducir|traduire)\s+(.+)",
        body, flags)
    if command:
        body = command.group(1)
        match = re.fullmatch(
            rf"(?:({language})\s*:\s*)?({language})\s*:\s*(.*)", body, flags)
        if match:
            source, target, text = match.groups()
            if text.strip():
                return text.strip(), LANGUAGE_ALIASES[source.lower()] if source else LANGUAGE.lower(), LANGUAGE_ALIASES[target.lower()]
            return None
        match = re.fullmatch(
            rf"(?:para|to|a|en)\s+({language})\s*:\s*(.+)", body, flags)
        if match:
            target, text = match.groups()
            return text.strip(), LANGUAGE.lower(), LANGUAGE_ALIASES[target.lower()]
    question = re.fullmatch(
        r"(?:como (?:se diz|dizer|falar)|how (?:do you say|to say))\s+(.+?)\s*\??", body, flags)
    if question:
        body = question.group(1)
    match = re.fullmatch(
        rf"(.+?)\s+(?:em|para|to|in|en)\s+({language})\s*\??", body, flags)
    if not match:
        return None
    text, target = match.groups()
    source = None
    if command:
        explicit = re.fullmatch(rf"(.+?)\s+(?:de|from)\s+({language})", text, flags)
        if explicit:
            text, source = explicit.groups()
    if text.strip():
        return text.strip(), LANGUAGE_ALIASES[source.lower()] if source else LANGUAGE.lower(), LANGUAGE_ALIASES[target.lower()]
