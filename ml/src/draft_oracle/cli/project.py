"""``oracle`` CLI entry point (US-017 will flesh out batch projection commands).

Kept intentionally small at scaffold time: it exposes ``oracle version`` so the
console script wired up in ``pyproject.toml`` is runnable and testable.
"""

from __future__ import annotations

import typer

from draft_oracle import __version__

app = typer.Typer(
    add_completion=False,
    help="Draft Oracle — NHL playoff fantasy draft optimizer.",
    no_args_is_help=True,
)


@app.callback()
def main() -> None:
    """Draft Oracle command group. Subcommands are added per story (US-017/024)."""


@app.command()
def version() -> None:
    """Print the installed draft_oracle version."""
    typer.echo(__version__)


if __name__ == "__main__":  # pragma: no cover
    app()
