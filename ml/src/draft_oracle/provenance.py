"""Shared artifact provenance helpers."""

from __future__ import annotations

import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def git_state(repo_dir: Path | None = None) -> tuple[str | None, bool | None]:
    """Return current commit and dirty-tree state, or ``None`` when git is unavailable."""
    cwd = None if repo_dir is None else str(repo_dir)
    try:
        sha_run = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
        )
        status_run = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=normal"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):  # pragma: no cover - env dependent
        return None, None
    return sha_run.stdout.strip() or None, bool(status_run.stdout.strip())


def add_git_provenance(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Copy manifest and stamp current commit plus explicit dirty-tree marker."""
    out = dict(manifest)
    sha, dirty = git_state()
    if out.get("git_sha") is None:
        out["git_sha"] = sha
    out["git_dirty"] = dirty
    return out
