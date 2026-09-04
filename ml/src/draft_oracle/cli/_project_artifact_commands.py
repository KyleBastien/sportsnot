"""Projection, recommendation, and draft-assistant CLI commands."""

from __future__ import annotations

import argparse
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


_NormalizedDirOption = Annotated[
    Path,
    typer.Option(help="Directory holding normalized Parquet tables."),
]
_ArtifactDirOption = Annotated[
    Path,
    typer.Option(help="Projection artifact directory (has skaters/teams parquet)."),
]
_ArtifactsRootOption = Annotated[
    Path,
    typer.Option(help="Root directory for the written artifact."),
]
_SnapshotOption = Annotated[
    str,
    typer.Option(help="Pin a frozen snapshot id (defaults to the live tables)."),
]
_ManagersOption = Annotated[
    int,
    typer.Option(help="League size (2-12); sets VOR replacement levels."),
]
_ManagersInputOption = Annotated[
    str,
    typer.Option(help="League size (2-12) or comma seat ids (e.g. ben,judah,levi,kyle)."),
]
_SeatOption = Annotated[int, typer.Option(help="Owner's snake seat (1-based).")]
_SlotOption = Annotated[int, typer.Option("--slot", help="Your snake seat (1-based).")]
_IrOption = Annotated[
    bool,
    typer.Option("--ir/--no-ir", help="League uses IR slots (+1 F, +1 D)."),
]
_DraftIrOption = Annotated[
    bool,
    typer.Option("--ir/--no-ir", help="League uses IR slots (+1 F, +1 D per manager)."),
]
_TemperatureOption = Annotated[float, typer.Option(help="Greedy opponent softmax temperature.")]
_SeedOption = Annotated[int, typer.Option(help="Deterministic seed.")]
_ProjectionSeedOption = Annotated[int, typer.Option(help="Deterministic training/MC seed.")]
_OpponentsOption = Annotated[
    str,
    typer.Option(help="Opponent model: greedy, fitted, or auto (fitted when the artifact exists)."),
]
_OpponentArtifactOption = Annotated[
    Path,
    typer.Option(help="Committed opponent-model artifact directory (fitted path)."),
]
_RolloutsOption = Annotated[int, typer.Option(help="Monte-Carlo rollouts per candidate.")]
_SlotRolloutsOption = Annotated[
    int,
    typer.Option(help="Monte-Carlo rollouts per turn in the slot report."),
]
_DepthOption = Annotated[
    int,
    typer.Option(help="Owner turns simulated vs. opponents (0 = full depth)."),
]
_ArchiveDirOption = Annotated[
    Path,
    typer.Option(help="Committed NHL archive directory (for the ingest refresh)."),
]
_NoRefreshOption = Annotated[
    bool,
    typer.Option("--no-refresh", help="Skip the idempotent ingest refresh (offline)."),
]
_SlotStrategiesOption = Annotated[
    bool,
    typer.Option(
        "--slot-strategies/--no-slot-strategies",
        help="Emit slot_strategies.md (per-slot draft plan, US-023).",
    ),
]
_EliminatedOption = Annotated[str, typer.Option(help="Comma-separated eliminated team abbrevs.")]
_SessionPathOption = Annotated[
    Path | None,
    typer.Option(help="Session-log path (defaults to ./draft-session.json)."),
]
_ResumePathOption = Annotated[
    Path | None,
    typer.Option("--resume", help="Resume a saved session JSON instead."),
]


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
class _ProjectCommandRequest:
    season: int
    playoff_round: int
    normalized_dir: Path
    artifacts_root: Path
    snapshot: str
    managers: int
    ir: bool
    archive_dir: Path
    no_refresh: bool
    seed: int
    slot_strategies: bool
    slot_rollouts: int


@dataclass(frozen=True)
class _RecommendCommandRequest:
    artifact_dir: Path
    managers: str
    seat: int
    ir: bool
    rollouts: int
    depth: int
    temperature: float
    seed: int
    opponents: str
    opponent_artifact: Path


@dataclass(frozen=True)
class _DraftCommandRequest:
    artifact: Path | None
    managers: str
    slot: int
    ir: bool
    eliminated: str
    session: Path | None
    resume: Path | None
    temperature: float
    seed: int
    rollouts: int
    opponents: str
    opponent_artifact: Path


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
    ctx: typer.Context,
) -> None:
    """Precompute a self-contained projection artifact for one upcoming round.

    Refreshes ingest (idempotent, offline), builds as-of features, runs inference, and
    writes skaters/teams Parquet + CSV, cheatsheet.md, slot_strategies.md, and
    run_manifest.json under artifacts_root/<season>-r<round>/. Eliminated teams are
    excluded automatically.
    """
    _run_project(_parse_project_request(ctx.args))


