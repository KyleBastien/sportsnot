"""Smoke test for the ``oracle`` CLI entry point."""

from __future__ import annotations

from typer.testing import CliRunner

from draft_oracle import __version__
from draft_oracle.cli.project import app

runner = CliRunner()


def test_version_command() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout
