"""Draft optimization public API with lazy re-exports.

Importing a draft-time submodule must not load training or HTTP dependencies. Keep
these convenience re-exports lazy so ``oracle draft`` and ``oracle recommend`` can
run from committed artifacts without LightGBM, scikit-learn, or httpx installed.
"""

# Type-only imports preserve static public-API types; runtime exports stay lazy.
# ruff: noqa: F401

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from draft_oracle.optimize.ir_value import (
        DEFAULT_STASH_HORIZON,
        DEFAULT_STASH_N_SIMS,
        StashInput,
        StashValuation,
        build_stash_valuations,
        healthy_alternative_value,
        render_ir_section,
        reprice_pool_for_ir,
        retroactive_swap_points,
        round_points_with_return,
        simulate_stash_samples,
        value_stash,
    )
    from draft_oracle.optimize.opponents import (
        Coefficients,
        FittedLeagueOpponents,
        FittedOpponentModel,
        MembershipScore,
        OpponentEvalResult,
        OpponentFitConfig,
        OpponentModelResult,
        PerPickScore,
        base_position,
        build_team_affinity,
        evaluate_opponents,
        fit_opponent_models,
        opponent_model_from_config,
        train_opponent_model_from_normalized,
    )
    from draft_oracle.optimize.recommend import (
        DEFAULT_RECOMMEND_ARTIFACT_DIR,
        PickEvaluation,
        Recommendation,
        RecommendConfig,
        StrategyComparison,
        asset_value,
        build_pool_from_frames,
        build_pool_from_projection_artifact,
        build_synthetic_pool,
        choose_pick,
        compare_strategies,
        evaluate_recommendation_strategies_from_normalized,
        greedy_vor_pick,
        recommend_pick,
        replacement_levels,
    )
    from draft_oracle.optimize.simulator import (
        DraftAsset,
        DraftState,
        GreedyOpponentModel,
        ManagerRoster,
        OpponentModel,
        RosterCapacity,
        SurvivalQuery,
        roster_capacity,
        run_draft,
        survival_probability,
        validate_draft,
    )
    from draft_oracle.optimize.slot_strategies import (
        Contingency,
        PickOption,
        SlotPlan,
        SlotStrategyConfig,
        SlotStrategyReport,
        TurnPlan,
        build_slot_strategies,
        slot_pick_numbers,
        write_slot_strategies,
    )
    from draft_oracle.optimize.vor import (
        CHEATSHEET_COLUMNS,
        CheatSheet,
        RosterDemand,
        VorConfig,
        build_cheatsheet,
        render_cheatsheet_markdown,
        replacement_level,
        roster_demand,
        write_cheatsheet,
    )

_MODULE_EXPORTS: dict[str, tuple[str, ...]] = {
    "draft_oracle.optimize.ir_value": (
        "DEFAULT_STASH_HORIZON",
        "DEFAULT_STASH_N_SIMS",
        "StashInput",
        "StashValuation",
        "build_stash_valuations",
        "healthy_alternative_value",
        "render_ir_section",
        "retroactive_swap_points",
        "round_points_with_return",
        "simulate_stash_samples",
        "value_stash",
    ),
    "draft_oracle.optimize.ir_pool": ("reprice_pool_for_ir",),
    "draft_oracle.optimize.opponents": (
        "Coefficients",
        "FittedLeagueOpponents",
        "FittedOpponentModel",
        "MembershipScore",
        "OpponentEvalResult",
        "OpponentFitConfig",
        "OpponentModelResult",
        "PerPickScore",
        "base_position",
        "build_team_affinity",
        "evaluate_opponents",
        "fit_opponent_models",
        "opponent_model_from_config",
        "train_opponent_model_from_normalized",
    ),
    "draft_oracle.optimize.recommend": (
        "DEFAULT_RECOMMEND_ARTIFACT_DIR",
        "PickEvaluation",
        "Recommendation",
        "RecommendConfig",
        "StrategyComparison",
        "asset_value",
        "build_pool_from_frames",
        "build_pool_from_projection_artifact",
        "build_synthetic_pool",
        "choose_pick",
        "compare_strategies",
        "evaluate_recommendation_strategies_from_normalized",
        "greedy_vor_pick",
        "recommend_pick",
        "replacement_levels",
    ),
    "draft_oracle.optimize.simulator": (
        "DraftAsset",
        "DraftState",
        "GreedyOpponentModel",
        "ManagerRoster",
        "OpponentModel",
        "RosterCapacity",
        "SurvivalQuery",
        "roster_capacity",
        "run_draft",
        "survival_probability",
        "validate_draft",
    ),
    "draft_oracle.optimize.slot_strategies": (
        "Contingency",
        "PickOption",
        "SlotPlan",
        "SlotStrategyConfig",
        "SlotStrategyReport",
        "TurnPlan",
        "build_slot_strategies",
        "slot_pick_numbers",
        "write_slot_strategies",
    ),
    "draft_oracle.optimize.vor": (
        "CHEATSHEET_COLUMNS",
        "CheatSheet",
        "RosterDemand",
        "VorConfig",
        "build_cheatsheet",
        "render_cheatsheet_markdown",
        "replacement_level",
        "roster_demand",
        "write_cheatsheet",
    ),
}

_EXPORT_MODULE = {
    name: module_name
    for module_name, names in _MODULE_EXPORTS.items()
    for name in names
}

__all__ = list(_EXPORT_MODULE)


def __getattr__(name: str) -> object:
    """Load one public optimization symbol only when first requested."""
    module_name = _EXPORT_MODULE.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = cast(object, getattr(import_module(module_name), name))
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    """Include lazy public symbols in interactive discovery."""
    return sorted({*globals(), *__all__})
