"""``oracle`` CLI entry point.

Exposes the top-level command group. Data-pipeline commands are added per
story: ``version`` (US-001), ``normalize`` / ``snapshot`` (US-004). Batch
projection and draft-assistant commands follow in US-017/024.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from draft_oracle import __version__
from draft_oracle.backtest.replay import (
    DEFAULT_BACKTEST_ROOT,
    STRATEGIES,
    BacktestConfig,
    Strategy,
    run_backtest_from_normalized,
)
from draft_oracle.cli.draft import draft as draft_command
from draft_oracle.ingest.entity_match import (
    DEFAULT_OVERRIDES_DIR,
    build_league_draft_picks,
)
from draft_oracle.ingest.injuries import (
    DEFAULT_INJURIES_OVERRIDES,
    build_injuries_table,
)
from draft_oracle.ingest.league_drafts import (
    DEFAULT_LEAGUE_DRAFTS_DIR,
    build_league_drafts,
)
from draft_oracle.ingest.normalize import (
    DEFAULT_ARCHIVE_DIR,
    DEFAULT_NORMALIZED_DIR,
    create_snapshot,
    list_snapshots,
    normalize_archive,
)
from draft_oracle.ingest.odds import (
    DEFAULT_ODDS_ARCHIVE_DIR,
    build_odds_table,
)
from draft_oracle.models.game_win import (
    DEFAULT_MODEL_ARTIFACT_DIR,
    GameWinConfig,
    train_game_win_from_normalized,
)
from draft_oracle.models.projections import (
    DEFAULT_MODEL_ARTIFACT_DIR as DEFAULT_PROJECTION_ARTIFACT_DIR,
)
from draft_oracle.models.projections import (
    ProjectionConfig,
    evaluate_skater_projections_from_normalized,
)
from draft_oracle.models.returns import (
    DEFAULT_MODEL_ARTIFACT_DIR as DEFAULT_RETURN_TIME_ARTIFACT_DIR,
)
from draft_oracle.models.returns import (
    ReturnTimeConfig,
    train_return_time_from_normalized,
)
from draft_oracle.models.series_sim import (
    DEFAULT_MODEL_ARTIFACT_DIR as DEFAULT_SERIES_SIM_ARTIFACT_DIR,
)
from draft_oracle.models.series_sim import (
    SeriesSimConfig,
    evaluate_series_sim_from_normalized,
)
from draft_oracle.models.shutout import (
    DEFAULT_MODEL_ARTIFACT_DIR as DEFAULT_SHUTOUT_ARTIFACT_DIR,
)
from draft_oracle.models.shutout import (
    ShutoutConfig,
    train_shutout_from_normalized,
)
from draft_oracle.models.skater_production import (
    DEFAULT_MODEL_ARTIFACT_DIR as DEFAULT_SKATER_PRODUCTION_ARTIFACT_DIR,
)
from draft_oracle.models.skater_production import (
    SkaterProductionConfig,
    train_skater_production_from_normalized,
)
from draft_oracle.optimize.opponents import (
    DEFAULT_OPPONENT_ARTIFACT_DIR,
    OpponentFitConfig,
    train_opponent_model_from_normalized,
)
from draft_oracle.optimize.slot_strategies import SlotStrategyConfig
from draft_oracle.projection_artifact import (
    DEFAULT_ARTIFACTS_ROOT,
    ProjectArtifactConfig,
    build_projection_artifact_from_normalized,
)

app = typer.Typer(
    add_completion=False,
    help="Draft Oracle - NHL playoff fantasy draft optimizer.",
    no_args_is_help=True,
)


@app.callback()
def main() -> None:
    """Draft Oracle command group. Subcommands are added per story (US-017/024)."""


@app.command()
def version() -> None:
    """Print the installed draft_oracle version."""
    typer.echo(__version__)


@app.command()
def normalize(
    archive_dir: Annotated[
        Path, typer.Option(help="Committed NHL archive directory.")
    ] = DEFAULT_ARCHIVE_DIR,
    out_dir: Annotated[
        Path, typer.Option(help="Output directory for normalized Parquet tables.")
    ] = DEFAULT_NORMALIZED_DIR,
    force: Annotated[
        bool, typer.Option("--force", help="Rebuild even if sources are unchanged.")
    ] = False,
) -> None:
    """Normalize the committed NHL archive into Parquet tables (idempotent)."""
    result = normalize_archive(archive_dir=archive_dir, out_dir=out_dir, force=force)
    if result.skipped:
        typer.echo(f"Up to date - {out_dir} matches sources; nothing to do.")
        return
    typer.echo(f"Normalized {len(result.seasons)} season(s) -> {out_dir}")
    for name, count in result.row_counts.items():
        typer.echo(f"  {name}: {count} rows")


@app.command()
def snapshot(
    out_dir: Annotated[
        Path, typer.Option(help="Directory holding normalized tables.")
    ] = DEFAULT_NORMALIZED_DIR,
    snapshot_id: Annotated[
        str, typer.Option(help="Snapshot id (defaults to a UTC timestamp).")
    ] = "",
    show_list: Annotated[
        bool,
        typer.Option("--list", help="List existing snapshot ids instead of creating one."),
    ] = False,
) -> None:
    """Freeze a dated copy of the normalized tables; downstream pins the id."""
    if show_list:
        ids = list_snapshots(out_dir)
        if not ids:
            typer.echo("No snapshots found.")
            return
        for sid in ids:
            typer.echo(sid)
        return
    result = create_snapshot(out_dir=out_dir, snapshot_id=snapshot_id or None)
    typer.echo(f"Snapshot {result.snapshot_id} -> {result.path}")


@app.command()
def odds(
    archive_dir: Annotated[
        Path, typer.Option(help="Committed odds-archive directory.")
    ] = DEFAULT_ODDS_ARCHIVE_DIR,
    out_dir: Annotated[
        Path, typer.Option(help="Output directory for the odds Parquet tables.")
    ] = DEFAULT_NORMALIZED_DIR,
    nhl_archive_dir: Annotated[
        Path,
        typer.Option(help="Committed NHL archive (supplies local game dates for the market join)."),
    ] = DEFAULT_ARCHIVE_DIR,
    no_odds: Annotated[
        bool,
        typer.Option("--no-odds", help="Skip odds ingestion entirely (stat-only path)."),
    ] = False,
) -> None:
    """Build the de-vigged odds tables from committed archives (offline)."""
    if no_odds:
        typer.echo("Odds ingestion skipped (--no-odds); stat-only path is unaffected.")
        return
    result = build_odds_table(
        archive_dir=archive_dir, out_dir=out_dir, nhl_archive_dir=nhl_archive_dir
    )
    typer.echo(f"Odds tables -> {out_dir}")
    typer.echo(f"  source rows: {result.source_rows}")
    typer.echo(f"  games: {result.game_rows} priced/flagged")
    typer.echo(f"  priced: {result.covered_rows}  flagged: {result.uncovered_rows}")
    typer.echo(
        f"  guards: {result.placeholder_uncovered_rows} placeholder rows rejected, "
        f"{result.xval_flagged_rows} cross-source-disagreement rows flagged"
    )


@app.command(name="league-drafts")
def league_drafts(
    league_dir: Annotated[
        Path, typer.Option(help="Committed league-drafts snapshot directory.")
    ] = DEFAULT_LEAGUE_DRAFTS_DIR,
    out_dir: Annotated[
        Path, typer.Option(help="Output directory for the league Parquet tables.")
    ] = DEFAULT_NORMALIZED_DIR,
) -> None:
    """Parse the committed league draft-history snapshots into Parquet tables."""
    result = build_league_drafts(league_dir=league_dir, out_dir=out_dir)
    for line in result.report_lines():
        typer.echo(line)


@app.command(name="match-drafts")
def match_drafts(
    normalized_dir: Annotated[
        Path, typer.Option(help="Directory holding normalized Parquet tables.")
    ] = DEFAULT_NORMALIZED_DIR,
    overrides_dir: Annotated[
        Path, typer.Option(help="Directory holding the override YAML files.")
    ] = DEFAULT_OVERRIDES_DIR,
    out_dir: Annotated[
        Path, typer.Option(help="Output directory for league_draft_picks.parquet.")
    ] = DEFAULT_NORMALIZED_DIR,
) -> None:
    """Match league picks to NHL ids -> league_draft_picks + match-rate report."""
    result = build_league_draft_picks(
        normalized_dir=normalized_dir,
        overrides_dir=overrides_dir,
        out_dir=out_dir,
    )
    for line in result.report_lines():
        typer.echo(line)


@app.command()
def injuries(
    overrides_path: Annotated[
        Path, typer.Option(help="Manual injury override YAML (final authority).")
    ] = DEFAULT_INJURIES_OVERRIDES,
    out_dir: Annotated[
        Path, typer.Option(help="Output directory for injuries.parquet.")
    ] = DEFAULT_NORMALIZED_DIR,
    no_fetch: Annotated[
        bool,
        typer.Option(
            "--no-fetch",
            help="Skip the ESPN feed; use last-known data + overrides (offline).",
        ),
    ] = False,
) -> None:
    """Ingest ESPN injuries into injuries.parquet; overrides win as final authority."""
    result = build_injuries_table(
        overrides_path=overrides_path,
        out_dir=out_dir,
        fetch=not no_fetch,
    )
    for line in result.report_lines():
        typer.echo(line)


@app.command(name="train-game-win")
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


@app.command(name="train-shutout")
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


@app.command(name="train-skater-production")
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


@app.command(name="train-return-time")
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


@app.command(name="eval-series-sim")
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


@app.command(name="project-skaters")
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


@app.command(name="train-opponents")
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


@app.command(name="project")
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
    if not no_refresh and not snapshot:
        normalize_archive(archive_dir=archive_dir, out_dir=normalized_dir)
    result, out_dir = build_projection_artifact_from_normalized(
        season=season,
        playoff_round=playoff_round,
        normalized_dir=normalized_dir,
        artifacts_root=artifacts_root,
        snapshot=snapshot or None,
        config=ProjectArtifactConfig(
            seed=seed,
            managers=managers,
            ir=ir,
            slot_strategies=slot_strategies,
            slot_strategy_config=SlotStrategyConfig(seed=seed, rollouts=slot_rollouts),
        ),
    )
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
            f" ({'fitted' if slots['fitted_opponents'] else 'greedy'} opponents);"
            f" best slot {slots['best_slot']}"
        )
    for warning in result.warnings:
        typer.echo(f"  warning: {warning}")


@app.command()
def recommend(
    artifact_dir: Annotated[
        Path, typer.Option(help="Projection artifact directory (has skaters/teams parquet).")
    ],
    managers: Annotated[int, typer.Option(help="League size (2-12).")] = 4,
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
) -> None:
    """Recommend the best pick right now via multi-step Monte-Carlo rollout (US-021).

    Builds a fresh draft from a projection artifact, puts the owner on the clock at
    ``seat``, and prints the top-5 explained recommendations (VOR, survival, need,
    delta vs. #2). Opponents are the greedy fallback (vectorized fast path).
    """
    from draft_oracle.optimize.recommend import (
        RecommendConfig,
        build_pool_from_projection_artifact,
        recommend_pick,
    )
    from draft_oracle.optimize.simulator import DraftState, GreedyOpponentModel

    if not 1 <= seat <= managers:
        raise typer.BadParameter(f"seat must be in 1..{managers}")
    pool = build_pool_from_projection_artifact(artifact_dir, ir=ir)
    manager_ids = [f"seat{i + 1}" for i in range(managers)]
    owner = manager_ids[seat - 1]
    state = DraftState.new(manager_ids, pool, allow_ir=ir)
    # Advance to the owner's first turn (opponents ahead of the owner draft greedily).
    model = GreedyOpponentModel(temperature=temperature, need_weight=4.0)
    import random as _random

    rng = _random.Random(seed)
    while state.current_manager != owner:
        current = state.current_manager
        state.apply_pick(model.pick(state, current, rng))
    config = RecommendConfig(rollouts=rollouts, depth=depth or None, seed=seed)
    result = recommend_pick(state, owner, model, config=config, managers=managers)
    typer.echo(f"Recommendation for {owner} (pick #{state.pick_index + 1}):")
    for line in result.report_lines():
        typer.echo(line)


@app.command(name="compare-strategies")
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


app.command(name="draft")(draft_command)


@app.command()
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


if __name__ == "__main__":  # pragma: no cover
    app()
