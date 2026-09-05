"""Interactive loop runtime for draft CLI."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from draft_oracle.cli._draft_parsing import ParsedCommand, parse_command
from draft_oracle.cli._draft_resolution import ActionResult

_HELP_LINES = [
    "Commands:",
    "  pick <manager> <name>   record a pick (manager = seat number or id)",
    "  undo                    undo the most recent pick",
    "  board                   remaining assets by position",
    "  roster [manager]        a roster (yours by default)",
    "  recommend [--depth N]   top-5 explained picks (full lookahead by default)",
    "  save <path>             write the session JSON",
    "  resume <path>           replace session and switch autosave to that JSON",
    "  help                    show this help",
    "  quit                    exit",
]


@dataclass
class _LoopState:
    session: Any
    session_path: Path | None
    echo: Callable[[str], None]


@dataclass(frozen=True)
class _LoopRuntime:
    dispatch: Callable[[Any, ParsedCommand], ActionResult]
    resume_session: Callable[[Path], Any]


@dataclass(frozen=True)
class _LoopRequest:
    session: Any
    session_path: Path | None
    input_fn: Callable[[str], str]
    echo: Callable[[str], None]


def _run_loop(
    runtime: _LoopRuntime,
    request: _LoopRequest,
) -> Any:
    """Drive an interactive session until EOF/quit. Returns final session."""
    state = _LoopState(request.session, request.session_path, request.echo)
    _show_help_banner(request.echo)
    _autosave(state)
    while True:
        parsed = _read_command(state.session, request.input_fn, request.echo)
        if parsed is None:
            break
        if _handle_loop_command(state, runtime, parsed):
            break
    _autosave(state)
    return state.session


def _show_help_banner(echo: Callable[[str], None]) -> None:
    echo("Draft Oracle interactive assistant (US-024). Type 'help' for commands.")
    _echo_lines(echo, _HELP_LINES)


def _read_command(
    session: Any,
    input_fn: Callable[[str], str],
    echo: Callable[[str], None],
) -> ParsedCommand | None:
    try:
        return parse_command(input_fn(_prompt(session)))
    except (EOFError, KeyboardInterrupt):
        echo("")
        return None


def _prompt(session: Any) -> str:
    if session.state.is_complete:
        return "[draft complete] > "
    return f"[#{session.state.pick_index + 1} {session.state.current_manager}] > "


def _handle_loop_command(
    state: _LoopState,
    runtime: _LoopRuntime,
    parsed: ParsedCommand,
) -> bool:
    if parsed.name == "":
        return False
    if parsed.error:
        state.echo(parsed.error)
        return False
    if parsed.name == "quit":
        return True
    if parsed.name == "help":
        _echo_lines(state.echo, _HELP_LINES)
        return False
    if parsed.name == "resume":
        _handle_resume(state, runtime, parsed)
        return False
    if parsed.name == "save":
        _handle_save(state, parsed)
        return False
    _handle_action_command(state, runtime, parsed)
    return False


def _handle_resume(
    state: _LoopState,
    runtime: _LoopRuntime,
    parsed: ParsedCommand,
) -> None:
    assert parsed.path is not None
    resume_path = Path(parsed.path)
    state.session = runtime.resume_session(resume_path)
    state.session_path = resume_path
    state.echo(
        f"resumed {len(state.session.picks)} pick(s) from {parsed.path}; "
        f"autosave target switched to {parsed.path}"
    )
    _autosave(state)


def _handle_save(state: _LoopState, parsed: ParsedCommand) -> None:
    assert parsed.path is not None
    state.session.save(Path(parsed.path))
    state.echo(f"saved session -> {parsed.path}")


def _handle_action_command(
    state: _LoopState,
    runtime: _LoopRuntime,
    parsed: ParsedCommand,
) -> None:
    result = runtime.dispatch(state.session, parsed)
    state.echo(result.message)
    _echo_lines(state.echo, result.lines)
    if parsed.name in ("pick", "undo") and result.ok:
        _autosave(state)


def _echo_lines(echo: Callable[[str], None], lines: list[str]) -> None:
    for line in lines:
        echo(line)


def _autosave(state: _LoopState) -> None:
    if state.session_path is not None:
        state.session.save(state.session_path)
