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
import os
import sys
import tempfile
from pathlib import Path

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
artifact = (Path.cwd() / "artifacts/2026-r1").resolve()
assert not (artifact / "draft-session.json").exists()
original_cwd = Path.cwd()
with tempfile.TemporaryDirectory() as temp_dir:
    try:
        os.chdir(temp_dir)
        result = runner.invoke(
            app,
            [
                "recommend",
                "--artifact-dir",
                str(artifact),
                "--rollouts",
                "1",
                "--depth",
                "1",
                "--opponents",
                "greedy",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "Recommendation for seat1" in result.output
        result = runner.invoke(
            app,
            ["draft", "--artifact", str(artifact), "--opponents", "greedy"],
            input="quit\\n",
        )
        assert result.exit_code == 0, result.output
        assert Path("draft-session.json").is_file()
    finally:
        os.chdir(original_cwd)
assert not (artifact / "draft-session.json").exists()
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
