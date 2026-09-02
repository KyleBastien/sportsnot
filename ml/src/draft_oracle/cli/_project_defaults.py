"""Shared defaults for the ``oracle`` Typer command group."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

DEFAULT_ARCHIVE_DIR = Path("data/raw/nhl-archive")
DEFAULT_NORMALIZED_DIR = Path("data/normalized")
DEFAULT_ODDS_ARCHIVE_DIR = Path("data/raw/odds-archive")
DEFAULT_LEAGUE_DRAFTS_DIR = Path("data/raw/league-drafts")
DEFAULT_OVERRIDES_DIR = Path("data/overrides")
DEFAULT_INJURIES_OVERRIDES = DEFAULT_OVERRIDES_DIR / "injuries.yaml"
DEFAULT_MODEL_ARTIFACT_DIR = Path("artifacts/models/game-win")
DEFAULT_SHUTOUT_ARTIFACT_DIR = Path("artifacts/models/shutout")
DEFAULT_SKATER_PRODUCTION_ARTIFACT_DIR = Path("artifacts/models/skater-production")
DEFAULT_RETURN_TIME_ARTIFACT_DIR = Path("artifacts/models/return-time")
DEFAULT_SERIES_SIM_ARTIFACT_DIR = Path("artifacts/models/series-sim")
DEFAULT_PROJECTION_ARTIFACT_DIR = Path("artifacts/models/skater-projection")
DEFAULT_OPPONENT_ARTIFACT_DIR = Path("artifacts/models/opponent")
DEFAULT_ARTIFACTS_ROOT = Path("artifacts")
DEFAULT_BACKTEST_ROOT = Path("artifacts/backtests")

Strategy = Literal["oracle", "greedy_vor", "one_step", "random_legal"]
STRATEGIES: tuple[Strategy, ...] = ("oracle", "greedy_vor", "one_step", "random_legal")
