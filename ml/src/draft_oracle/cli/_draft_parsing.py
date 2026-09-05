"""Draft-assistant command parsing and CLI option validation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import typer

OPPONENTS_GREEDY = "greedy"
OPPONENTS_FITTED = "fitted"
_OPPONENTS_AUTO = ("", "auto")


@dataclass(frozen=True)
class ParsedCommand:
    """A tokenized command line (pure result of :func:`parse_command`)."""

    name: str
    manager: str | None = None
    query: str | None = None
    path: str | None = None
    depth: int | None = None
    manager_name: str | None = None
    error: str | None = None


def parse_managers(managers: str) -> list[str]:
    """Resolve the seat->id map from the ``--managers`` value."""
    stripped = managers.strip()
    if stripped.isdigit():
        return _manager_seats(int(stripped))
    names = [token.strip() for token in stripped.split(",") if token.strip()]
    if not 2 <= len(names) <= 12:
        raise typer.BadParameter("--managers must name 2..12 seats (or give a count)")
    duplicates = _duplicate_manager_ids(names)
    if duplicates:
        raise typer.BadParameter(f"--managers contains duplicate id(s): {', '.join(duplicates)}")
    return names


def _manager_seats(count: int) -> list[str]:
    if not 2 <= count <= 12:
        raise typer.BadParameter("--managers count must be in 2..12")
    return [f"seat{index + 1}" for index in range(count)]


def _duplicate_manager_ids(names: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: list[str] = []
    for name in names:
        normalized = name.casefold()
        if normalized in seen and normalized not in duplicates:
            duplicates.append(normalized)
        seen.add(normalized)
    return duplicates


def resolve_opponents_kind(opponents: str, artifact_dir: Path) -> str:
    """Resolve explicit ``greedy``/``fitted`` or auto-detect from artifact presence."""
    kind = opponents.strip().lower()
    if kind in _OPPONENTS_AUTO:
        return _auto_opponents_kind(artifact_dir)
    if kind == OPPONENTS_FITTED:
        _require_fitted_artifact(artifact_dir)
        return OPPONENTS_FITTED
    if kind == OPPONENTS_GREEDY:
        return OPPONENTS_GREEDY
    raise typer.BadParameter(f"--opponents must be greedy, fitted, or auto (got {opponents!r})")


def _auto_opponents_kind(artifact_dir: Path) -> str:
    has_artifact = (Path(artifact_dir) / "manifest.json").exists()
    return OPPONENTS_FITTED if has_artifact else OPPONENTS_GREEDY


def _require_fitted_artifact(artifact_dir: Path) -> None:
    if (Path(artifact_dir) / "manifest.json").exists():
        return
    raise typer.BadParameter(
        f"--opponents fitted needs a committed artifact at {artifact_dir} "
        "(run `oracle train-opponents` first)"
    )


def parse_command(line: str) -> ParsedCommand:
    """Tokenize one input ``line`` into a :class:`ParsedCommand`."""
    stripped = line.strip()
    if not stripped:
        return ParsedCommand(name="")
    tokens = stripped.split()
    cmd = tokens[0].lower()
    rest = tokens[1:]
    parser = _COMMAND_PARSERS.get(cmd)
    if parser is None:
        return ParsedCommand(cmd, error=f"unknown command {cmd!r}")
    return parser(rest)


CommandParser = Callable[[list[str]], ParsedCommand]


def _constant_command(name: str) -> CommandParser:
    return lambda _rest: ParsedCommand(name)


def _parse_roster(rest: list[str]) -> ParsedCommand:
    return ParsedCommand("roster", manager_name=rest[0] if rest else None)


def _parse_save(rest: list[str]) -> ParsedCommand:
    return _parse_path_command("save", rest)


def _parse_resume(rest: list[str]) -> ParsedCommand:
    return _parse_path_command("resume", rest)


def _parse_pick(rest: list[str]) -> ParsedCommand:
    if len(rest) < 2:
        return ParsedCommand("pick", error="usage: pick <manager> <name>")
    return ParsedCommand("pick", manager=rest[0], query=" ".join(rest[1:]))


def _parse_path_command(name: str, rest: list[str]) -> ParsedCommand:
    if not rest:
        return ParsedCommand(name, error=f"usage: {name} <path>")
    return ParsedCommand(name, path=" ".join(rest))


def _parse_recommend(rest: list[str]) -> ParsedCommand:
    depth: int | None = None
    index = 0
    while index < len(rest):
        token = rest[index]
        if token in ("--depth", "-d") and index + 1 < len(rest):
            parsed_depth = _parse_depth(rest[index + 1])
            if parsed_depth is None:
                return ParsedCommand("recommend", error="depth must be an integer")
            depth = parsed_depth
            index += 2
            continue
        index += 1
    return ParsedCommand("recommend", depth=depth)


def _parse_depth(token: str) -> int | None:
    try:
        return int(token)
    except ValueError:
        return None


_COMMAND_PARSERS: dict[str, CommandParser] = {
    "?": _constant_command("help"),
    "b": _constant_command("board"),
    "board": _constant_command("board"),
    "exit": _constant_command("quit"),
    "h": _constant_command("help"),
    "help": _constant_command("help"),
    "load": _parse_resume,
    "p": _parse_pick,
    "pick": _parse_pick,
    "q": _constant_command("quit"),
    "quit": _constant_command("quit"),
    "r": _parse_roster,
    "rec": _parse_recommend,
    "recommend": _parse_recommend,
    "resume": _parse_resume,
    "roster": _parse_roster,
    "save": _parse_save,
    "u": _constant_command("undo"),
    "undo": _constant_command("undo"),
}
