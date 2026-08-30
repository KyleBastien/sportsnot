"""Smoke test for the ``oracle`` CLI entry point."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from typer.testing import CliRunner

from draft_oracle import __version__
from draft_oracle.cli.project import app

runner = CliRunner()


def test_version_command() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_draft_commands_start_without_training_or_network_stack() -> None:
    code = """
import builtins
import sys

blocked_roots = {"lightgbm", "sklearn", "httpx"}
real_import = builtins.__import__

def blocked_import(name, *args, **kwargs):
    if name.split(".", 1)[0] in blocked_roots:
        raise ImportError(f"blocked startup import: {name}")
    return real_import(name, *args, **kwargs)

builtins.__import__ = blocked_import
from typer.testing import CliRunner
from draft_oracle.cli.project import app

runner = CliRunner()
for command in ("draft", "recommend"):
    result = runner.invoke(app, [command, "--help"])
    assert result.exit_code == 0, result.output
assert not blocked_roots.intersection(sys.modules)
"""
    ml_root = Path(__file__).parents[1]
    environment = os.environ | {"PYTHONPATH": str(ml_root / "src")}

    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ml_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
