"""Install the optional GNOME Shell integration."""
import os
from pathlib import Path
import subprocess
import tempfile
import zipfile

UUID = "spot-launcher@spot.local"


def enable_integration():
    """Return False when installation needs a new GNOME session."""
    if "GNOME" not in os.environ.get("XDG_CURRENT_DESKTOP", "").upper():
        raise RuntimeError("GNOME Shell required")
    info = subprocess.run(("gnome-extensions", "info", UUID), capture_output=True, text=True, timeout=30)
    source = Path(__file__).resolve().parents[1] / "data" / "gnome-extension"
    installed = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "gnome-shell/extensions" / UUID
    try:
        current = all((installed / name).read_bytes() == (source / name).read_bytes()
                      for name in ("metadata.json", "extension.js"))
    except OSError:
        current = False
    if info.returncode == 0 and current:
        result = subprocess.run(("gnome-extensions", "enable", UUID), capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "gnome-extensions failed")
        return True
    with tempfile.TemporaryDirectory() as directory:
        archive = Path(directory) / "extension.zip"
        with zipfile.ZipFile(archive, "w") as bundle:
            for name in ("metadata.json", "extension.js"):
                bundle.write(source / name, name)
        for command in (("install", "--force", str(archive)),):
            result = subprocess.run(("gnome-extensions", *command), capture_output=True, text=True, timeout=30)
            if result.returncode:
                raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "gnome-extensions failed")
    # Local installation does not make a running Shell discover a new extension.
    return False

SHORTCUT_PATH = '/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/spot-launcher/'


def shortcut_settings():
    from gi.repository import Gio
    source = Gio.SettingsSchemaSource.get_default()
    if not source or not source.lookup('org.gnome.settings-daemon.plugins.media-keys.custom-keybinding', True):
        return None, None
    return (Gio.Settings.new('org.gnome.settings-daemon.plugins.media-keys'),
            Gio.Settings.new_with_path('org.gnome.settings-daemon.plugins.media-keys.custom-keybinding', SHORTCUT_PATH))


def set_shortcut(binding):
    from gi.repository import Gio
    settings, own = shortcut_settings()
    if not settings:
        raise RuntimeError('GNOME shortcuts unavailable')
    paths = settings.get_strv('custom-keybindings')
    for path in paths:
        if path != SHORTCUT_PATH:
            other = Gio.Settings.new_with_path('org.gnome.settings-daemon.plugins.media-keys.custom-keybinding', path)
            if binding and other.get_string('binding') == binding:
                raise ValueError('shortcut already in use')
    own.set_string('name', 'Spot Launcher')
    own.set_string('command', 'gapplication action org.spot.Launcher toggle')
    own.set_string('binding', binding)
    if binding and SHORTCUT_PATH not in paths:
        settings.set_strv('custom-keybindings', paths + [SHORTCUT_PATH])
    elif not binding and SHORTCUT_PATH in paths:
        settings.set_strv('custom-keybindings', [path for path in paths if path != SHORTCUT_PATH])
