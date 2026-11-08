#!/usr/bin/env python3
import os
from pathlib import Path
import sys

from src import LANGUAGE, configure_native_locale


def main():
    # GTK and Gio read language preferences during initialization.
    session_language = os.environ.get("LANGUAGE")
    os.environ["LANGUAGE"] = "pt_BR:pt" if LANGUAGE == "pt" else LANGUAGE
    # The launcher draws text and icons. Avoid a resident GPU renderer for this window.
    use_cairo = "GSK_RENDERER" not in os.environ
    if use_cairo:
        os.environ["GSK_RENDERER"] = "cairo"

    import gi
    gi.require_version("Gdk", "4.0")
    from gi.repository import Gdk
    if os.getenv("DISPLAY") and not os.getenv("GDK_BACKEND"):
        Gdk.set_allowed_backends("x11,wayland")
    from src.app import SpotApplication

    configure_native_locale()
    app = SpotApplication()
    if use_cairo:
        # Restore the environment before the launcher can open other applications.
        def window_added(app, window):
            window.connect("map", lambda *_: os.environ.pop("GSK_RENDERER", None))
        app.connect("window-added", window_added)
    status = app.run(sys.argv)
    if session_language is None:
        os.environ.pop("LANGUAGE", None)
    else:
        os.environ["LANGUAGE"] = session_language
    if app.reopen_preferences:
        os.execv(sys.executable, [sys.executable, str(Path(__file__).resolve()), "--preferences"])
    return status


if __name__ == "__main__":
    sys.exit(main())
