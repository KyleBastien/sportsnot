"""Projection, recommendation, and draft-assistant CLI commands."""

from __future__ import annotations

import random as _random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer

from draft_oracle.cli._project_defaults import (
    DEFAULT_ARCHIVE_DIR,
    DEFAULT_ARTIFACTS_ROOT,
    DEFAULT_NORMALIZED_DIR,
    DEFAULT_OPPONENT_ARTIFACT_DIR,
)

if TYPE_CHECKING:
    from draft_oracle.optimize.opponents import FittedLeagueOpponents
    from draft_oracle.optimize.recommend import Recommendation
    from draft_oracle.optimize.simulator import DraftAsset, DraftState, OpponentModel
    from draft_oracle.projection_artifact import ProjectArtifactConfig, ProjectArtifactResult


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


def project(
    season: Annotated[int, typer.Option(help="Playoff season end year, e.g. 2026.")],
    playoff_round: Annotated[int, typer.Option("--round", help="Playoff round number (1-4).")],
    normalized_dir: Annotated[
        Path, typer.Option(help="Directory holding normalized Parquet tables.")
    ] = DEFAULT_NORMALIZED_DIR,
    artifacts_root: Annotated[
        Path, typer.Option(help="Root directory for the written artifact.")
    ] = DEFAULT_ARTIFACTS_ROOT,
    snapshot: Annotated[
        str, typer.Option(help="Pin a frozen snapshot id (defaults to the live tables).")
    ] = "",
    managers: Annotated[
        int, typer.Option(help="League size (2-12); sets VOR replacement levels.")
    ] = 4,
    ir: Annotated[
        bool,
        typer.Option("--ir/--no-ir", help="League uses IR slots (+1 F, +1 D per manager)."),
    ] = False,
    archive_dir: Annotated[
        Path, typer.Option(help="Committed NHL archive directory (for the ingest refresh).")
    ] = DEFAULT_ARCHIVE_DIR,
    no_refresh: Annotated[
        bool,
        typer.Option("--no-refresh", help="Skip the idempotent ingest refresh (offline)."),
    ] = False,
    seed: Annotated[int, typer.Option(help="Deterministic training/MC seed.")] = 20260827,
    slot_strategies: Annotated[
        bool,
        typer.Option(
            "--slot-strategies/--no-slot-strategies",
            help="Emit slot_strategies.md (per-slot draft plan, US-023).",
        ),
    ] = True,
    slot_rollouts: Annotated[
        int, typer.Option(help="Monte-Carlo rollouts per turn in the slot report.")
    ] = 60,
) -> None:
    """Precompute a self-contained projection artifact for one upcoming round.

    Refreshes ingest (idempotent, offline), builds as-of features, runs inference, and
    writes skaters/teams Parquet + CSV, cheatsheet.md, slot_strategies.md, and
    run_manifest.json under artifacts_root/<season>-r<round>/. Eliminated teams are
    excluded automatically.
    """
    from draft_oracle.projection_artifact import build_projection_artifact_from_normalized

    _maybe_refresh_normalized_archive(
        no_refresh=no_refresh,
        snapshot=snapshot,
        archive_dir=archive_dir,
        normalized_dir=normalized_dir,
    )
    result, out_dir = build_projection_artifact_from_normalized(
        season=season,
        playoff_round=playoff_round,
        normalized_dir=normalized_dir,
        artifacts_root=artifacts_root,
        snapshot=snapshot or None,
        config=_project_config(
            _ProjectConfigRequest(
            seed=seed,
            managers=managers,
            ir=ir,
            no_refresh=no_refresh,
            slot_strategies=slot_strategies,
            slot_rollouts=slot_rollouts,
            )
        ),
    )
    _echo_project_summary(result, out_dir)


def recommend(
    artifact_dir: Annotated[
        Path, typer.Option(help="Projection artifact directory (has skaters/teams parquet).")
    ],
    managers: Annotated[
        str,
        typer.Option(help="League size (2-12) or comma seat ids (e.g. ben,judah,levi,kyle)."),
    ] = "4",
    seat: Annotated[int, typer.Option(help="Owner's snake seat (1-based).")] = 1,
    ir: Annotated[
        bool, typer.Option("--ir/--no-ir", help="League uses IR slots (+1 F, +1 D).")
    ] = False,
    rollouts: Annotated[int, typer.Option(help="Monte-Carlo rollouts per candidate.")] = 500,
    depth: Annotated[
        int, typer.Option(help="Owner turns simulated vs. opponents (0 = full depth).")
    ] = 0,
    temperature: Annotated[float, typer.Option(help="Greedy opponent softmax temperature.")] = 0.3,
    seed: Annotated[int, typer.Option(help="Deterministic seed.")] = 20260827,
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
            artifact_dir=artifact_dir,
            managers=managers,
            seat=seat,
            ir=ir,
            temperature=temperature,
            opponents=opponents,
            opponent_artifact=opponent_artifact,
        )
    )
    result = _recommendation_result(inputs, rollouts=rollouts, depth=depth, seed=seed)
    _echo_recommendation(result, inputs.label)


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
    typer.echo(
        f"Recommendation for {result.owner} (pick #{result.pick_index + 1}, {label}):"
    )
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


def draft_cmd(
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
    temperature: Annotated[float, typer.Option(help="Greedy opponent softmax temperature.")] = 0.3,
    seed: Annotated[int, typer.Option(help="Deterministic seed.")] = 20260827,
    rollouts: Annotated[
        int, typer.Option(help="Monte-Carlo rollouts per candidate for recommend.")
    ] = 500,
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
    """Start the interactive, artifact-powered draft assistant (US-024)."""
    from draft_oracle.cli.draft import draft

    draft(
        artifact=artifact,
        managers=managers,
        slot=slot,
        ir=ir,
        eliminated=eliminated,
        session=session,
        resume=resume,
        temperature=temperature,
        seed=seed,
        rollouts=rollouts,
        opponents=opponents,
        opponent_artifact=opponent_artifact,
    )
