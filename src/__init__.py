import gettext
import json
import locale
import os
from pathlib import Path

VERSION = "1.4.0"
APP_ID = "org.spot.Launcher"
LOCALE_DIR = Path(__file__).resolve().parents[1] / "data" / "locales"


def system_language():
    """Resolve desktop language preferences to a supported message catalog."""
    candidates = os.getenv("LANGUAGE", "").split(":")
    for key in ("LC_ALL", "LC_MESSAGES", "GDM_LANG", "LANG"):
        value = os.getenv(key, "")
        if value and value.split(".")[0].upper() not in ("C", "POSIX"):
            candidates.append(value)
            break
    for candidate in candidates:
        language = candidate.split("@")[0].split(".")[0].replace("-", "_").split("_")[0].lower()
        if language in ("pt", "en", "es", "fr"):
            return language
        if language in ("c", "posix"):
            break
    return "en"


def configured_language():
    config_home = Path(os.getenv("XDG_CONFIG_HOME") or Path.home() / ".config")
    try:
        with (config_home / "spot-launcher" / "config.json").open(encoding="utf-8") as stream:
            language = json.load(stream).get("language", "system")
        if language in ("pt", "en", "es", "fr"):
            return language
    except (OSError, ValueError, AttributeError, TypeError):
        pass
    return system_language()


LANGUAGE = configured_language()
# Portuguese is the source language of the gettext messages.
_ = gettext.translation(APP_ID, LOCALE_DIR, languages=[LANGUAGE], fallback=True).gettext

_date_format = "%x"


def configure_native_locale():
    global _date_format
    _date_format = locale.nl_langinfo(locale.D_FMT)
    regions = {"pt": "pt_BR", "en": "en_US", "es": "es_ES", "fr": "fr_FR"}
    for category in (locale.LC_MESSAGES, locale.LC_TIME):
        # Keep the regional variant when it already uses the chosen language.
        current = locale.setlocale(category)
        if current.split("_")[0] == LANGUAGE:
            continue
        try:
            locale.setlocale(category, regions[LANGUAGE] + ".UTF-8")
        except locale.Error:
            pass  # The launcher's bundled translations are still available.


def regional_date_format():
    return _date_format


__all__ = ["_", "APP_ID", "LANGUAGE"]
