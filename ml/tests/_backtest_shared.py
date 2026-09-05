"""Shared backtest-test helpers and compatibility exports."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

from draft_oracle.backtest.replay import BacktestConfig, Strategy
from draft_oracle.models.skater_production import SkaterProductionConfig
from draft_oracle.projection_artifact import ProjectArtifactConfig
from tests.backtest_fixtures import SERIES_PAIRS, TEAMS, _tables

__all__ = [
    'SERIES_PAIRS',
    'TEAMS',
    '_config',
    '_config_ir',
    '_require_real_backtest_tables',
    '_series_odds_frame',
    '_tables',
]


def _config(
    strategies: tuple[Strategy, ...] = ('oracle',),
    n_drafts: int = 1,
) -> BacktestConfig:
    project = ProjectArtifactConfig(
        seed=20260827,
        n_sims=200,
        slot_strategies=False,
        production_config=SkaterProductionConfig(
            seed=20260827,
            n_val_seasons=1,
            n_test_seasons=1,
            min_confident_games=5,
        ),
    )
    return BacktestConfig(
        seed=20260827,
        managers=4,
        n_drafts=n_drafts,
        rollouts=8,
        max_candidates=5,
        strategies=strategies,
        project_config=project,
    )


def _config_ir() -> BacktestConfig:
    return replace(_config(), ir=True)


def _series_odds_frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    """Minimal odds frame with the columns ``_market_series_prob`` reads."""
    return pd.DataFrame(
        rows,
        columns=[
            'season_end_year',
            'game_date',
            'is_playoff',
            'home_team_id',
            'away_team_id',
            'home_implied',
            'away_implied',
        ],
    )


def _require_real_backtest_tables(normalized: Path) -> None:
    required = (
        'league_draft_picks.parquet',
        'series.parquet',
        'skater_games.parquet',
        'team_games.parquet',
    )
    missing = [name for name in required if not (normalized / name).exists()]
    if missing:
        pytest.skip(f"generated normalized tables not present: {', '.join(missing)}")