def _run_project(request: _ProjectCommandRequest) -> None:
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


def recommend(
    ctx: typer.Context,
) -> None:
    """Recommend the best pick right now via multi-step Monte-Carlo rollout (US-021).

    Builds a fresh draft from a projection artifact, puts the owner on the clock at
    ``seat``, and prints the top-5 explained recommendations (VOR, survival, need,
    delta vs. #2). Opponents default to the committed *fitted* league model when its
    artifact is present; ``--opponents greedy`` forces the vectorized fallback, and
    passing real names to ``--managers`` attaches each manager's fitted model to their
    real seat.
    """
    request = _parse_recommend_request(ctx.args)
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


def draft_cmd(
    ctx: typer.Context,
) -> None:
    """Start the interactive, artifact-powered draft assistant (US-024)."""
    from draft_oracle.cli.draft import draft

    request = _parse_draft_request(ctx.args)
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


def _project_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="project",
        add_help=False,
        description="Precompute a self-contained projection artifact for one upcoming round.",
    )
    parser.add_argument("--season", type=int, required=True, help="Playoff season end year.")
    parser.add_argument(
        "--round", dest="playoff_round", type=int, required=True, help="Playoff round number (1-4)."
    )
    parser.add_argument(
        "--normalized-dir",
        type=Path,
        default=DEFAULT_NORMALIZED_DIR,
        help="Directory holding normalized Parquet tables.",
    )
    parser.add_argument(
        "--artifacts-root",
        type=Path,
        default=DEFAULT_ARTIFACTS_ROOT,
        help="Root directory for written artifact.",
    )
    parser.add_argument(
        "--snapshot",
        type=str,
        default="",
        help="Pin a frozen snapshot id (defaults to live tables).",
    )
    parser.add_argument(
        "--managers", type=int, default=4, help="League size (2-12); sets VOR replacement levels."
    )
    _add_ir_toggle(
        parser,
        help_on="League uses IR slots (+1 F, +1 D per manager).",
        help_off="League does not use IR slots.",
    )
    parser.add_argument(
        "--archive-dir",
        type=Path,
        default=DEFAULT_ARCHIVE_DIR,
        help="Committed NHL archive directory (for ingest refresh).",
    )
    parser.add_argument(
        "--no-refresh", action="store_true", help="Skip idempotent ingest refresh (offline)."
    )
    _add_seed_argument(parser, help_text="Deterministic training/MC seed.")
    _add_toggle_argument(
        parser,
        name="slot_strategies",
        help_on="Emit slot_strategies.md (per-slot draft plan, US-023).",
        help_off="Skip slot_strategies.md output.",
        default=True,
    )
    parser.add_argument(
        "--slot-rollouts",
        type=int,
        default=60,
        help="Monte-Carlo rollouts per turn in slot report.",
    )
    return parser


def _recommend_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="recommend",
        add_help=False,
        description="Recommend best pick right now via multi-step Monte-Carlo rollout.",
    )
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        required=True,
        help="Projection artifact directory (has skaters/teams parquet).",
    )
    _add_manager_ids_argument(parser)
    parser.add_argument("--seat", type=int, default=1, help="Owner's snake seat (1-based).")
    _add_ir_toggle(
        parser,
        help_on="League uses IR slots (+1 F, +1 D).",
        help_off="League does not use IR slots.",
    )
    parser.add_argument(
        "--rollouts", type=int, default=500, help="Monte-Carlo rollouts per candidate."
    )
    parser.add_argument(
        "--depth", type=int, default=0, help="Owner turns simulated vs. opponents (0 = full depth)."
    )
    parser.add_argument(
        "--temperature", type=float, default=0.3, help="Greedy opponent softmax temperature."
    )
    _add_seed_argument(parser, help_text="Deterministic seed.")
    _add_opponent_arguments(parser)
    return parser


