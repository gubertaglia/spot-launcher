import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from src import updater


class UpdaterTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        self.remote = root / "remote"
        self.clone = root / "clone"
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.remote)], check=True)
        self.git(self.remote, "config", "user.email", "test@example.com")
        self.git(self.remote, "config", "user.name", "Test")
        (self.remote / "file").write_text("first")
        self.git(self.remote, "add", "file")
        self.git(self.remote, "commit", "-qm", "first")
        subprocess.run(["git", "clone", "-q", str(self.remote), str(self.clone)], check=True)
        self.root_patch = patch.object(updater, "ROOT", self.clone)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)

    def git(self, directory, *args):
        return subprocess.run(["git", "-C", str(directory), *args], check=True,
                              capture_output=True, text=True).stdout.strip()

    def test_check_install_and_preserve_local_changes(self):
        self.assertIsNone(updater.check_update())
        (self.remote / "file").write_text("second")
        self.git(self.remote, "commit", "-qam", "second")
        commit = updater.check_update()
        self.assertEqual(commit, self.git(self.remote, "rev-parse", "HEAD"))
        (self.clone / "file").write_text("local")
        self.assertFalse(updater.install_update(commit))
        self.assertEqual((self.clone / "file").read_text(), "local")
        self.git(self.clone, "restore", "file")
        self.assertTrue(updater.install_update(commit))
        self.assertEqual((self.clone / "file").read_text(), "second")
        self.assertIsNone(updater.check_update())

    def test_missing_upstream_is_safe(self):
        self.git(self.clone, "branch", "--unset-upstream")
        self.assertIsNone(updater.check_update())

    def test_ignored_collision_is_preserved(self):
        (self.clone / "local.pyc").write_text("private")
        (self.clone / ".git/info/exclude").write_text("*.pyc\n")
        (self.remote / "local.pyc").write_text("upstream")
        self.git(self.remote, "add", "-f", "local.pyc")
        self.git(self.remote, "commit", "-qm", "new tracked path")
        commit = updater.check_update()
        self.assertFalse(updater.install_update(commit))
        self.assertEqual((self.clone / "local.pyc").read_text(), "private")
