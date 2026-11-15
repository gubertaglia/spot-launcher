from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import install
import gi
gi.require_version("Adw", "1")
from src.desktop import quote_argument


class InstallTests(unittest.TestCase):
    def test_installs_quoted_launcher_and_desktop_without_touching_user_data(self):
        from gi.repository import GLib
        with TemporaryDirectory(prefix="spot install ") as directory:
            home = Path(directory)
            root = home / "project $ with % spaces"
            root.mkdir()
            with patch.object(install, "ROOT", root), \
                 patch("install.os.geteuid", return_value=1000), \
                 patch("install.check_native_dependencies"), \
                 patch("install.subprocess.run") as run, \
                 patch("install.Path.home", return_value=home), \
                 patch("gi.repository.GLib.get_user_data_dir", return_value=str(home / "data")), \
                 patch("src.desktop.__file__", str(root / "src/desktop.py")):
                install.install()
            binary = home / ".local/bin/spot-launcher"
            desktop = home / "data/applications/org.spot.Launcher.desktop"
            self.assertEqual(binary.stat().st_mode & 0o777, 0o755)
            # Execute the installed shell wrapper with a disposable interpreter.
            python = root / ".venv/bin/python"
            python.parent.mkdir(parents=True)
            python.symlink_to(sys.executable)
            (root / "run.py").write_text("import sys; print(repr(sys.argv[1:]))\n")
            result = subprocess.run([str(binary), "--toggle", "argument with spaces"],
                                    check=True, capture_output=True, text=True)
            self.assertEqual(result.stdout.strip(), "['--toggle', 'argument with spaces']")
            entry = GLib.KeyFile()
            entry.load_from_file(str(desktop), GLib.KeyFileFlags.NONE)
            command = entry.get_string("Desktop Entry", "Exec")
            self.assertIn(quote_argument(python), command)
            self.assertIn(quote_argument(root / "run.py"), command)
            self.assertNotIn("--daemon", command)
            self.assertEqual(run.call_args_list[0].args[0],
                             [sys.executable, "-m", "venv", "--system-site-packages", str(root / ".venv")])
            self.assertEqual(run.call_count, 4)

    def test_failed_dependency_install_does_not_publish_shortcuts(self):
        with TemporaryDirectory() as directory, \
             patch.object(install, "ROOT", Path(directory)), \
             patch("install.os.geteuid", return_value=1000), \
             patch("install.check_native_dependencies"), \
             patch("install.subprocess.run", side_effect=subprocess.CalledProcessError(1, "venv")), \
             patch("install.Path.home", return_value=Path(directory)):
            with self.assertRaises(subprocess.CalledProcessError):
                install.install()
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_refuses_root_before_any_write(self):
        with patch("install.os.geteuid", return_value=0), patch("install.subprocess.run") as run:
            with self.assertRaisesRegex(RuntimeError, "sem sudo"):
                install.install()
            run.assert_not_called()

    def test_native_check_requires_supported_adwaita(self):
        with patch("gi.repository.Adw.get_major_version", return_value=1), \
             patch("gi.repository.Adw.get_minor_version", return_value=2):
            with self.assertRaisesRegex(RuntimeError, "1.4"):
                install.check_native_dependencies()

    def test_desktop_quotes_round_trip_through_gio(self):
        from gi.repository import Gio, GLib
        argument = 'spaces $ ` " \\ % ; café'
        entry = GLib.KeyFile()
        entry.set_string("Desktop Entry", "Type", "Application")
        entry.set_string("Desktop Entry", "Name", "Quote test")
        entry.set_string("Desktop Entry", "Exec", "/bin/echo " + quote_argument(argument))
        app = Gio.DesktopAppInfo.new_from_keyfile(entry)
        self.assertIsNotNone(app)
        with TemporaryDirectory() as directory:
            output = Path(directory) / "args"
            script = Path(directory) / "capture.py"
            script.write_text("import pathlib,sys; pathlib.Path(sys.argv[1]).write_text(sys.argv[2])")
            entry.set_string("Desktop Entry", "Exec", " ".join(map(quote_argument,
                             [sys.executable, script, output, argument])))
            self.assertTrue(Gio.DesktopAppInfo.new_from_keyfile(entry).launch())
            import time
            deadline = time.monotonic() + 3
            while not output.exists() and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertEqual(output.read_text(), argument)
