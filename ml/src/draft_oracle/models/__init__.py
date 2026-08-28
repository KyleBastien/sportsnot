"""Predictive models: win, shutout, series sim, skater rate, returns, projections (US-011..016).

Public API re-exported for convenience; see :mod:`draft_oracle.models.game_win`.
"""

from draft_oracle.models.game_win import (
    GAME_WIN_MODEL_VERSION,
    MARKET_FEATURE_COLUMNS,
    STAT_FEATURE_COLUMNS,
    GameWinConfig,
    GameWinModel,
    GameWinResult,
    TeamState,
    TemporalSplit,
    baseline_higher_points_probs,
    brier_score,
    build_game_dataset,
    coin_flip_probs,
    default_temporal_split,
    matchup_feature_row,
    train_game_win_from_normalized,
    train_game_win_model,
)

__all__ = [
    "GAME_WIN_MODEL_VERSION",
    "MARKET_FEATURE_COLUMNS",
    "STAT_FEATURE_COLUMNS",
    "GameWinConfig",
    "GameWinModel",
    "GameWinResult",
    "TeamState",
    "TemporalSplit",
    "baseline_higher_points_probs",
    "brier_score",
    "build_game_dataset",
    "coin_flip_probs",
    "default_temporal_split",
    "matchup_feature_row",
    "train_game_win_from_normalized",
    "train_game_win_model",
]
