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

__all__ = [
    "FEATURE_COLUMNS",
    "FEATURE_SET_VERSION",
    "LeakageError",
    "SkaterFeatureConfig",
    "age_years",
    "as_of",
    "assert_no_leakage",
    "build_round_feature_matrix",
    "build_skater_features",
    "linemate_ppg",
    "per_game",
    "pp_point_share",
    "safe_ratio",
    "shooting_pct",
    "to_cutoff",
    "write_feature_matrix",
]
