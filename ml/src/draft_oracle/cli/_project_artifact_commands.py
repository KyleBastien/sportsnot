"""Projection, recommendation, and draft-assistant CLI commands.

Each command's options are declared once, as the fields of a frozen request dataclass
(``field(metadata=option(...))``); ``_request_commands.register_request_command`` turns
the dataclass into the Typer command and calls the ``run_*`` function with the request.
"""

from __future__ import annotations

import random as _random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import typer

from draft_oracle.cli._project_defaults import (
    DEFAULT_ARCHIVE_DIR,
    DEFAULT_ARTIFACTS_ROOT,
    DEFAULT_NORMALIZED_DIR,
    DEFAULT_OPPONENT_ARTIFACT_DIR,
)
from draft_oracle.cli._request_commands import option

if TYPE_CHECKING:
    from draft_oracle.optimize.opponents import FittedLeagueOpponents
    from draft_oracle.optimize.recommend import Recommendation
    from draft_oracle.optimize.simulator import DraftAsset, DraftState, OpponentModel
    from draft_oracle.projection_artifact import ProjectArtifactConfig, ProjectArtifactResult


DEFAULT_SEED = 20260827
DEFAULT_TEMPERATURE = 0.3
DEFAULT_ROLLOUTS = 500

# One ``typer.Option`` per CLI option; shared between commands where the meaning is the same.
_SEASON = typer.Option(help="Playoff season end year, e.g. 2026.")
_ROUND = typer.Option("--round", help="Playoff round number (1-4).")
_NORMALIZED_DIR = typer.Option(help="Directory holding normalized Parquet tables.")
_ARTIFACT_DIR = typer.Option(help="Projection artifact directory (has skaters/teams parquet).")
_DRAFT_ARTIFACT = typer.Option(help="Projection artifact directory (skaters/teams parquet).")
_ARTIFACTS_ROOT = typer.Option(help="Root directory for the written artifact.")
_SNAPSHOT = typer.Option(help="Pin a frozen snapshot id (defaults to the live tables).")
_LEAGUE_SIZE = typer.Option(help="League size (2-12); sets VOR replacement levels.")
_MANAGER_IDS = typer.Option(help="League size (2-12) or comma seat ids (e.g. ben,judah,levi,kyle).")
_SEAT = typer.Option(help="Owner's snake seat (1-based).")
_SLOT = typer.Option("--slot", help="Your snake seat (1-based).")
_IR = typer.Option("--ir/--no-ir", help="League uses IR slots (+1 F, +1 D).")
_PROJECT_IR = typer.Option("--ir/--no-ir", help="League uses IR slots (+1 F, +1 D per manager).")
_TEMPERATURE = typer.Option(help="Greedy opponent softmax temperature.")
_SEED = typer.Option(help="Deterministic seed.")
_PROJECTION_SEED = typer.Option(help="Deterministic training/MC seed.")
_OPPONENTS = typer.Option(
    help="Opponent model: greedy, fitted, or auto (fitted when the artifact exists)."
)
_OPPONENT_ARTIFACT = typer.Option(help="Committed opponent-model artifact directory (fitted path).")
_ROLLOUTS = typer.Option(help="Monte-Carlo rollouts per candidate.")
_DRAFT_ROLLOUTS = typer.Option(help="Monte-Carlo rollouts per candidate for recommend.")
_SLOT_ROLLOUTS = typer.Option(help="Monte-Carlo rollouts per turn in the slot report.")
_DEPTH = typer.Option(help="Owner turns simulated vs. opponents (0 = full depth).")
_ARCHIVE_DIR = typer.Option(help="Committed NHL archive directory (for the ingest refresh).")
_NO_REFRESH = typer.Option("--no-refresh", help="Skip the idempotent ingest refresh (offline).")
_SLOT_STRATEGIES = typer.Option(
    "--slot-strategies/--no-slot-strategies",
    help="Emit slot_strategies.md (per-slot draft plan, US-023).",
)
_ELIMINATED = typer.Option(help="Comma-separated eliminated team abbrevs.")
_SESSION = typer.Option(help="Session-log path (defaults to ./draft-session.json).")
_RESUME = typer.Option("--resume", help="Resume a saved session JSON instead.")


@dataclass(frozen=True)
class _ProjectConfigRequest:
    seed: int
    managers: int
    ir: bool
    no_refresh: bool
    slot_strategies: bool
    slot_rollouts: int


