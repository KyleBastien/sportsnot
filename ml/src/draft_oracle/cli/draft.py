"""Interactive CLI draft assistant (US-024).

A terminal session where every pick is recorded live and the best remaining
options are surfaced instantly — powered *entirely* by a precomputed US-017
projection artifact. There is **no network access and no model training at
draft time**: the pool, projections, and every valuation come from the artifact
on disk, and all reasoning routes through the US-021 recommendation engine and
the rules-enforcing simulator (SPEC section 1).

The module is split into small, unit-testable pieces:

* :func:`parse_command` — pure line -> :class:`ParsedCommand` tokenizer.
* :func:`resolve_asset` — pure fuzzy name -> pool asset resolver.
* :func:`resolve_manager` — pure manager token -> canonical id resolver.
* :class:`DraftSession` — the mutable session: record picks (turn-order and
  legality enforced, illegal actions rejected *with a reason*), undo, board,
  roster, recommend, and JSON save/resume (a replayable session log).

The Typer command :func:`draft` wires these together into an interactive loop.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Annotated, Any

import typer

from draft_oracle.cli._draft_parsing import (
    OPPONENTS_FITTED,
    OPPONENTS_GREEDY,
    ParsedCommand,
    parse_command,
    parse_managers,
    resolve_opponents_kind,
)
from draft_oracle.optimize.opponents import (
    DEFAULT_OPPONENT_ARTIFACT_DIR,
    FittedLeagueOpponents,
)
from draft_oracle.optimize.recommend import (
    RecommendConfig,
    build_pool_from_projection_artifact,
    recommend_pick,
)
from draft_oracle.optimize.simulator import (
    DraftAsset,
    DraftState,
    GreedyOpponentModel,
    OpponentModel,
)

for _exported in (ParsedCommand, parse_command, parse_managers, resolve_opponents_kind):
    _exported.__module__ = __name__

__all__ = [
    "ActionResult",
    "AssetResolution",
    "DraftSession",
    "ParsedCommand",
    "RecordedPick",
    "draft",
    "opponent_label",
    "parse_command",
    "parse_managers",
    "resolve_asset",
    "resolve_manager",
    "resolve_opponents_kind",
]

SESSION_VERSION = 1
DEFAULT_TEMPERATURE = 0.3
DEFAULT_SEED = 20260827
DEFAULT_ROLLOUTS = 500
DEFAULT_NEED_WEIGHT = 4.0

# A resolution is treated as unambiguous only when the best fuzzy match clears
# the runner-up by this margin; otherwise the pick is rejected as ambiguous.
_FUZZY_MARGIN = 0.08
_FUZZY_FLOOR = 0.5


# ── Pure helpers (command parsing + resolution) ───────────────────────────


def resolve_manager(managers: list[str], token: str) -> str | None:
    """Resolve a manager ``token`` (1-based seat number, id, or prefix)."""
    stripped = token.strip().lower()
    if not stripped:
        return None
    if stripped.isdigit():
        return _manager_by_seat(managers, int(stripped))
    exact = _manager_by_exact_id(managers, stripped)
    if exact is not None:
        return exact
    return _manager_by_prefix(managers, stripped)


def _manager_by_seat(managers: list[str], index: int) -> str | None:
    if 1 <= index <= len(managers):
        return managers[index - 1]
    return None


def _manager_by_exact_id(managers: list[str], stripped: str) -> str | None:
    for manager in managers:
        if manager.lower() == stripped:
            return manager
    return None


def _manager_by_prefix(managers: list[str], stripped: str) -> str | None:
    prefixed = [manager for manager in managers if manager.lower().startswith(stripped)]
    if len(prefixed) == 1:
        return prefixed[0]
    return None


@dataclass(frozen=True)
class AssetResolution:
    """Outcome of resolving a fuzzy name against the pool.

    ``asset`` is the single confident match (or ``None``); ``matches`` are the
    ranked candidates surfaced to the user; ``reason`` is ``""`` on success or a
    short tag (``"ambiguous"`` / ``"no match"`` / ``"empty query"``).
    """

    asset: DraftAsset | None
    matches: list[DraftAsset]
    reason: str


def _ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def resolve_asset(pool: list[DraftAsset], query: str, *, limit: int = 5) -> AssetResolution:
    """Resolve a fuzzy ``query`` to a single pool asset (pure, deterministic).

    Resolution order: exact (case-insensitive) name, then substring, then a
    SequenceMatcher fuzzy pass. A match is only accepted when it is unique or
    clears the runner-up by :data:`_FUZZY_MARGIN`; otherwise the candidates are
    returned as ``ambiguous`` so the caller can ask again. Ties break by name
    then key so the same query always resolves the same way.
    """
    normalized = query.strip().lower()
    if not normalized:
        return AssetResolution(None, [], "empty query")

    exact = [asset for asset in pool if asset.name.lower() == normalized]
    if len(exact) == 1:
        return AssetResolution(exact[0], exact, "")
    if len(exact) >= 2:
        return AssetResolution(None, exact[:limit], "ambiguous")

    substrings = [asset for asset in pool if normalized in asset.name.lower()]
    if len(substrings) == 1:
        return AssetResolution(substrings[0], substrings, "")

    candidates = substrings if substrings else list(pool)
    scored = sorted(
        candidates,
        key=lambda asset: (-_ratio(normalized, asset.name.lower()), asset.name.lower(), asset.key),
    )
    if not scored:
        return AssetResolution(None, [], "no match")

    top = scored[0]
    top_score = _ratio(normalized, top.name.lower())
    if not substrings and top_score < _FUZZY_FLOOR:
        return AssetResolution(None, scored[:limit], "no match")
    if len(scored) >= 2:
        second_score = _ratio(normalized, scored[1].name.lower())
        if top_score - second_score < _FUZZY_MARGIN:
            return AssetResolution(None, scored[:limit], "ambiguous")
    return AssetResolution(top, scored[:limit], "")


# ── Session engine ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RecordedPick:
    """One recorded pick: who drafted which asset (a replayable log entry)."""

    manager: str
    asset_key: str
    name: str
    position: str

    def as_dict(self) -> dict[str, str]:
        """JSON-serialisable form."""
        return {
            "manager": self.manager,
            "asset_key": self.asset_key,
            "name": self.name,
            "position": self.position,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RecordedPick:
        """Rebuild from :meth:`as_dict` output."""
        return cls(
            manager=str(data["manager"]),
            asset_key=str(data["asset_key"]),
            name=str(data["name"]),
            position=str(data["position"]),
        )


@dataclass(frozen=True)
class ActionResult:
    """The outcome of a session action: success flag, message, and any lines."""

    ok: bool
    message: str
    lines: list[str] = field(default_factory=list)


def _resolve_eliminated(pool: list[DraftAsset], abbrevs: list[str]) -> frozenset[int]:
    wanted = {abbrev.strip().upper() for abbrev in abbrevs if abbrev.strip()}
    if not wanted:
        return frozenset()
    team_ids: dict[str, set[int]] = defaultdict(set)
    for asset in pool:
        if asset.team_id is not None:
            team_ids[asset.team_abbrev.upper()].add(asset.team_id)
    unknown = sorted(wanted - team_ids.keys())
    if unknown:
        raise typer.BadParameter(f"--eliminated unknown team abbrev(s): {', '.join(unknown)}")
    return frozenset(team_id for abbrev in wanted for team_id in team_ids[abbrev])


def opponent_label(
    opponents: str,
    fitted: FittedLeagueOpponents | None,
    managers: list[str],
) -> str:
    """Describe fitted-policy coverage for the supplied manager ids honestly."""
    if opponents == OPPONENTS_GREEDY:
        return "greedy opponents"
    if fitted is None:
        raise ValueError("fitted opponents requested but no artifact is loaded")
    attached = [
        manager in fitted.per_manager or bool(fitted.affinity.get(manager)) for manager in managers
    ]
    if all(attached):
        return "fitted opponents"
    if any(attached):
        return "fitted opponents: mixed per-manager and league-average"
    return "fitted opponents: league-average, no per-manager affinity"


@dataclass
class DraftSession:
    """A live draft: the artifact-backed pool, recorded picks, and derived state.

    The :class:`~draft_oracle.optimize.simulator.DraftState` is *derived* by
    replaying ``picks`` from a fresh state, so undo is just "drop the last pick
    and rebuild" — always consistent with the rules engine.
    """

    artifact_dir: Path
    manager_count: int
    slot: int
    ir: bool
    pool: list[DraftAsset]
    managers: list[str]
    eliminated_team_ids: frozenset[int] = frozenset()
    picks: list[RecordedPick] = field(default_factory=list)
    temperature: float = DEFAULT_TEMPERATURE
    seed: int = DEFAULT_SEED
    rollouts: int = DEFAULT_ROLLOUTS
    opponents: str = OPPONENTS_GREEDY
    opponent_artifact_dir: Path = DEFAULT_OPPONENT_ARTIFACT_DIR
    fitted: FittedLeagueOpponents | None = None
    state: DraftState = field(init=False)

    def __post_init__(self) -> None:
        if not 1 <= self.slot <= self.manager_count:
            raise ValueError(f"slot must be in 1..{self.manager_count}, got {self.slot}")
        if len(self.managers) != self.manager_count:
            raise ValueError("managers length must equal manager_count")
        if self.opponents not in (OPPONENTS_GREEDY, OPPONENTS_FITTED):
            raise ValueError(f"opponents must be greedy or fitted, got {self.opponents!r}")
        if self.opponents == OPPONENTS_FITTED and self.fitted is None:
            self.fitted = FittedLeagueOpponents.load(self.opponent_artifact_dir)
        self._rebuild()

    @classmethod
    def from_artifact(
        cls,
        artifact_dir: Path,
        *,
        manager_count: int,
        slot: int,
        ir: bool = False,
        eliminated: list[str] | None = None,
        temperature: float = DEFAULT_TEMPERATURE,
        seed: int = DEFAULT_SEED,
        rollouts: int = DEFAULT_ROLLOUTS,
        managers: list[str] | None = None,
        opponents: str = OPPONENTS_GREEDY,
        opponent_artifact_dir: Path = DEFAULT_OPPONENT_ARTIFACT_DIR,
        fitted: FittedLeagueOpponents | None = None,
    ) -> DraftSession:
        """Start a fresh session from a US-017 projection artifact directory."""
        pool = build_pool_from_projection_artifact(artifact_dir, ir=ir)
        manager_ids = managers or [f"seat{i + 1}" for i in range(manager_count)]
        eliminated_ids = _resolve_eliminated(pool, eliminated or [])
        return cls(
            artifact_dir=artifact_dir,
            manager_count=manager_count,
            slot=slot,
            ir=ir,
            pool=pool,
            managers=manager_ids,
            eliminated_team_ids=eliminated_ids,
            temperature=temperature,
            seed=seed,
            rollouts=rollouts,
            opponents=opponents,
            opponent_artifact_dir=opponent_artifact_dir,
            fitted=fitted,
        )

    @property
    def owner(self) -> str:
        """The manager occupying the owner's snake ``slot``."""
        return self.managers[self.slot - 1]

    def _rebuild(self) -> None:
        """Rebuild :attr:`state` by replaying ``picks`` from a fresh draft."""
        self.state = DraftState.new(
            self.managers,
            self.pool,
            allow_ir=self.ir,
            eliminated_team_ids=self.eliminated_team_ids,
        )
        by_key = {asset.key: asset for asset in self.pool}
        for pick in self.picks:
            asset = by_key.get(pick.asset_key)
            if asset is None:
                raise ValueError(f"recorded pick references unknown asset {pick.asset_key!r}")
            expected = self.state.current_manager
            if pick.manager != expected:
                raise ValueError(
                    f"session log out of order: {pick.manager!r} recorded but "
                    f"{expected!r} was on the clock"
                )
            self.state.apply_pick(asset)

    # ── Mutating / query actions ─────────────────────────────────────────

    def record_pick(self, manager_token: str, query: str) -> ActionResult:
        """Record ``manager``'s pick of the fuzzy-named asset, or reject with reason."""
        manager = resolve_manager(self.managers, manager_token)
        if manager is None:
            return ActionResult(False, f"unknown manager {manager_token!r}")
        if self.state.is_complete:
            return ActionResult(False, "draft is complete; every slot is filled")
        current = self.state.current_manager
        if manager != current:
            return ActionResult(False, f"not {manager}'s turn (on the clock: {current})")

        resolution = resolve_asset(self.pool, query)
        if resolution.asset is None:
            if resolution.reason == "ambiguous":
                names = ", ".join(
                    f"{asset.name} ({asset.position} {asset.team_abbrev})"
                    for asset in resolution.matches
                )
                return ActionResult(False, f"ambiguous name {query!r}; did you mean: {names}")
            return ActionResult(False, f"no player matches {query!r}")

        asset = resolution.asset
        if asset.team_id is not None and asset.team_id in self.eliminated_team_ids:
            return ActionResult(
                False, f"{asset.name} is on an eliminated team and cannot be drafted"
            )
        if asset.key not in self.state.available:
            return ActionResult(False, f"{asset.name} is already drafted")
        if not self.state.has_capacity(current, asset.position):
            limit = self.state.capacity.limit(asset.position)
            return ActionResult(False, f"{current} is full at {asset.position} ({limit} slots)")

        self.state.apply_pick(asset)
        self.picks.append(RecordedPick(current, asset.key, asset.name, asset.position))
        return ActionResult(
            True,
            f"pick #{len(self.picks)}: {current} drafts {asset.name} "
            f"({asset.position} {asset.team_abbrev})",
        )

    def undo(self) -> ActionResult:
        """Undo the most recent pick and rebuild the derived state."""
        if not self.picks:
            return ActionResult(False, "nothing to undo")
        last = self.picks.pop()
        self._rebuild()
        return ActionResult(True, f"undid {last.manager}'s pick of {last.name}")

    def board(self, top: int = 10) -> ActionResult:
        """Remaining assets grouped by position, best projection first."""
        groups: dict[str, list[DraftAsset]] = defaultdict(list)
        for asset in self.state.available.values():
            groups[asset.position].append(asset)
        if self.state.is_complete:
            header = "Board - draft complete"
        else:
            header = (
                f"Board - pick #{self.state.pick_index + 1}, "
                f"on the clock: {self.state.current_manager}"
            )
        lines = [header]
        for position in ("F", "D", "G"):
            assets = sorted(
                groups.get(position, []),
                key=lambda asset: (-_value(asset), asset.name),
            )
            lines.append(f"  {position} ({len(assets)} left):")
            for asset in assets[:top]:
                lines.append(f"    {asset.name[:22]:22} {asset.team_abbrev:4} {_value(asset):6.2f}")
        return ActionResult(True, "board", lines)

    def roster(self, manager_token: str | None = None) -> ActionResult:
        """A manager's current roster (defaults to the owner's)."""
        if manager_token is None:
            manager = self.owner
        else:
            resolved = resolve_manager(self.managers, manager_token)
            if resolved is None:
                return ActionResult(False, f"unknown manager {manager_token!r}")
            manager = resolved
        roster = self.state.rosters[manager]
        capacity = self.state.capacity
        marker = " (you)" if manager == self.owner else ""
        lines = [f"Roster - {manager}{marker}"]
        for label, bucket, limit in (
            ("F", roster.forwards, capacity.forwards),
            ("D", roster.defense, capacity.defense),
            ("G", roster.goalies, capacity.goalies),
        ):
            lines.append(f"  {label} ({len(bucket)}/{limit}):")
            for asset in bucket:
                lines.append(f"    {asset.name[:22]:22} {asset.team_abbrev:4} {_value(asset):6.2f}")
        return ActionResult(True, "roster", lines)

    def build_opponent_model(self) -> OpponentModel | Mapping[str, OpponentModel]:
        """The opponent policy the recommender rolls out: fitted per-manager or greedy.

        ``fitted`` returns the per-seat mapping so each real manager id gets their own
        fitted model (unknown ids fall back to the league model); ``greedy`` returns the
        single vectorized fast-path fallback.
        """
        if self.opponents == OPPONENTS_FITTED:
            if self.fitted is None:
                raise ValueError("fitted opponents requested but no artifact is loaded")
            return self.fitted.as_mapping(self.managers)
        return GreedyOpponentModel(temperature=self.temperature, need_weight=DEFAULT_NEED_WEIGHT)

    def opponent_label(self) -> str:
        """Visible label for the opponent policy actually attached to these seats."""
        return opponent_label(self.opponents, self.fitted, self.managers)

    def recommend(self, depth: int | None = None) -> ActionResult:
        """Top-5 explained recommendations for whoever is on the clock (US-021)."""
        if self.state.is_complete:
            return ActionResult(False, "draft is complete; nothing to recommend")
        current = self.state.current_manager
        model = self.build_opponent_model()
        config = RecommendConfig(
            rollouts=self.rollouts,
            depth=depth,
            seed=self.seed,
            top_n=5,
        )
        recommendation = recommend_pick(
            self.state, current, model, config=config, managers=self.manager_count
        )
        return ActionResult(
            True, f"recommendation ({self.opponent_label()})", recommendation.report_lines()
        )

    # ── Persistence (replayable session log) ─────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """JSON-serialisable snapshot: config + recorded picks (a replay log)."""
        return {
            "version": SESSION_VERSION,
            "artifact_dir": str(self.artifact_dir),
            "manager_count": self.manager_count,
            "managers": list(self.managers),
            "slot": self.slot,
            "ir": self.ir,
            "temperature": self.temperature,
            "seed": self.seed,
            "rollouts": self.rollouts,
            "opponents": self.opponents,
            "opponent_artifact_dir": str(self.opponent_artifact_dir),
            "eliminated_team_ids": sorted(self.eliminated_team_ids),
            "picks": [pick.as_dict() for pick in self.picks],
        }

    def save(self, path: Path) -> None:
        """Write the session JSON to ``path`` (parents created as needed)."""
        path = Path(path)
        if path.parent:
            path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def resume(
        cls,
        path: Path,
        *,
        pool_loader: Callable[[Path, bool], list[DraftAsset]] | None = None,
    ) -> DraftSession:
        """Rebuild a session from a saved JSON file (round-trips :meth:`save`).

        ``pool_loader`` overrides how the pool is rebuilt (defaults to reading the
        artifact directory); tests inject a synthetic pool this way.
        """
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        artifact_dir = Path(data["artifact_dir"])
        ir = bool(data["ir"])
        loader = pool_loader or (
            lambda directory, use_ir: build_pool_from_projection_artifact(directory, ir=use_ir)
        )
        pool = loader(artifact_dir, ir)
        return cls(
            artifact_dir=artifact_dir,
            manager_count=int(data["manager_count"]),
            slot=int(data["slot"]),
            ir=ir,
            pool=pool,
            managers=[str(manager) for manager in data["managers"]],
            eliminated_team_ids=frozenset(
                int(team) for team in data.get("eliminated_team_ids", [])
            ),
            picks=[RecordedPick.from_dict(pick) for pick in data["picks"]],
            temperature=float(data.get("temperature", DEFAULT_TEMPERATURE)),
            seed=int(data.get("seed", DEFAULT_SEED)),
            rollouts=int(data.get("rollouts", DEFAULT_ROLLOUTS)),
            opponents=str(data.get("opponents", OPPONENTS_GREEDY)),
            opponent_artifact_dir=Path(
                data.get("opponent_artifact_dir", str(DEFAULT_OPPONENT_ARTIFACT_DIR))
            ),
        )


