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
    no_odds: Annotated[
        bool,
        typer.Option("--no-odds", help="Skip odds ingestion entirely (stat-only path)."),
    ] = False,
) -> None:
    """Build the de-vigged odds tables from committed archives (offline)."""
    if no_odds:
        typer.echo("Odds ingestion skipped (--no-odds); stat-only path is unaffected.")
        return
    result = build_odds_table(archive_dir=archive_dir, out_dir=out_dir)
    typer.echo(f"Odds tables -> {out_dir}")
    typer.echo(f"  source rows: {result.source_rows}")
    typer.echo(f"  games: {result.game_rows} priced/flagged")
    typer.echo(f"  priced: {result.covered_rows}  flagged: {result.uncovered_rows}")


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


if __name__ == "__main__":  # pragma: no cover
    app()
