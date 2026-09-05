"""``_request_commands``: a request dataclass becomes a real Typer command."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from draft_oracle.cli._request_commands import option, register_request_command

runner = CliRunner()


@dataclass(frozen=True)
class _Request:
    season: int = field(metadata=option(typer.Option(help="Season end year.")))
    playoff_round: int = field(metadata=option(typer.Option("--round", help="Round (1-4).")))
    ir: bool = field(default=False, metadata=option(typer.Option("--ir/--no-ir", help="IR.")))
    out: Path = field(default=Path("artifacts"), metadata=option(typer.Option(help="Out dir.")))
    seasons: list[int] | None = field(default=None, metadata=option(typer.Option(help="Extra.")))


def _app() -> tuple[typer.Typer, list[_Request]]:
    seen: list[_Request] = []
    app = typer.Typer()

    def run(request: _Request) -> None:
        """Do the thing.

        Longer description.
        """
        seen.append(request)

    register_request_command(app, "do-thing", _Request, run)
    return app, seen


def test_options_parse_into_the_request_with_defaults() -> None:
    app, seen = _app()
    result = runner.invoke(
        app, ["--season", "2027", "--round", "2", "--ir", "--seasons", "1", "--seasons", "2"]
    )
    assert result.exit_code == 0, result.output
    assert seen == [_Request(season=2027, playoff_round=2, ir=True, seasons=[1, 2])]


def test_help_shows_docstring_defaults_and_required_markers() -> None:
    app, _ = _app()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Do the thing." in result.output
    assert "[required]" in result.output
    assert "artifacts" in result.output  # the default renders
    assert "--no-ir" in result.output


def test_missing_required_option_fails_and_never_runs() -> None:
    app, seen = _app()
    result = runner.invoke(app, ["--round", "2"])
    assert result.exit_code != 0
    assert seen == []


def test_field_without_option_metadata_is_rejected_at_registration() -> None:
    @dataclass(frozen=True)
    class _Bare:
        season: int

    with pytest.raises(TypeError, match="season"):
        register_request_command(typer.Typer(), "bare", _Bare, lambda _request: None)
