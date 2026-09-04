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

from collections import defaultdict
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any, TypedDict, Unpack, cast

import typer

from draft_oracle.cli._draft_parsing import (
    OPPONENTS_FITTED,
    OPPONENTS_GREEDY,
    ParsedCommand,
    parse_command,
    parse_managers,
    resolve_opponents_kind,
)
from draft_oracle.cli._draft_resolution import (
    ActionResult,
    AssetResolution,
    RecordedPick,
    resolve_asset,
    resolve_manager,
)
from draft_oracle.cli._draft_runtime import _LoopRequest, _LoopRuntime
from draft_oracle.cli._draft_runtime import _run_loop as _run_loop_impl
from draft_oracle.cli._draft_session_io import (
    _resume_inputs,
    _save_session,
    _session_dict,
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
# ── Session engine ────────────────────────────────────────────────────────
def _resolve_eliminated(pool: list[DraftAsset], abbrevs: list[str]) -> frozenset[int]:
    wanted = _wanted_eliminated_abbrevs(abbrevs)
    if not wanted:
        return frozenset()
    team_ids = _team_ids_by_abbrev(pool)
    unknown = sorted(wanted - team_ids.keys())
    if unknown:
        raise typer.BadParameter(f"--eliminated unknown team abbrev(s): {', '.join(unknown)}")
    return frozenset(team_id for abbrev in wanted for team_id in team_ids[abbrev])


def _wanted_eliminated_abbrevs(abbrevs: list[str]) -> set[str]:
    return {abbrev.strip().upper() for abbrev in abbrevs if abbrev.strip()}


def _team_ids_by_abbrev(pool: list[DraftAsset]) -> dict[str, set[int]]:
    team_ids: dict[str, set[int]] = defaultdict(set)
    for asset in pool:
        if asset.team_id is not None:
            team_ids[asset.team_abbrev.upper()].add(asset.team_id)
    return team_ids


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
        self._validate_session_shape()
        self._load_fitted_if_requested()
        self._rebuild()

    @classmethod
    def from_artifact(
        cls,
        artifact_dir: DraftSessionArtifactRequest | Path,
        **legacy: Unpack[_DraftSessionArtifactKwargs],
    ) -> DraftSession:
        """Start a fresh session from a US-017 projection artifact directory."""
        request = _resolve_artifact_request(artifact_dir, legacy)
        pool = build_pool_from_projection_artifact(request.artifact_dir, ir=request.ir)
        manager_ids = request.managers or [f"seat{i + 1}" for i in range(request.manager_count)]
        eliminated_ids = _resolve_eliminated(pool, request.eliminated or [])
        return cls(
            artifact_dir=request.artifact_dir,
            manager_count=request.manager_count,
            slot=request.slot,
            ir=request.ir,
            pool=pool,
            managers=manager_ids,
            eliminated_team_ids=eliminated_ids,
            temperature=request.temperature,
            seed=request.seed,
            rollouts=request.rollouts,
            opponents=request.opponents,
            opponent_artifact_dir=request.opponent_artifact_dir,
            fitted=request.fitted,
        )

    def _validate_session_shape(self) -> None:
        if not 1 <= self.slot <= self.manager_count:
            raise ValueError(f"slot must be in 1..{self.manager_count}, got {self.slot}")
        if len(self.managers) != self.manager_count:
            raise ValueError("managers length must equal manager_count")
        if self.opponents not in (OPPONENTS_GREEDY, OPPONENTS_FITTED):
            raise ValueError(f"opponents must be greedy or fitted, got {self.opponents!r}")

    def _load_fitted_if_requested(self) -> None:
        if self.opponents == OPPONENTS_FITTED and self.fitted is None:
            self.fitted = FittedLeagueOpponents.load(self.opponent_artifact_dir)

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
        manager_result = self._pick_manager_result(manager_token)
        if manager_result is not None:
            return manager_result
        current = self.state.current_manager
        asset_result = self._pick_asset_result(query)
        if asset_result is not None:
            return asset_result
        asset = self._draftable_asset(query, current)
        if isinstance(asset, ActionResult):
            return asset
        self.state.apply_pick(asset)
        self.picks.append(RecordedPick(current, asset.key, asset.name, asset.position))
        return ActionResult(
            True,
            f"pick #{len(self.picks)}: {current} drafts {asset.name} "
            f"({asset.position} {asset.team_abbrev})",
        )

    def _pick_manager_result(self, manager_token: str) -> ActionResult | None:
        manager = resolve_manager(self.managers, manager_token)
        if manager is None:
            return ActionResult(False, f"unknown manager {manager_token!r}")
        if self.state.is_complete:
            return ActionResult(False, "draft is complete; every slot is filled")
        current = self.state.current_manager
        if manager != current:
            return ActionResult(False, f"not {manager}'s turn (on the clock: {current})")
        return None

    def _pick_asset_result(self, query: str) -> ActionResult | None:
        resolution = resolve_asset(self.pool, query)
        if resolution.asset is not None:
            return None
        if resolution.reason == "ambiguous":
            names = ", ".join(
                f"{asset.name} ({asset.position} {asset.team_abbrev})"
                for asset in resolution.matches
            )
            return ActionResult(False, f"ambiguous name {query!r}; did you mean: {names}")
        return ActionResult(False, f"no player matches {query!r}")

    def _draftable_asset(self, query: str, current: str) -> DraftAsset | ActionResult:
        resolution = resolve_asset(self.pool, query)
        assert resolution.asset is not None
        asset = resolution.asset
        if asset.team_id is not None and asset.team_id in self.eliminated_team_ids:
            return ActionResult(
                False,
                f"{asset.name} is on an eliminated team and cannot be drafted",
            )
        if asset.key not in self.state.available:
            return ActionResult(False, f"{asset.name} is already drafted")
        if not self.state.has_capacity(current, asset.position):
            limit = self.state.capacity.limit(asset.position)
            return ActionResult(False, f"{current} is full at {asset.position} ({limit} slots)")
        return asset

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
        manager, error = self._resolve_roster_manager(manager_token)
        if error is not None:
            return ActionResult(False, error)
        assert manager is not None
        roster = self.state.rosters[manager]
        lines = [self._roster_header(manager)]
        for label, bucket, limit in (
            ("F", roster.forwards, self.state.capacity.forwards),
            ("D", roster.defense, self.state.capacity.defense),
            ("G", roster.goalies, self.state.capacity.goalies),
        ):
            lines.extend(_roster_bucket_lines(label, bucket, limit))
        return ActionResult(True, "roster", lines)

    def _resolve_roster_manager(
        self, manager_token: str | None
    ) -> tuple[str | None, str | None]:
        if manager_token is None:
            return self.owner, None
        manager = resolve_manager(self.managers, manager_token)
        if manager is None:
            return None, f"unknown manager {manager_token!r}"
        return manager, None

    def _roster_header(self, manager: str) -> str:
        marker = " (you)" if manager == self.owner else ""
        return f"Roster - {manager}{marker}"

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
        recommendation = recommend_pick(self.state, current, model, config=config)
        return ActionResult(
            True, f"recommendation ({self.opponent_label()})", recommendation.report_lines()
        )

    # ── Persistence (replayable session log) ─────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """JSON-serialisable snapshot: config + recorded picks (a replay log)."""
        return _session_dict(self, version=SESSION_VERSION)

    def save(self, path: Path) -> None:
        """Write the session JSON to ``path`` (parents created as needed)."""
        _save_session(path, self.to_dict())

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
        loader = pool_loader or (
            lambda directory, use_ir: build_pool_from_projection_artifact(directory, ir=use_ir)
        )
        data, pool = _resume_inputs(path, pool_loader=loader)
        artifact_dir = Path(data["artifact_dir"])
        ir = bool(data["ir"])
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


def _roster_bucket_lines(label: str, bucket: list[DraftAsset], limit: int) -> list[str]:
    lines = [f"  {label} ({len(bucket)}/{limit}):"]
    for asset in bucket:
        lines.append(f"    {asset.name[:22]:22} {asset.team_abbrev:4} {_value(asset):6.2f}")
    return lines


# ── Interactive loop + Typer command ──────────────────────────────────────


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


def _run_loop(
    session: DraftSession,
    session_path: Path | None,
    *,
    input_fn: Callable[[str], str] = input,
    echo: Callable[[str], None] = typer.echo,
) -> DraftSession:
    return cast(
        "DraftSession",
        _run_loop_impl(
            _LoopRuntime(_dispatch, DraftSession.resume),
            _LoopRequest(session, session_path, input_fn, echo),
        ),
    )


def _resume_session_path(resume: Path, session: Path | None) -> Path:
    if _resume_conflicts_with_session(resume, session):
        raise typer.BadParameter(
            f"session log already exists at {session} and differs from resumed log "
            f"{resume}; omit --session to resume in place or choose a new path"
        )
    return session or resume


def _resume_conflicts_with_session(resume: Path, session: Path | None) -> bool:
    return session is not None and session.exists() and not _same_path(resume, session)


def _new_session_path(session: Path | None) -> Path:
    session_path = session or Path("draft-session.json")
    if session_path.exists():
        raise typer.BadParameter(
            f"session log already exists at {session_path}; use --resume {session_path} "
            "or choose a different --session path"
        )
    return session_path


def _validate_draft_slot(slot: int, manager_count: int) -> None:
    if not 1 <= slot <= manager_count:
        raise typer.BadParameter(f"slot must be in 1..{manager_count}")


class _DraftSessionArtifactKwargs(TypedDict, total=False):
    manager_count: int
    slot: int
    ir: bool
    eliminated: list[str] | None
    temperature: float
    seed: int
    rollouts: int
    managers: list[str] | None
    opponents: str
    opponent_artifact_dir: Path
    fitted: FittedLeagueOpponents | None


@dataclass(frozen=True)
class DraftSessionArtifactRequest:
    artifact_dir: Path
    manager_count: int
    slot: int
    ir: bool = False
    eliminated: list[str] | None = None
    temperature: float = DEFAULT_TEMPERATURE
    seed: int = DEFAULT_SEED
    rollouts: int = DEFAULT_ROLLOUTS
    managers: list[str] | None = None
    opponents: str = OPPONENTS_GREEDY
    opponent_artifact_dir: Path = DEFAULT_OPPONENT_ARTIFACT_DIR
    fitted: FittedLeagueOpponents | None = None


def _resolve_artifact_request(
    artifact_dir: DraftSessionArtifactRequest | Path,
    legacy: Mapping[str, object],
) -> DraftSessionArtifactRequest:
    if isinstance(artifact_dir, DraftSessionArtifactRequest):
        if legacy:
            raise TypeError("DraftSessionArtifactRequest calls do not accept extra keyword args")
        return artifact_dir
    return DraftSessionArtifactRequest(
        artifact_dir=artifact_dir,
        manager_count=cast("int", legacy["manager_count"]),
        slot=cast("int", legacy["slot"]),
        ir=cast("bool", legacy.get("ir", False)),
        eliminated=cast("list[str] | None", legacy.get("eliminated")),
        temperature=cast("float", legacy.get("temperature", DEFAULT_TEMPERATURE)),
        seed=cast("int", legacy.get("seed", DEFAULT_SEED)),
        rollouts=cast("int", legacy.get("rollouts", DEFAULT_ROLLOUTS)),
        managers=cast("list[str] | None", legacy.get("managers")),
        opponents=cast("str", legacy.get("opponents", OPPONENTS_GREEDY)),
        opponent_artifact_dir=cast(
            "Path",
            legacy.get("opponent_artifact_dir", DEFAULT_OPPONENT_ARTIFACT_DIR),
        ),
        fitted=cast("FittedLeagueOpponents | None", legacy.get("fitted")),
    )


@dataclass(frozen=True)
class _NewDraftSessionRequest:
    artifact: Path
    managers: str
    slot: int
    ir: bool
    eliminated: str
    temperature: float
    seed: int
    rollouts: int
    opponents: str
    opponent_artifact: Path


def _new_draft_session(request: _NewDraftSessionRequest) -> DraftSession:
    manager_ids = parse_managers(request.managers)
    manager_count = len(manager_ids)
    _validate_draft_slot(request.slot, manager_count)
    eliminated_teams = [token for token in request.eliminated.split(",") if token.strip()]
    opponents_kind = resolve_opponents_kind(request.opponents, request.opponent_artifact)
    return DraftSession.from_artifact(
        DraftSessionArtifactRequest(
            artifact_dir=request.artifact,
            manager_count=manager_count,
            slot=request.slot,
            ir=request.ir,
            eliminated=eliminated_teams,
            temperature=request.temperature,
            seed=request.seed,
            rollouts=request.rollouts,
            managers=manager_ids,
            opponents=opponents_kind,
            opponent_artifact_dir=request.opponent_artifact,
        )
    )


def _resume_draft_session(resume: Path, session: Path | None) -> None:
    session_path = _resume_session_path(resume, session)
    _run_loop(DraftSession.resume(resume), session_path)


def _start_new_draft_session(
    artifact: Path,
    managers: str,
    slot: int,
    ir: bool,
    eliminated: str,
    temperature: float,
    seed: int,
    rollouts: int,
    opponents: str,
    opponent_artifact: Path,
    session: Path | None,
) -> None:
    session_path = _new_session_path(session)
    new_session = _new_draft_session(
        _NewDraftSessionRequest(
            artifact=artifact,
            managers=managers,
            slot=slot,
            ir=ir,
            eliminated=eliminated,
            temperature=temperature,
            seed=seed,
            rollouts=rollouts,
            opponents=opponents,
            opponent_artifact=opponent_artifact,
        )
    )
    _run_loop(new_session, session_path)


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
        _resume_draft_session(resume, session)
        return
    if artifact is None:
        raise typer.BadParameter("provide --artifact <dir> (or --resume <session.json>)")
    _start_new_draft_session(
        artifact,
        managers,
        slot,
        ir,
        eliminated,
        temperature,
        seed,
        rollouts,
        opponents,
        opponent_artifact,
        session,
    )


def _same_path(left: Path, right: Path) -> bool:
    """Return whether two paths identify the same file or normalized location."""
    try:
        return left.samefile(right)
    except (FileNotFoundError, OSError):
        return left.resolve(strict=False) == right.resolve(strict=False)
