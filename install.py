#!/usr/bin/env python3
"""Instala para o usuário atual, mantendo o código neste diretório."""
import argparse
import os
from pathlib import Path
import shlex
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def check_native_dependencies():
    if sys.platform != "linux" or sys.version_info < (3, 10):
        raise RuntimeError("Use Linux com Python 3.10 ou superior.")
    try:
        import gi
        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
        gi.require_foreign("cairo")
        from gi.repository import Adw, Gtk
    except (ImportError, ValueError) as error:
        raise RuntimeError(
            "Instale PyGObject, Cairo, GTK 4 e libadwaita pelo sistema. "
            "Consulte a seção Instalar do README.md. Detalhe: " + str(error)
        ) from error
    if (Adw.get_major_version(), Adw.get_minor_version()) < (1, 4):
        raise RuntimeError("libadwaita 1.4 ou superior é necessária; atualize sua distribuição.")
    print(f"GTK {Gtk.get_major_version()}.{Gtk.get_minor_version()}, "
          f"libadwaita {Adw.get_major_version()}.{Adw.get_minor_version()}: OK")


def install():
    if os.geteuid() == 0:
        raise RuntimeError("Execute sem sudo; a instalação pertence ao seu usuário.")
    check_native_dependencies()
    environment = ROOT / ".venv"
    python = environment / "bin" / "python"
    subprocess.run([sys.executable, "-m", "venv", "--system-site-packages", str(environment)], check=True)
    subprocess.run([str(python), "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")], check=True)
    # Só publique os atalhos depois de validar o interpretador instalado.
    subprocess.run([str(python), str(ROOT / "install.py"), "--check"], check=True)
    subprocess.run([str(python), "-c", "import rapidfuzz, pint"], check=True)

    from gi.repository import GLib
    from src import APP_ID
    from src.desktop import launcher_entry

    binary = Path.home() / ".local" / "bin" / "spot-launcher"
    desktop = Path(GLib.get_user_data_dir()) / "applications" / (APP_ID + ".desktop")
    binary.parent.mkdir(parents=True, exist_ok=True)
    desktop.parent.mkdir(parents=True, exist_ok=True)
    if binary.is_symlink() or desktop.is_symlink():
        raise RuntimeError("Um atalho de destino é um link simbólico; revise-o antes de reinstalar.")
    binary.write_text(
        "#!/bin/sh\nexec " + shlex.quote(str(python)) + " "
        + shlex.quote(str(ROOT / "run.py")) + ' "$@"\n', encoding="utf-8",
    )
    binary.chmod(0o755)
    desktop.write_text(launcher_entry(python), encoding="utf-8")
    print(f"Instalado. Abra SpotLauncher no menu de aplicativos ou execute {binary}.")
    print(f"Mantenha o projeto em {ROOT}; após movê-lo, execute o instalador novamente.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="valida dependências nativas sem instalar")
    args = parser.parse_args()
    try:
        if args.check:
            check_native_dependencies()
        else:
            install()
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"Instalação interrompida: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
