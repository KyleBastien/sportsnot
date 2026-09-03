"""Feature engineering with leakage guards.

Public API re-exported for convenience; see :mod:`draft_oracle.features.skater`,
:mod:`draft_oracle.features.elo`, and :mod:`draft_oracle.features.leakage`.
"""

from draft_oracle.features.elo import (
    EloConfig,
    expected_score,
    regress_to_mean,
    update_rating,
)
from draft_oracle.features.leakage import (
    LeakageError,
    as_of,
    assert_no_leakage,
    to_cutoff,
)
from draft_oracle.features.skater import (
    FEATURE_COLUMNS,
    FEATURE_SET_VERSION,
    RoundFeatureMatrixRequest,
    SkaterFeatureConfig,
    SkaterFeatureRequest,
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

__all__ = [
    "FEATURE_COLUMNS",
    "FEATURE_SET_VERSION",
    "EloConfig",
    "LeakageError",
    "RoundFeatureMatrixRequest",
    "SkaterFeatureConfig",
    "SkaterFeatureRequest",
    "age_years",
    "as_of",
    "assert_no_leakage",
    "build_round_feature_matrix",
    "build_skater_features",
    "expected_score",
    "linemate_ppg",
    "per_game",
    "pp_point_share",
    "regress_to_mean",
    "safe_ratio",
    "shooting_pct",
    "to_cutoff",
    "update_rating",
    "write_feature_matrix",
]
