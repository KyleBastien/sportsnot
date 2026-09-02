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
from draft_oracle.cli._project_artifact_commands import draft_cmd, project, recommend
from draft_oracle.cli._project_defaults import (
    DEFAULT_ARCHIVE_DIR,
    DEFAULT_ARTIFACTS_ROOT,
    DEFAULT_BACKTEST_ROOT,
    DEFAULT_INJURIES_OVERRIDES,
    DEFAULT_LEAGUE_DRAFTS_DIR,
    DEFAULT_MODEL_ARTIFACT_DIR,
    DEFAULT_NORMALIZED_DIR,
    DEFAULT_ODDS_ARCHIVE_DIR,
    DEFAULT_OPPONENT_ARTIFACT_DIR,
    DEFAULT_OVERRIDES_DIR,
    DEFAULT_PROJECTION_ARTIFACT_DIR,
    DEFAULT_RETURN_TIME_ARTIFACT_DIR,
    DEFAULT_SERIES_SIM_ARTIFACT_DIR,
    DEFAULT_SHUTOUT_ARTIFACT_DIR,
    DEFAULT_SKATER_PRODUCTION_ARTIFACT_DIR,
    STRATEGIES,
    Strategy,
)
from draft_oracle.cli._project_training_commands import (
    backtest,
    compare_strategies_cmd,
    eval_series_sim,
    project_skaters,
    train_game_win,
    train_opponents,
    train_return_time,
    train_shutout,
    train_skater_production,
)

_PROJECT_PUBLIC_DEFAULTS = (
    DEFAULT_ARCHIVE_DIR,
    DEFAULT_ARTIFACTS_ROOT,
    DEFAULT_BACKTEST_ROOT,
    DEFAULT_INJURIES_OVERRIDES,
    DEFAULT_LEAGUE_DRAFTS_DIR,
    DEFAULT_MODEL_ARTIFACT_DIR,
    DEFAULT_NORMALIZED_DIR,
    DEFAULT_ODDS_ARCHIVE_DIR,
    DEFAULT_OPPONENT_ARTIFACT_DIR,
    DEFAULT_OVERRIDES_DIR,
    DEFAULT_PROJECTION_ARTIFACT_DIR,
    DEFAULT_RETURN_TIME_ARTIFACT_DIR,
    DEFAULT_SERIES_SIM_ARTIFACT_DIR,
    DEFAULT_SHUTOUT_ARTIFACT_DIR,
    DEFAULT_SKATER_PRODUCTION_ARTIFACT_DIR,
    STRATEGIES,
    Strategy,
)

_PROJECT_COMMAND_EXPORTS = (
    backtest,
    compare_strategies_cmd,
    draft_cmd,
    eval_series_sim,
    project,
    project_skaters,
    recommend,
    train_game_win,
    train_opponents,
    train_return_time,
    train_shutout,
    train_skater_production,
)
for _exported in _PROJECT_COMMAND_EXPORTS:
    _exported.__module__ = __name__

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
    from draft_oracle.ingest.normalize import normalize_archive

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
    from draft_oracle.ingest.normalize import create_snapshot, list_snapshots

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
    from draft_oracle.ingest.odds import build_odds_table

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
        f"{result.unattributed_uncovered_rows} unattributed-price rows flagged, "
        f"{result.xval_flagged_rows} cross-source-disagreement rows flagged, "
        f"{result.unmatched_uncovered_rows} archive-unjoinable rows excluded "
        f"({result.orientation_unmatched_rows} reversed-orientation)"
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
    from draft_oracle.ingest.league_drafts import build_league_drafts

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
    from draft_oracle.ingest.entity_match import build_league_draft_picks

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
    from draft_oracle.ingest.injuries import build_injuries_table

    result = build_injuries_table(
        overrides_path=overrides_path,
        out_dir=out_dir,
        fetch=not no_fetch,
    )
    for line in result.report_lines():
        typer.echo(line)






app.command(name="train-game-win")(train_game_win)
app.command(name="train-shutout")(train_shutout)
app.command(name="train-skater-production")(train_skater_production)
app.command(name="train-return-time")(train_return_time)
app.command(name="eval-series-sim")(eval_series_sim)
app.command(name="project-skaters")(project_skaters)
app.command(name="train-opponents")(train_opponents)
app.command(name="project")(project)
app.command(name="recommend")(recommend)
app.command(name="compare-strategies")(compare_strategies_cmd)
app.command(name="draft")(draft_cmd)
app.command(name="backtest")(backtest)

if __name__ == "__main__":  # pragma: no cover
    app()
