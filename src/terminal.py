import shutil
from typing import List, Optional

# Lista de emuladores de terminal por ordem de preferência no GNOME/Fedora
KNOWN_TERMINALS = [
    ("ptyxis", ["ptyxis", "--"]),
    ("gnome-terminal", ["gnome-terminal", "--"]),
    ("kgx", ["kgx", "-e"]),
    ("alacritty", ["alacritty", "-e"]),
    ("kitty", ["kitty"]),
    ("xterm", ["xterm", "-e"]),
]


def get_default_terminal() -> Optional[List[str]]:
    """Identifica o emulador de terminal disponível no sistema operacional."""
    for term_binary, prefix in KNOWN_TERMINALS:
        if shutil.which(term_binary):
            return prefix
    return None
