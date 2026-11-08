"""Atualização de instalações feitas com Git."""
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def git(*args):
    return subprocess.run(
        ["git", "-C", str(ROOT), *args], check=True, capture_output=True,
        text=True, timeout=30, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    ).stdout.strip()


def check_update():
    try:
        upstream = git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}")
        remote, branch = upstream.split("/", 1)
        git("fetch", "--no-tags", remote, branch)
        current = git("rev-parse", "HEAD")
        available = git("rev-parse", "FETCH_HEAD")
        if current != available:
            git("merge-base", "--is-ancestor", current, available)
            return available
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return None


def install_update(commit):
    try:
        if git("status", "--porcelain", "--untracked-files=no"):
            return False
        git("merge", "--ff-only", commit)
        return True
    except (OSError, subprocess.SubprocessError):
        return False
