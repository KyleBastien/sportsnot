"""Model training/evaluation, strategy-comparison, and backtest CLI commands.

``compare-strategies`` and ``backtest`` declare their options as request-dataclass
fields (see ``_request_commands``); the ``train-*`` commands are small enough to keep
plain Typer signatures.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated

import typer

from draft_oracle.cli._project_defaults import (
    DEFAULT_BACKTEST_ROOT,
    DEFAULT_MODEL_ARTIFACT_DIR,
    DEFAULT_NORMALIZED_DIR,
    DEFAULT_OPPONENT_ARTIFACT_DIR,
    DEFAULT_PROJECTION_ARTIFACT_DIR,
    DEFAULT_RETURN_TIME_ARTIFACT_DIR,
    DEFAULT_SERIES_SIM_ARTIFACT_DIR,
    DEFAULT_SHUTOUT_ARTIFACT_DIR,
    DEFAULT_SKATER_PRODUCTION_ARTIFACT_DIR,
    STRATEGIES,
    Strategy,
)
from draft_oracle.cli._request_commands import option

NormalizedDirOption = Annotated[
    Path,
    typer.Option(help="Directory holding normalized Parquet tables."),
]
ReportArtifactDirOption = Annotated[
    Path,
    typer.Option(help="Output directory for the report + manifest."),
]
TrainingSeedOption = Annotated[int, typer.Option(help="Deterministic training seed.")]
ProjectionSeedOption = Annotated[int, typer.Option(help="Deterministic training/MC seed.")]
DeterministicSeedOption = Annotated[int, typer.Option(help="Deterministic seed.")]


_SIM_LEAGUE_SIZE = typer.Option(help="League size for the simulated drafts.")
_SIM_N_DRAFTS = typer.Option(help="Seeded simulated drafts (>=200).")
_SIM_ROLLOUTS = typer.Option(help="Rollouts per recommendation.")
_MAX_CANDIDATES = typer.Option(help="Candidates rolled out.")
_SEED = typer.Option(help="Deterministic seed.")
_SEASONS = typer.Option(help="Playoff end years to replay, e.g. 2022.")
_NORMALIZED_DIR = typer.Option(help="Directory holding normalized Parquet tables.")
_BACKTEST_ROOT = typer.Option(help="Root directory for the written backtest run.")
_SNAPSHOT = typer.Option(help="Pin a frozen snapshot id (defaults to the live tables).")
_LEAGUE_SIZE = typer.Option(help="League size (2-12).")
_IR = typer.Option("--ir/--no-ir", help="League uses IR slots (+1 F, +1 D).")
_N_DRAFTS = typer.Option(help="Seeded drafts per (round, slot).")
_ROLLOUTS = typer.Option(help="Monte-Carlo rollouts per oracle pick.")
_STRATEGY = typer.Option(
    "--strategy", help="Oracle policies to seat (oracle/greedy_vor/one_step/random_legal)."
)


@dataclass(frozen=True)
class CompareStrategiesRequest:
    """Options of ``oracle compare-strategies`` — every field is one CLI option."""

    normalized_dir: Path = field(default=DEFAULT_NORMALIZED_DIR, metadata=option(_NORMALIZED_DIR))
    managers: int = field(default=4, metadata=option(_SIM_LEAGUE_SIZE))
    n_drafts: int = field(default=200, metadata=option(_SIM_N_DRAFTS))
    rollouts: int = field(default=40, metadata=option(_SIM_ROLLOUTS))
    max_candidates: int = field(default=6, metadata=option(_MAX_CANDIDATES))
    seed: int = field(default=20260827, metadata=option(_SEED))


@dataclass(frozen=True)
class BacktestCommandRequest:
    """Options of ``oracle backtest`` — every field is one CLI option."""

    seasons: list[int] = field(metadata=option(_SEASONS))
    normalized_dir: Path = field(default=DEFAULT_NORMALIZED_DIR, metadata=option(_NORMALIZED_DIR))
    backtest_root: Path = field(default=DEFAULT_BACKTEST_ROOT, metadata=option(_BACKTEST_ROOT))
    snapshot: str = field(default="", metadata=option(_SNAPSHOT))
    managers: int = field(default=4, metadata=option(_LEAGUE_SIZE))
    ir: bool = field(default=False, metadata=option(_IR))
    n_drafts: int = field(default=1, metadata=option(_N_DRAFTS))
    rollouts: int = field(default=40, metadata=option(_ROLLOUTS))
    strategies: list[str] | None = field(default=None, metadata=option(_STRATEGY))
    seed: int = field(default=20260827, metadata=option(_SEED))


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _echo_chosen_model(chosen_model_type: str) -> None:
    typer.echo(f"  chosen model: {chosen_model_type}")


def _echo_held_out_seasons(test_years: Iterable[object]) -> None:
    typer.echo(f"  held-out seasons: {list(test_years)}")


def _echo_metrics(metric: str, *named_values: tuple[str, float]) -> None:
    rendered = " / ".join(f"{name} {value:.4f}" for name, value in named_values)
    typer.echo(f"  {metric}: {rendered}")


def train_game_win(
    normalized_dir: NormalizedDirOption = DEFAULT_NORMALIZED_DIR,
    artifact_dir: ReportArtifactDirOption = DEFAULT_MODEL_ARTIFACT_DIR,
    no_odds: Annotated[
        bool,
        typer.Option("--no-odds", help="Train stat-only (skip the market features)."),
    ] = False,
    seed: TrainingSeedOption = 20260827,
) -> None:
    """Train the per-game win model; write the evaluation report + manifest."""
    from draft_oracle.models.game_win import GameWinConfig, train_game_win_from_normalized

    result = train_game_win_from_normalized(
        normalized_dir=normalized_dir,
        artifact_dir=artifact_dir,
        config=GameWinConfig(seed=seed),
        use_odds=not no_odds,
    )
    typer.echo(f"Per-game win model -> {artifact_dir}")
    _echo_chosen_model(result.chosen_model_type)
    _echo_metrics(
        "test Brier",
        ("market+stats", result.test_brier_market),
        ("stats-only", result.test_brier_stats_only),
    )
    _echo_metrics(
        "baselines",
        ("coin-flip", result.test_brier_coin_flip),
        ("higher-points", result.test_brier_higher_points),
    )
    typer.echo(f"  beats both baselines: {_yes_no(result.beats_both_baselines)}")


def train_shutout(
    normalized_dir: NormalizedDirOption = DEFAULT_NORMALIZED_DIR,
    artifact_dir: ReportArtifactDirOption = DEFAULT_SHUTOUT_ARTIFACT_DIR,
    seed: TrainingSeedOption = 20260827,
) -> None:
    """Train the shutout-probability model; write the evaluation report + manifest."""
    from draft_oracle.models.shutout import ShutoutConfig, train_shutout_from_normalized

    result = train_shutout_from_normalized(
        normalized_dir=normalized_dir,
        artifact_dir=artifact_dir,
        config=ShutoutConfig(seed=seed),
    )
    typer.echo(f"Shutout model -> {artifact_dir}")
    _echo_chosen_model(result.chosen_model_type)
    _echo_metrics(
        "test Brier",
        ("model", result.test_brier_model),
        ("base-rate", result.test_brier_base_rate),
    )
    typer.echo(
        f"  calibration: observed {result.test_observed_rate:.4f} / "
        f"predicted {result.test_predicted_rate:.4f} "
        f"(rel err {result.calibration_rel_error:.1%})"
    )
    typer.echo(f"  within +/-25%: {_yes_no(result.calibrated_within_tolerance)}")


def train_skater_production(
    normalized_dir: NormalizedDirOption = DEFAULT_NORMALIZED_DIR,
    artifact_dir: ReportArtifactDirOption = DEFAULT_SKATER_PRODUCTION_ARTIFACT_DIR,
    seed: TrainingSeedOption = 20260827,
) -> None:
    """Train the skater per-game production model; write the report + manifest."""
    from draft_oracle.models.skater_production import (
        SkaterProductionConfig,
        train_skater_production_from_normalized,
    )

    result = train_skater_production_from_normalized(
        normalized_dir=normalized_dir,
        artifact_dir=artifact_dir,
        config=SkaterProductionConfig(seed=seed),
    )
    typer.echo(f"Skater production model -> {artifact_dir}")
    _echo_chosen_model(result.chosen_model_type)
    _echo_metrics(
        "test MAE",
        ("model", result.test_mae_model),
        ("reg-ppg", result.test_mae_baseline_reg),
        ("mean", result.test_mae_baseline_mean),
    )
    _echo_metrics(
        "test Spearman",
        ("model", result.test_spearman_model),
        ("reg-ppg", result.test_spearman_baseline_reg),
    )
    typer.echo(f"  beats reg-ppg baseline: {_yes_no(result.beats_reg_baseline)}")
    typer.echo(f"  cold cases (test): {result.n_cold_cases_test}")


def train_return_time(
    normalized_dir: NormalizedDirOption = DEFAULT_NORMALIZED_DIR,
    artifact_dir: ReportArtifactDirOption = DEFAULT_RETURN_TIME_ARTIFACT_DIR,
    seed: TrainingSeedOption = 20260827,
) -> None:
    """Calibrate the injury return-time model on archive absence spells."""
    from draft_oracle.models.returns import ReturnTimeConfig, train_return_time_from_normalized

    result = train_return_time_from_normalized(
        normalized_dir=normalized_dir,
        artifact_dir=artifact_dir,
        config=ReturnTimeConfig(seed=seed),
    )
    typer.echo(f"Return-time model -> {artifact_dir}")
    typer.echo(f"  spells retained: {result.n_spells_total}")
    typer.echo(
        f"  spell length: mean {result.mean_spell:.2f} / "
        f"median {result.median_spell:.1f} / p90 {result.p90_spell:.1f}"
    )
    _echo_held_out_seasons(result.test_years)
    typer.echo(f"  calibration MAE (survival): {result.calibration_mae:.4f}")


def eval_series_sim(
    normalized_dir: NormalizedDirOption = DEFAULT_NORMALIZED_DIR,
    artifact_dir: ReportArtifactDirOption = DEFAULT_SERIES_SIM_ARTIFACT_DIR,
    seed: TrainingSeedOption = 20260827,
) -> None:
    """Calibrate the best-of-7 series simulator; write the report + manifest."""
    from draft_oracle.models.series_sim import SeriesSimConfig, evaluate_series_sim_from_normalized

    result = evaluate_series_sim_from_normalized(
        normalized_dir=normalized_dir,
        artifact_dir=artifact_dir,
        config=SeriesSimConfig(seed=seed),
    )
    typer.echo(f"Series simulator -> {artifact_dir}")
    _echo_held_out_seasons(result.test_years)
    typer.echo(f"  series scored: {result.n_series_scored} (skipped {result.n_series_skipped})")
    _echo_metrics(
        "series-winner Brier",
        ("model", result.brier_series),
        ("higher-seed", result.brier_higher_seed),
        ("coin", result.brier_coin_flip),
    )


def project_skaters(
    normalized_dir: NormalizedDirOption = DEFAULT_NORMALIZED_DIR,
    artifact_dir: ReportArtifactDirOption = DEFAULT_PROJECTION_ARTIFACT_DIR,
    seed: ProjectionSeedOption = 20260827,
) -> None:
    """Evaluate skater round-point projections with uncertainty; write report + manifest."""
    from draft_oracle.models.projections import (
        ProjectionConfig,
        evaluate_skater_projections_from_normalized,
    )

    result = evaluate_skater_projections_from_normalized(
        normalized_dir=normalized_dir,
        artifact_dir=artifact_dir,
        config=ProjectionConfig(seed=seed),
    )
    typer.echo(f"Skater round projections -> {artifact_dir}")
    _echo_held_out_seasons(result.test_years)
    typer.echo(
        f"  skater-rounds projected: {result.n_projected} (skipped {result.n_skipped_no_series})"
    )
    _echo_metrics(
        "test MAE",
        ("model", result.test_mae_model),
        ("reg-ppg", result.test_mae_baseline_reg),
        ("prev-round", result.test_mae_baseline_prev),
    )
    _echo_metrics(
        "test Spearman",
        ("model", result.test_spearman_model),
        ("reg-ppg", result.test_spearman_baseline_reg),
        ("prev-round", result.test_spearman_baseline_prev),
    )
    typer.echo(f"  beats both baselines: {_yes_no(result.beats_both_baselines)}")


def train_opponents(
    normalized_dir: NormalizedDirOption = DEFAULT_NORMALIZED_DIR,
    artifact_dir: ReportArtifactDirOption = DEFAULT_OPPONENT_ARTIFACT_DIR,
    seed: TrainingSeedOption = 20260827,
) -> None:
    """Fit the league-history opponent model; write the validation report + manifest."""
    from draft_oracle.optimize.opponents import (
        OpponentFitConfig,
        train_opponent_model_from_normalized,
    )

    result = train_opponent_model_from_normalized(
        normalized_dir=normalized_dir,
        artifact_dir=artifact_dir,
        config=OpponentFitConfig(seed=seed),
    )
    fitted = result.fitted
    evaluation = result.evaluation
    typer.echo(f"Opponent model -> {artifact_dir}")
    typer.echo(
        f"  league coefficients: rank {fitted.league.rank:+.3f} / "
        f"affinity {fitted.league.affinity:+.3f}"
    )
    typer.echo(
        f"  per-manager models: {len(fitted.per_manager)} "
        f"(min picks {fitted.config.min_manager_picks})"
    )
    for score in evaluation.membership:
        typer.echo(
            f"  {score.season} membership: fitted {score.fitted_accuracy:.3f} vs "
            f"greedy {score.greedy_accuracy:.3f} "
            f"({'beats' if score.fitted_beats_greedy else 'ties/loses'} fallback)"
        )
    if evaluation.per_pick is not None:
        pp = evaluation.per_pick
        typer.echo(f"  per-pick top-1: fitted {pp.fitted_top1:.3f} vs greedy {pp.greedy_top1:.3f}")
    typer.echo(
        f"  seasons beating fallback: "
        f"{evaluation.seasons_beating_fallback}/{len(evaluation.membership)}"
    )


def run_compare_strategies(request: CompareStrategiesRequest) -> None:
    """Run the committed multi-step vs. greedy-VOR vs. one-step comparison (US-021)."""
    from draft_oracle.optimize.recommend import (
        DEFAULT_RECOMMEND_ARTIFACT_DIR,
        RecommendationEvaluationRequest,
        evaluate_recommendation_strategies_from_normalized,
    )

    result = evaluate_recommendation_strategies_from_normalized(
        RecommendationEvaluationRequest(
            normalized_dir=request.normalized_dir,
            managers=request.managers,
            n_drafts=request.n_drafts,
            rollouts=request.rollouts,
            max_candidates=request.max_candidates,
            seed=request.seed,
        )
    )
    typer.echo(f"Strategy comparison -> {DEFAULT_RECOMMEND_ARTIFACT_DIR}")
    for line in result.report_lines():
        typer.echo(line)


def run_backtest(request: BacktestCommandRequest) -> None:
    """Replay historical playoff rounds end-to-end and score against actuals (US-025).

    Rebuilds as-of projections for every round, seats the oracle in each snake slot
    vs. the fitted (league-history) or greedy opponent model, and scores every roster
    with the real results through the rules engine. A hard leakage guard fails loudly
    if any round-N game leaks into the as-of inputs. Per-round intermediates and the
    run manifest are written under backtest_root/<run-id>/.
    """
    from draft_oracle.backtest.replay import BacktestConfig, run_backtest_from_normalized

    resolved: tuple[Strategy, ...] = tuple(
        _coerce_strategy(strategy) for strategy in (request.strategies or ["oracle"])
    )
    config = BacktestConfig(
        seed=request.seed,
        managers=request.managers,
        ir=request.ir,
        n_drafts=request.n_drafts,
        rollouts=request.rollouts,
        strategies=resolved,
    )
    result, out_dir = run_backtest_from_normalized(
        seasons=request.seasons,
        normalized_dir=request.normalized_dir,
        backtest_root=request.backtest_root,
        snapshot=request.snapshot or None,
        config=config,
    )
    typer.echo(f"Backtest run {result.run_id} -> {out_dir}")
    typer.echo(f"  report: {out_dir / 'report.md'}")
    typer.echo(f"  seasons: {', '.join(str(s) for s in result.seasons)}")
    typer.echo(f"  rounds replayed: {len(result.rounds)}")
    typer.echo(f"  strategies: {', '.join(config.strategies)}; drafts/slot: {request.n_drafts}")
    for round_result in result.rounds:
        drafts = len(round_result.slot_results)
        typer.echo(
            f"  {round_result.season} r{round_result.playoff_round} "
            f"(as of {round_result.as_of_cutoff}, {round_result.opponents_kind}): "
            f"{drafts} draft(s), leakage_ok={round_result.leakage_ok}"
        )
    typer.echo(f"  leakage_ok (all rounds): {all(r.leakage_ok for r in result.rounds)}")


def _coerce_strategy(value: str) -> Strategy:
    if value not in STRATEGIES:
        raise typer.BadParameter(f"unknown strategy {value!r}; choose from {list(STRATEGIES)}")
    return value