@dataclass(frozen=True)
class _RecommendInputsRequest:
    artifact_dir: Path
    managers: str
    seat: int
    ir: bool
    temperature: float
    opponents: str
    opponent_artifact: Path


@dataclass(frozen=True)
class _BuildRecommendSetupRequest:
    manager_ids: list[str]
    seat: int
    ir: bool
    pool: Sequence[DraftAsset]
    opponents_kind: str
    opponent_artifact: Path
    temperature: float


@dataclass(frozen=True)
class ProjectCommandRequest:
    """Options of ``oracle project`` — every field is one CLI option."""

    season: int = field(metadata=option(_SEASON))
    playoff_round: int = field(metadata=option(_ROUND))
    normalized_dir: Path = field(default=DEFAULT_NORMALIZED_DIR, metadata=option(_NORMALIZED_DIR))
    artifacts_root: Path = field(default=DEFAULT_ARTIFACTS_ROOT, metadata=option(_ARTIFACTS_ROOT))
    snapshot: str = field(default="", metadata=option(_SNAPSHOT))
    managers: int = field(default=4, metadata=option(_LEAGUE_SIZE))
    ir: bool = field(default=False, metadata=option(_PROJECT_IR))
    archive_dir: Path = field(default=DEFAULT_ARCHIVE_DIR, metadata=option(_ARCHIVE_DIR))
    no_refresh: bool = field(default=False, metadata=option(_NO_REFRESH))
    seed: int = field(default=DEFAULT_SEED, metadata=option(_PROJECTION_SEED))
    slot_strategies: bool = field(default=True, metadata=option(_SLOT_STRATEGIES))
    slot_rollouts: int = field(default=60, metadata=option(_SLOT_ROLLOUTS))


@dataclass(frozen=True)
class RecommendCommandRequest:
    """Options of ``oracle recommend`` — every field is one CLI option."""

    artifact_dir: Path = field(metadata=option(_ARTIFACT_DIR))
    managers: str = field(default="4", metadata=option(_MANAGER_IDS))
    seat: int = field(default=1, metadata=option(_SEAT))
    ir: bool = field(default=False, metadata=option(_IR))
    rollouts: int = field(default=DEFAULT_ROLLOUTS, metadata=option(_ROLLOUTS))
    depth: int = field(default=0, metadata=option(_DEPTH))
    temperature: float = field(default=DEFAULT_TEMPERATURE, metadata=option(_TEMPERATURE))
    seed: int = field(default=DEFAULT_SEED, metadata=option(_SEED))
    opponents: str = field(default="auto", metadata=option(_OPPONENTS))
    opponent_artifact: Path = field(
        default=DEFAULT_OPPONENT_ARTIFACT_DIR, metadata=option(_OPPONENT_ARTIFACT)
    )


@dataclass(frozen=True)
class DraftCommandRequest:
    """Options of ``oracle draft`` — every field is one CLI option."""

    artifact: Path | None = field(default=None, metadata=option(_DRAFT_ARTIFACT))
    managers: str = field(default="4", metadata=option(_MANAGER_IDS))
    slot: int = field(default=1, metadata=option(_SLOT))
    ir: bool = field(default=False, metadata=option(_IR))
    eliminated: str = field(default="", metadata=option(_ELIMINATED))
    session: Path | None = field(default=None, metadata=option(_SESSION))
    resume: Path | None = field(default=None, metadata=option(_RESUME))
    temperature: float = field(default=DEFAULT_TEMPERATURE, metadata=option(_TEMPERATURE))
    seed: int = field(default=DEFAULT_SEED, metadata=option(_SEED))
    rollouts: int = field(default=DEFAULT_ROLLOUTS, metadata=option(_DRAFT_ROLLOUTS))
    opponents: str = field(default="auto", metadata=option(_OPPONENTS))
    opponent_artifact: Path = field(
        default=DEFAULT_OPPONENT_ARTIFACT_DIR, metadata=option(_OPPONENT_ARTIFACT)
    )


def _maybe_refresh_normalized_archive(
    *,
    no_refresh: bool,
    snapshot: str,
    archive_dir: Path,
    normalized_dir: Path,
) -> None:
    if no_refresh or snapshot:
        return
    from draft_oracle.ingest.normalize import normalize_archive

    normalize_archive(archive_dir=archive_dir, out_dir=normalized_dir)


