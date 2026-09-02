"""Model training, evaluation, and backtest CLI commands."""

from __future__ import annotations

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


def train_game_win(
    normalized_dir: Annotated[
        Path, typer.Option(help="Directory holding normalized Parquet tables.")
    ] = DEFAULT_NORMALIZED_DIR,
    artifact_dir: Annotated[
        Path, typer.Option(help="Output directory for the report + manifest.")
    ] = DEFAULT_MODEL_ARTIFACT_DIR,
    no_odds: Annotated[
        bool,
        typer.Option("--no-odds", help="Train stat-only (skip the market features)."),
    ] = False,
    seed: Annotated[int, typer.Option(help="Deterministic training seed.")] = 20260827,
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
    typer.echo(f"  chosen model: {result.chosen_model_type}")
    typer.echo(
        f"  test Brier: market+stats {result.test_brier_market:.4f} / "
        f"stats-only {result.test_brier_stats_only:.4f}"
    )
    typer.echo(
        f"  baselines: coin-flip {result.test_brier_coin_flip:.4f} / "
        f"higher-points {result.test_brier_higher_points:.4f}"
    )
    typer.echo(f"  beats both baselines: {'yes' if result.beats_both_baselines else 'no'}")


def train_shutout(
    normalized_dir: Annotated[
        Path, typer.Option(help="Directory holding normalized Parquet tables.")
    ] = DEFAULT_NORMALIZED_DIR,
    artifact_dir: Annotated[
        Path, typer.Option(help="Output directory for the report + manifest.")
    ] = DEFAULT_SHUTOUT_ARTIFACT_DIR,
    seed: Annotated[int, typer.Option(help="Deterministic training seed.")] = 20260827,
) -> None:
    """Train the shutout-probability model; write the evaluation report + manifest."""
    from draft_oracle.models.shutout import ShutoutConfig, train_shutout_from_normalized

    result = train_shutout_from_normalized(
        normalized_dir=normalized_dir,
        artifact_dir=artifact_dir,
        config=ShutoutConfig(seed=seed),
    )
    typer.echo(f"Shutout model -> {artifact_dir}")
    typer.echo(f"  chosen model: {result.chosen_model_type}")
    typer.echo(
        f"  test Brier: model {result.test_brier_model:.4f} / "
        f"base-rate {result.test_brier_base_rate:.4f}"
    )
    typer.echo(
        f"  calibration: observed {result.test_observed_rate:.4f} / "
        f"predicted {result.test_predicted_rate:.4f} "
        f"(rel err {result.calibration_rel_error:.1%})"
    )
    typer.echo(f"  within +/-25%: {'yes' if result.calibrated_within_tolerance else 'no'}")


def train_skater_production(
    normalized_dir: Annotated[
        Path, typer.Option(help="Directory holding normalized Parquet tables.")
    ] = DEFAULT_NORMALIZED_DIR,
    artifact_dir: Annotated[
        Path, typer.Option(help="Output directory for the report + manifest.")
    ] = DEFAULT_SKATER_PRODUCTION_ARTIFACT_DIR,
    seed: Annotated[int, typer.Option(help="Deterministic training seed.")] = 20260827,
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
    typer.echo(f"  chosen model: {result.chosen_model_type}")
    typer.echo(
        f"  test MAE: model {result.test_mae_model:.4f} / "
        f"reg-ppg {result.test_mae_baseline_reg:.4f} / "
        f"mean {result.test_mae_baseline_mean:.4f}"
    )
    typer.echo(
        f"  test Spearman: model {result.test_spearman_model:.4f} / "
        f"reg-ppg {result.test_spearman_baseline_reg:.4f}"
    )
    typer.echo(f"  beats reg-ppg baseline: {'yes' if result.beats_reg_baseline else 'no'}")
    typer.echo(f"  cold cases (test): {result.n_cold_cases_test}")


def train_return_time(
    normalized_dir: Annotated[
        Path, typer.Option(help="Directory holding normalized Parquet tables.")
    ] = DEFAULT_NORMALIZED_DIR,
    artifact_dir: Annotated[
        Path, typer.Option(help="Output directory for the report + manifest.")
    ] = DEFAULT_RETURN_TIME_ARTIFACT_DIR,
    seed: Annotated[int, typer.Option(help="Deterministic training seed.")] = 20260827,
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
    typer.echo(f"  held-out seasons: {list(result.test_years)}")
    typer.echo(f"  calibration MAE (survival): {result.calibration_mae:.4f}")


def eval_series_sim(
    normalized_dir: Annotated[
        Path, typer.Option(help="Directory holding normalized Parquet tables.")
    ] = DEFAULT_NORMALIZED_DIR,
    artifact_dir: Annotated[
        Path, typer.Option(help="Output directory for the report + manifest.")
    ] = DEFAULT_SERIES_SIM_ARTIFACT_DIR,
    seed: Annotated[int, typer.Option(help="Deterministic training seed.")] = 20260827,
) -> None:
    """Calibrate the best-of-7 series simulator; write the report + manifest."""
    from draft_oracle.models.series_sim import SeriesSimConfig, evaluate_series_sim_from_normalized

    result = evaluate_series_sim_from_normalized(
        normalized_dir=normalized_dir,
        artifact_dir=artifact_dir,
        config=SeriesSimConfig(seed=seed),
    )
    typer.echo(f"Series simulator -> {artifact_dir}")
    typer.echo(f"  held-out seasons: {list(result.test_years)}")
    typer.echo(f"  series scored: {result.n_series_scored} (skipped {result.n_series_skipped})")
    typer.echo(
        f"  series-winner Brier: model {result.brier_series:.4f} / "
        f"higher-seed {result.brier_higher_seed:.4f} / coin {result.brier_coin_flip:.4f}"
    )


def project_skaters(
    normalized_dir: Annotated[
        Path, typer.Option(help="Directory holding normalized Parquet tables.")
    ] = DEFAULT_NORMALIZED_DIR,
    artifact_dir: Annotated[
        Path, typer.Option(help="Output directory for the report + manifest.")
    ] = DEFAULT_PROJECTION_ARTIFACT_DIR,
    seed: Annotated[int, typer.Option(help="Deterministic training/MC seed.")] = 20260827,
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
    typer.echo(f"  held-out seasons: {list(result.test_years)}")
    typer.echo(
        f"  skater-rounds projected: {result.n_projected} (skipped {result.n_skipped_no_series})"
    )
    typer.echo(
        f"  test MAE: model {result.test_mae_model:.4f} / "
        f"reg-ppg {result.test_mae_baseline_reg:.4f} / "
        f"prev-round {result.test_mae_baseline_prev:.4f}"
    )
    typer.echo(
        f"  test Spearman: model {result.test_spearman_model:.4f} / "
        f"reg-ppg {result.test_spearman_baseline_reg:.4f} / "
        f"prev-round {result.test_spearman_baseline_prev:.4f}"
    )
    typer.echo(f"  beats both baselines: {'yes' if result.beats_both_baselines else 'no'}")


def train_opponents(
    normalized_dir: Annotated[
        Path, typer.Option(help="Directory holding normalized Parquet tables.")
    ] = DEFAULT_NORMALIZED_DIR,
    artifact_dir: Annotated[
        Path, typer.Option(help="Output directory for the report + manifest.")
    ] = DEFAULT_OPPONENT_ARTIFACT_DIR,
    seed: Annotated[int, typer.Option(help="Deterministic training seed.")] = 20260827,
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


def compare_strategies_cmd(
    normalized_dir: Annotated[
        Path, typer.Option(help="Directory holding normalized Parquet tables.")
    ] = DEFAULT_NORMALIZED_DIR,
    managers: Annotated[int, typer.Option(help="League size for the simulated drafts.")] = 4,
    n_drafts: Annotated[int, typer.Option(help="Seeded simulated drafts (>=200).")] = 200,
    rollouts: Annotated[int, typer.Option(help="Rollouts per recommendation.")] = 40,
    max_candidates: Annotated[int, typer.Option(help="Candidates rolled out.")] = 6,
    seed: Annotated[int, typer.Option(help="Deterministic seed.")] = 20260827,
) -> None:
    """Run the committed multi-step vs. greedy-VOR vs. one-step comparison (US-021)."""
    from draft_oracle.optimize.recommend import (
        DEFAULT_RECOMMEND_ARTIFACT_DIR,
        evaluate_recommendation_strategies_from_normalized,
    )

    result = evaluate_recommendation_strategies_from_normalized(
        normalized_dir=normalized_dir,
        managers=managers,
        n_drafts=n_drafts,
        rollouts=rollouts,
        max_candidates=max_candidates,
        seed=seed,
    )
    typer.echo(f"Strategy comparison -> {DEFAULT_RECOMMEND_ARTIFACT_DIR}")
    for line in result.report_lines():
        typer.echo(line)


def backtest(
    seasons: Annotated[
        list[int], typer.Option("--seasons", help="Playoff end years to replay, e.g. 2022.")
    ],
    normalized_dir: Annotated[
        Path, typer.Option(help="Directory holding normalized Parquet tables.")
    ] = DEFAULT_NORMALIZED_DIR,
    backtest_root: Annotated[
        Path, typer.Option(help="Root directory for the written backtest run.")
    ] = DEFAULT_BACKTEST_ROOT,
    snapshot: Annotated[
        str, typer.Option(help="Pin a frozen snapshot id (defaults to the live tables).")
    ] = "",
    managers: Annotated[int, typer.Option(help="League size (2-12).")] = 4,
    ir: Annotated[
        bool, typer.Option("--ir/--no-ir", help="League uses IR slots (+1 F, +1 D).")
    ] = False,
    n_drafts: Annotated[int, typer.Option(help="Seeded drafts per (round, slot).")] = 1,
    rollouts: Annotated[int, typer.Option(help="Monte-Carlo rollouts per oracle pick.")] = 40,
    strategies: Annotated[
        list[str] | None,
        typer.Option(
            "--strategy",
            help="Oracle policies to seat (oracle/greedy_vor/one_step/random_legal).",
        ),
    ] = None,
    seed: Annotated[int, typer.Option(help="Deterministic seed.")] = 20260827,
) -> None:
    """Replay historical playoff rounds end-to-end and score against actuals (US-025).

    Rebuilds as-of projections for every round, seats the oracle in each snake slot
    vs. the fitted (league-history) or greedy opponent model, and scores every roster
    with the real results through the rules engine. A hard leakage guard fails loudly
    if any round-N game leaks into the as-of inputs. Per-round intermediates and the
    run manifest are written under backtest_root/<run-id>/.
    """
    from draft_oracle.backtest.replay import BacktestConfig, run_backtest_from_normalized

    resolved: tuple[Strategy, ...] = tuple(_coerce_strategy(s) for s in (strategies or ["oracle"]))
    config = BacktestConfig(
        seed=seed,
        managers=managers,
        ir=ir,
        n_drafts=n_drafts,
        rollouts=rollouts,
        strategies=resolved,
    )
    result, out_dir = run_backtest_from_normalized(
        seasons=seasons,
        normalized_dir=normalized_dir,
        backtest_root=backtest_root,
        snapshot=snapshot or None,
        config=config,
    )
    typer.echo(f"Backtest run {result.run_id} -> {out_dir}")
    typer.echo(f"  report: {out_dir / 'report.md'}")
    typer.echo(f"  seasons: {', '.join(str(s) for s in result.seasons)}")
    typer.echo(f"  rounds replayed: {len(result.rounds)}")
    typer.echo(f"  strategies: {', '.join(config.strategies)}; drafts/slot: {n_drafts}")
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