def _value(asset: DraftAsset) -> float:
    return float(asset.projection if asset.projection is not None else asset.rank_value)


# ── Interactive loop + Typer command ──────────────────────────────────────

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
    session: DraftSession
    session_path: Path | None
    echo: Callable[[str], None]


def _run_loop(
    session: DraftSession,
    session_path: Path | None,
    *,
    input_fn: Callable[[str], str] = input,
    echo: Callable[[str], None] = typer.echo,
) -> DraftSession:
    """Drive an interactive session until EOF/quit. Returns the final session."""
    state = _LoopState(session, session_path, echo)
    _show_help_banner(echo)
    _autosave(state)
    while True:
        parsed = _read_command(state.session, input_fn, echo)
        if parsed is None:
            break
        if _handle_loop_command(state, parsed):
            break
    _autosave(state)
    return state.session


def _show_help_banner(echo: Callable[[str], None]) -> None:
    echo("Draft Oracle interactive assistant (US-024). Type 'help' for commands.")
    _echo_lines(echo, _HELP_LINES)


def _read_command(
    session: DraftSession,
    input_fn: Callable[[str], str],
    echo: Callable[[str], None],
) -> ParsedCommand | None:
    try:
        return parse_command(input_fn(_prompt(session)))
    except (EOFError, KeyboardInterrupt):
        echo("")
        return None