def _project_config(request: _ProjectConfigRequest) -> ProjectArtifactConfig:
    from draft_oracle.optimize.slot_strategies import SlotStrategyConfig
    from draft_oracle.projection_artifact import ProjectArtifactConfig

    return ProjectArtifactConfig(
        seed=request.seed,
        managers=request.managers,
        ir=request.ir,
        no_refresh=request.no_refresh,
        slot_strategies=request.slot_strategies,
        slot_strategy_config=SlotStrategyConfig(
            seed=request.seed,
            rollouts=request.slot_rollouts,
        ),
    )


def _slot_summary_label(slots: Mapping[str, object]) -> str:
    configured = slots.get("opponent_label")
    if isinstance(configured, str):
        return configured
    return "fitted" if bool(slots.get("fitted_opponents", False)) else "greedy"


def _echo_project_summary(result: ProjectArtifactResult, out_dir: Path) -> None:
    counts = result.manifest["counts"]
    scarcity = result.manifest["scarcity"]
    typer.echo(f"Projection artifact -> {out_dir}")
    typer.echo(
        f"  season {result.season} round {result.playoff_round} (as of {result.as_of_cutoff})"
    )
    typer.echo(
        f"  eligible: {counts['eligible_teams']} teams / "
        f"{counts['skaters_projected']} skaters ({counts['skaters_injured']} injured)"
    )
    repl = scarcity["replacement_level"]
    typer.echo(
        f"  VOR: {scarcity['managers']} managers, IR {'on' if scarcity['ir'] else 'off'}; "
        f"replacement F {repl['F']:.2f} / D {repl['D']:.2f} / G {repl['G']:.2f}"
    )
    typer.echo(f"  snapshot id: {result.manifest['snapshot_id']}")
    slots = result.manifest.get("slot_strategies")
    if slots:
        typer.echo(
            f"  slot strategies: {len(slots['slots'])} slots"
            f" ({_slot_summary_label(slots)} opponents);"
            f" best slot {slots['best_slot']}"
        )
    for warning in result.warnings:
        typer.echo(f"  warning: {warning}")


def run_project(request: ProjectCommandRequest) -> None:
    """Precompute a self-contained projection artifact for one upcoming round.

    Refreshes ingest (idempotent, offline), builds as-of features, runs inference, and
    writes skaters/teams Parquet + CSV, cheatsheet.md, slot_strategies.md, and
    run_manifest.json under artifacts_root/<season>-r<round>/. Eliminated teams are
    excluded automatically.
    """
    from draft_oracle.projection_artifact import build_projection_artifact_from_normalized

    _maybe_refresh_normalized_archive(
        no_refresh=request.no_refresh,
        snapshot=request.snapshot,
        archive_dir=request.archive_dir,
        normalized_dir=request.normalized_dir,
    )
    result, out_dir = build_projection_artifact_from_normalized(
        season=request.season,
        playoff_round=request.playoff_round,
        normalized_dir=request.normalized_dir,
        artifacts_root=request.artifacts_root,
        snapshot=request.snapshot or None,
        config=_project_config(
            _ProjectConfigRequest(
                seed=request.seed,
                managers=request.managers,
                ir=request.ir,
                no_refresh=request.no_refresh,
                slot_strategies=request.slot_strategies,
                slot_rollouts=request.slot_rollouts,
            )
        ),
    )
    _echo_project_summary(result, out_dir)


@dataclass(frozen=True)
class _RecommendInputs:
    setup: _RecommendSetup
    label: str


def _recommend_inputs(request: _RecommendInputsRequest) -> _RecommendInputs:
    from draft_oracle.cli.draft import (
        opponent_label,
        parse_managers,
        resolve_opponents_kind,
    )
    from draft_oracle.optimize.recommend import build_pool_from_projection_artifact

    manager_ids = parse_managers(request.managers)
    _validate_seat(request.seat, len(manager_ids))
    opponents_kind = resolve_opponents_kind(request.opponents, request.opponent_artifact)
    pool = build_pool_from_projection_artifact(request.artifact_dir, ir=request.ir)
    setup = _build_recommend_setup(
        _BuildRecommendSetupRequest(
            manager_ids=manager_ids,
            seat=request.seat,
            ir=request.ir,
            pool=pool,
            opponents_kind=opponents_kind,
            opponent_artifact=request.opponent_artifact,
            temperature=request.temperature,
        )
    )
    return _RecommendInputs(
        setup=setup,
        label=opponent_label(opponents_kind, setup.fitted, manager_ids),
    )