def _draft_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="draft",
        add_help=False,
        description="Start interactive, artifact-powered draft assistant.",
    )
    parser.add_argument(
        "--artifact",
        type=Path,
        default=None,
        help="Projection artifact directory (skaters/teams parquet).",
    )
    _add_manager_ids_argument(parser)
    parser.add_argument("--slot", type=int, default=1, help="Your snake seat (1-based).")
    _add_ir_toggle(
        parser,
        help_on="League uses IR slots (+1 F, +1 D).",
        help_off="League does not use IR slots.",
    )
    parser.add_argument(
        "--eliminated", type=str, default="", help="Comma-separated eliminated team abbrevs."
    )
    parser.add_argument(
        "--session",
        type=Path,
        default=None,
        help="Session-log path (defaults to ./draft-session.json).",
    )
    parser.add_argument(
        "--resume", type=Path, default=None, help="Resume a saved session JSON instead."
    )
    parser.add_argument(
        "--temperature", type=float, default=0.3, help="Greedy opponent softmax temperature."
    )
    _add_seed_argument(parser, help_text="Deterministic seed.")
    parser.add_argument(
        "--rollouts",
        type=int,
        default=500,
        help="Monte-Carlo rollouts per candidate for recommend.",
    )
    _add_opponent_arguments(parser)
    return parser


def _parse_project_request(args: list[str]) -> _ProjectCommandRequest:
    parser = _project_parser()
    namespace = _parse_args(parser, args)
    return _ProjectCommandRequest(
        season=namespace.season,
        playoff_round=namespace.playoff_round,
        normalized_dir=namespace.normalized_dir,
        artifacts_root=namespace.artifacts_root,
        snapshot=namespace.snapshot,
        managers=namespace.managers,
        ir=namespace.ir,
        archive_dir=namespace.archive_dir,
        no_refresh=namespace.no_refresh,
        seed=namespace.seed,
        slot_strategies=namespace.slot_strategies,
        slot_rollouts=namespace.slot_rollouts,
    )


def _parse_recommend_request(args: list[str]) -> _RecommendCommandRequest:
    parser = _recommend_parser()
    namespace = _parse_args(parser, args)
    return _RecommendCommandRequest(
        artifact_dir=namespace.artifact_dir,
        managers=namespace.managers,
        seat=namespace.seat,
        ir=namespace.ir,
        rollouts=namespace.rollouts,
        depth=namespace.depth,
        temperature=namespace.temperature,
        seed=namespace.seed,
        opponents=namespace.opponents,
        opponent_artifact=namespace.opponent_artifact,
    )


def _parse_draft_request(args: list[str]) -> _DraftCommandRequest:
    parser = _draft_parser()
    namespace = _parse_args(parser, args)
    return _DraftCommandRequest(
        artifact=namespace.artifact,
        managers=namespace.managers,
        slot=namespace.slot,
        ir=namespace.ir,
        eliminated=namespace.eliminated,
        session=namespace.session,
        resume=namespace.resume,
        temperature=namespace.temperature,
        seed=namespace.seed,
        rollouts=namespace.rollouts,
        opponents=namespace.opponents,
        opponent_artifact=namespace.opponent_artifact,
    )


def _parse_args(
    parser: argparse.ArgumentParser,
    args: list[str],
) -> argparse.Namespace:
    if any(arg in {"-h", "--help"} for arg in args):
        typer.echo(parser.format_help().rstrip())
        raise typer.Exit()
    namespace, extras = parser.parse_known_args(args)
    if extras:
        raise typer.BadParameter(f"unknown {parser.prog} args: {' '.join(extras)}")
    return namespace


def _add_toggle_argument(
    parser: argparse.ArgumentParser,
    *,
    name: str,
    help_on: str,
    help_off: str,
    default: bool,
) -> None:
    flag = name.replace("_", "-")
    parser.add_argument(f"--{flag}", dest=name, action="store_true", help=help_on)
    parser.add_argument(f"--no-{flag}", dest=name, action="store_false", help=help_off)
    parser.set_defaults(**{name: default})


def _add_ir_toggle(
    parser: argparse.ArgumentParser,
    *,
    help_on: str,
    help_off: str,
) -> None:
    _add_toggle_argument(parser, name="ir", help_on=help_on, help_off=help_off, default=False)


def _add_seed_argument(parser: argparse.ArgumentParser, *, help_text: str) -> None:
    parser.add_argument("--seed", type=int, default=20260827, help=help_text)


def _add_manager_ids_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--managers", type=str, default="4", help="League size (2-12) or comma seat ids."
    )


def _add_opponent_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--opponents", type=str, default="auto", help="Opponent model: greedy, fitted, or auto."
    )
    parser.add_argument(
        "--opponent-artifact",
        type=Path,
        default=DEFAULT_OPPONENT_ARTIFACT_DIR,
        help="Committed opponent-model artifact directory (fitted path).",
    )