def _prompt(session: DraftSession) -> str:
    if session.state.is_complete:
        return "[draft complete] > "
    return f"[#{session.state.pick_index + 1} {session.state.current_manager}] > "


def _handle_loop_command(state: _LoopState, parsed: ParsedCommand) -> bool:
    if parsed.name == "":
        return False
    if parsed.error:
        state.echo(parsed.error)
        return False
    if parsed.name == "quit":
        return True
    handler = _LOOP_HANDLERS.get(parsed.name)
    if handler is not None:
        handler(state, parsed)
        return False
    _handle_action_command(state, parsed)
    return False


def _handle_help(state: _LoopState, _parsed: ParsedCommand) -> None:
    _echo_lines(state.echo, _HELP_LINES)


def _handle_resume(state: _LoopState, parsed: ParsedCommand) -> None:
    assert parsed.path is not None
    resume_path = Path(parsed.path)
    state.session = DraftSession.resume(resume_path)
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


def _handle_action_command(state: _LoopState, parsed: ParsedCommand) -> None:
    result = _dispatch(state.session, parsed)
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


_LOOP_HANDLERS: dict[str, Callable[[_LoopState, ParsedCommand], None]] = {
    "help": _handle_help,
    "resume": _handle_resume,
    "save": _handle_save,
}