def _recommendation_result(
    inputs: _RecommendInputs,
    *,
    rollouts: int,
    depth: int,
    seed: int,
) -> Recommendation:
    from draft_oracle.optimize.recommend import RecommendConfig, recommend_pick

    setup = inputs.setup
    _advance_to_owner(setup.state, setup.owner, setup.opponent_model, seed)
    config = RecommendConfig(rollouts=rollouts, depth=depth or None, seed=seed)
    return recommend_pick(
        setup.state,
        setup.owner,
        setup.opponent_model,
        config=config,
    )


def _echo_recommendation(result: Recommendation, label: str) -> None:
    typer.echo(f"Recommendation for {result.owner} (pick #{result.pick_index + 1}, {label}):")
    for line in result.report_lines():
        typer.echo(line)


@dataclass(frozen=True)
class _RecommendSetup:
    owner: str
    state: DraftState
    opponent_model: OpponentModel | Mapping[str, OpponentModel]
    fitted: FittedLeagueOpponents | None


def _validate_seat(seat: int, manager_count: int) -> None:
    if not 1 <= seat <= manager_count:
        raise typer.BadParameter(f"seat must be in 1..{manager_count}")


def _build_recommend_setup(request: _BuildRecommendSetupRequest) -> _RecommendSetup:
    from draft_oracle.optimize.opponents import load_committed_opponents
    from draft_oracle.optimize.simulator import DraftState, GreedyOpponentModel

    owner = request.manager_ids[request.seat - 1]
    state = DraftState.new(request.manager_ids, request.pool, allow_ir=request.ir)
    fitted = (
        load_committed_opponents(request.opponent_artifact)
        if request.opponents_kind == "fitted"
        else None
    )
    if request.opponents_kind == "fitted" and fitted is None:
        raise typer.BadParameter(
            f"--opponents fitted needs a committed artifact at {request.opponent_artifact}"
        )
    if fitted is not None:
        return _RecommendSetup(owner, state, fitted.as_mapping(request.manager_ids), fitted)
    greedy = GreedyOpponentModel(temperature=request.temperature, need_weight=4.0)
    return _RecommendSetup(owner, state, greedy, None)


def _advance_to_owner(
    state: DraftState,
    owner: str,
    opponent_model: OpponentModel | Mapping[str, OpponentModel],
    seed: int,
) -> None:
    rng = _random.Random(seed)
    while state.current_manager != owner:
        current = state.current_manager
        state.apply_pick(_model_for(opponent_model, current).pick(state, current, rng))


def _model_for(
    opponent_model: OpponentModel | Mapping[str, OpponentModel], manager: str
) -> OpponentModel:
    if isinstance(opponent_model, Mapping):
        return opponent_model[manager]
    return opponent_model


def run_recommend(request: RecommendCommandRequest) -> None:
    """Recommend the best pick right now via multi-step Monte-Carlo rollout (US-021).

    Builds a fresh draft from a projection artifact, puts the owner on the clock at
    ``seat``, and prints the top-5 explained recommendations (VOR, survival, need,
    delta vs. #2). Opponents default to the committed *fitted* league model when its
    artifact is present; ``--opponents greedy`` forces the vectorized fallback, and
    passing real names to ``--managers`` attaches each manager's fitted model to their
    real seat.
    """
    inputs = _recommend_inputs(
        _RecommendInputsRequest(
            artifact_dir=request.artifact_dir,
            managers=request.managers,
            seat=request.seat,
            ir=request.ir,
            temperature=request.temperature,
            opponents=request.opponents,
            opponent_artifact=request.opponent_artifact,
        )
    )
    result = _recommendation_result(
        inputs,
        rollouts=request.rollouts,
        depth=request.depth,
        seed=request.seed,
    )
    _echo_recommendation(result, inputs.label)


def run_draft(request: DraftCommandRequest) -> None:
    """Start the interactive, artifact-powered draft assistant (US-024)."""
    from draft_oracle.cli.draft import draft

    draft(
        artifact=request.artifact,
        managers=request.managers,
        slot=request.slot,
        ir=request.ir,
        eliminated=request.eliminated,
        session=request.session,
        resume=request.resume,
        temperature=request.temperature,
        seed=request.seed,
        rollouts=request.rollouts,
        opponents=request.opponents,
        opponent_artifact=request.opponent_artifact,
    )
