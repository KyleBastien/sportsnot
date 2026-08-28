"""Feature engineering with leakage guards (US-009/010).

Public API re-exported for convenience; see :mod:`draft_oracle.features.skater`
and :mod:`draft_oracle.features.leakage`.
"""

from draft_oracle.features.leakage import (
    LeakageError,
    as_of,
    assert_no_leakage,
    to_cutoff,
)
from draft_oracle.features.skater import (
    FEATURE_COLUMNS,
    FEATURE_SET_VERSION,
    SkaterFeatureConfig,
    age_years,
    build_round_feature_matrix,
    build_skater_features,
    linemate_ppg,
    per_game,
    pp_point_share,
    safe_ratio,
    shooting_pct,
    write_feature_matrix,
)
from draft_oracle.features.team_series import (
    TEAM_FEATURE_COLUMNS,
    TEAM_FEATURE_SET_VERSION,
    EloConfig,
    TeamSeriesFeatureConfig,
    build_round_team_series_matrix,
    build_team_series_features,
    compute_elo_ratings,
    days_between,
    expected_score,
    goal_differential_per_game,
    regress_to_mean,
    save_pct,
    update_rating,
)

__all__ = [
    "FEATURE_COLUMNS",
    "FEATURE_SET_VERSION",
    "TEAM_FEATURE_COLUMNS",
    "TEAM_FEATURE_SET_VERSION",
    "EloConfig",
    "LeakageError",
    "SkaterFeatureConfig",
    "TeamSeriesFeatureConfig",
    "age_years",
    "as_of",
    "assert_no_leakage",
    "build_round_feature_matrix",
    "build_round_team_series_matrix",
    "build_skater_features",
    "build_team_series_features",
    "compute_elo_ratings",
    "days_between",
    "expected_score",
    "goal_differential_per_game",
    "linemate_ppg",
    "per_game",
    "pp_point_share",
    "regress_to_mean",
    "safe_ratio",
    "save_pct",
    "shooting_pct",
    "to_cutoff",
    "update_rating",
    "write_feature_matrix",
]