def _dispatch(session: DraftSession, parsed: ParsedCommand) -> ActionResult:
    if parsed.name == "pick":
        assert parsed.manager is not None and parsed.query is not None
        return session.record_pick(parsed.manager, parsed.query)
    if parsed.name == "undo":
        return session.undo()
    if parsed.name == "board":
        return session.board()
    if parsed.name == "roster":
        return session.roster(parsed.manager_name)
    if parsed.name == "recommend":
        return session.recommend(depth=parsed.depth)
    return ActionResult(False, f"unknown command {parsed.name!r}")


def draft(
    artifact: Annotated[
        Path | None,
        typer.Option(help="Projection artifact directory (skaters/teams parquet)."),
    ] = None,
    managers: Annotated[
        str,
        typer.Option(help="League size (2-12) or comma seat ids (e.g. ben,judah,levi,kyle)."),
    ] = "4",
    slot: Annotated[int, typer.Option("--slot", help="Your snake seat (1-based).")] = 1,
    ir: Annotated[
        bool, typer.Option("--ir/--no-ir", help="League uses IR slots (+1 F, +1 D).")
    ] = False,
    eliminated: Annotated[str, typer.Option(help="Comma-separated eliminated team abbrevs.")] = "",
    session: Annotated[
        Path | None,
        typer.Option(help="Session-log path (defaults to ./draft-session.json)."),
    ] = None,
    resume: Annotated[
        Path | None, typer.Option("--resume", help="Resume a saved session JSON instead.")
    ] = None,
    temperature: Annotated[
        float, typer.Option(help="Greedy opponent softmax temperature.")
    ] = DEFAULT_TEMPERATURE,
    seed: Annotated[int, typer.Option(help="Deterministic seed.")] = DEFAULT_SEED,
    rollouts: Annotated[
        int, typer.Option(help="Monte-Carlo rollouts per candidate for recommend.")
    ] = DEFAULT_ROLLOUTS,
    opponents: Annotated[
        str,
        typer.Option(
            help="Opponent model: greedy, fitted, or auto (fitted when the artifact exists)."
        ),
    ] = "auto",
    opponent_artifact: Annotated[
        Path, typer.Option(help="Committed opponent-model artifact directory (fitted path).")
    ] = DEFAULT_OPPONENT_ARTIFACT_DIR,
) -> None:
    """Start an interactive, artifact-powered draft assistant (US-024).

    Record every pick live (``pick <manager> <name>``) and get instant, explained
    recommendations (``recommend``) with full multi-step lookahead. All valuation
    comes from the precomputed artifact — no network, no training at draft time.
    Illegal actions are rejected with the reason (position full, already drafted,
    eliminated), and the session autosaves to a replayable JSON log in the current
    directory unless ``--session`` supplies another path. Artifact directories remain
    immutable inputs.

    Opponents default to the committed *fitted* league model when its artifact is
    present (``--opponents greedy`` forces the fallback); pass real names to
    ``--managers`` (``ben,judah,levi,kyle``) to attach each manager's fitted model
    to their real seat.
    """
    if resume is not None:
        if session is not None and session.exists() and not _same_path(resume, session):
            raise typer.BadParameter(
                f"session log already exists at {session} and differs from resumed log "
                f"{resume}; omit --session to resume in place or choose a new path"
            )
        loaded = DraftSession.resume(resume)
        session_path = session or resume
        _run_loop(loaded, session_path)
        return
    if artifact is None:
        raise typer.BadParameter("provide --artifact <dir> (or --resume <session.json>)")
    manager_ids = parse_managers(managers)
    manager_count = len(manager_ids)
    if not 1 <= slot <= manager_count:
        raise typer.BadParameter(f"slot must be in 1..{manager_count}")
    session_path = session or Path("draft-session.json")
    if session_path.exists():
        raise typer.BadParameter(
            f"session log already exists at {session_path}; use --resume {session_path} "
            "or choose a different --session path"
        )
    eliminated_teams = [token for token in eliminated.split(",") if token.strip()]
    opponents_kind = resolve_opponents_kind(opponents, opponent_artifact)
    new_session = DraftSession.from_artifact(
        artifact,
        manager_count=manager_count,
        slot=slot,
        ir=ir,
        eliminated=eliminated_teams,
        temperature=temperature,
        seed=seed,
        rollouts=rollouts,
        managers=manager_ids,
        opponents=opponents_kind,
        opponent_artifact_dir=opponent_artifact,
    )
    _run_loop(new_session, session_path)


def _same_path(left: Path, right: Path) -> bool:
    """Return whether two paths identify the same file or normalized location."""
    try:
        return left.samefile(right)
    except (FileNotFoundError, OSError):
        return left.resolve(strict=False) == right.resolve(strict=False)
