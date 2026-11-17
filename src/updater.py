"""Atualização de instalações feitas com Git."""
import os
import re
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def git(*args):
    if not (ROOT / ".git").exists():
        raise ValueError("A instalação não é a raiz de um repositório Git")
    return subprocess.run(
        ["git", "-C", str(ROOT), *args], check=True, capture_output=True,
        text=True, timeout=30, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    ).stdout.strip()


def check_update():
    try:
        upstream = git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}")
        remote, branch = upstream.split("/", 1)
        git("fetch", "--no-tags", "--no-write-fetch-head", remote, branch)
        current = git("rev-parse", "HEAD")
        available = git("rev-parse", "@{upstream}")
        if current != available:
            git("merge-base", "--is-ancestor", current, available)
            return available
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return None


def install_update(commit):
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", commit):
        return False
    try:
        current = git("rev-parse", "HEAD")
        if commit == current or commit != git("rev-parse", "@{upstream}"):
            return False
        git("merge-base", "--is-ancestor", current, commit)
        if git("status", "--porcelain", "--untracked-files=no"):
            return False
        git("merge", "--ff-only", "--no-overwrite-ignore", commit)
        return True
    except (OSError, ValueError, subprocess.SubprocessError):
        return False
