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
    if info.returncode == 0:
        result = subprocess.run(("gnome-extensions", "enable", UUID), capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "gnome-extensions failed")
        return True
    source = Path(__file__).resolve().parents[1] / "data" / "gnome-extension"
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
