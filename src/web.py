"""Prepara pesquisas sem acessar a rede enquanto o usuário digita."""
from dataclasses import dataclass
import re
from urllib.parse import urlencode


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
