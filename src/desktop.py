"""Entradas desktop com as regras de escape do formato freedesktop."""
from pathlib import Path

from gi.repository import GLib
from src import _


def quote_argument(argument):
    escaped = "".join("\\" + char if char in '\\"`$' else char for char in str(argument))
    return '"' + escaped.replace("%", "%%") + '"'


def launcher_entry(python, *arguments):
    command = " ".join(quote_argument(argument) for argument in (
        python, Path(__file__).resolve().parents[1] / "run.py", *arguments,
    ))
    entry = GLib.KeyFile()
    for key, value in {
        "Type": "Application", "Name": "SpotLauncher",
        "Comment": _("Iniciador de aplicativos rápido e nativo"), "Exec": command,
        "Icon": "system-search", "Terminal": "false", "Categories": "Utility;",
        "X-GNOME-Autostart-enabled": "true",
    }.items():
        entry.set_string("Desktop Entry", key, value)
    return entry.to_data()[0]
