"""Per-slot strategy report builder for projection artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import pandas as pd

from draft_oracle.optimize.opponents import (
    FittedLeagueOpponents,
    OpponentFitConfig,
    fit_opponent_models,
)
from draft_oracle.optimize.recommend import build_pool_from_frames
from draft_oracle.optimize.simulator import DraftAsset, roster_capacity
from draft_oracle.optimize.slot_strategies import (
    SlotStrategyConfig,
    SlotStrategyReport,
    build_slot_strategies,
)


class _SlotReportConfig(Protocol):
    @property
    def slot_strategies(self) -> bool: ...

    @property
    def ir(self) -> bool: ...

    @property
    def managers(self) -> int: ...

    @property
    def resolved_slot_config(self) -> SlotStrategyConfig: ...


@dataclass(frozen=True)
class SlotReportInput:
    skaters: pd.DataFrame
    teams: pd.DataFrame
    league_picks: pd.DataFrame | None
    warnings: list[str]
    config: _SlotReportConfig


def _build_slot_report(request: SlotReportInput) -> SlotStrategyReport | None:
    """Build the per-slot strategy report (US-023), or ``None`` when disabled/empty."""
    skaters = request.skaters
    teams = request.teams
    warnings = request.warnings
    config = request.config
    if not config.slot_strategies:
        return None
    if skaters.empty and teams.empty:
        warnings.append("slot strategies skipped: no eligible assets in the pool")
        return None
    pool = build_pool_from_frames(skaters, teams, ir=config.ir)
    shortfall = _slot_pool_shortfall(pool, config.managers, config.ir)
    if shortfall:
        warnings.append(f"slot strategies skipped: pool too small to fill every roster {shortfall}")
        return None
    return build_slot_strategies(
        pool,
        managers=config.managers,
        allow_ir=config.ir,
        opponents=_fit_slot_opponents(request.league_picks, warnings),
        config=config.resolved_slot_config,
    )


def _slot_pool_shortfall(pool: list[DraftAsset], managers: int, allow_ir: bool) -> str:
    capacity = roster_capacity(allow_ir)
    per_position = {
        "F": sum(1 for asset in pool if asset.position == "F"),
        "D": sum(1 for asset in pool if asset.position == "D"),
        "G": sum(1 for asset in pool if asset.position == "G"),
    }
    need = {
        "F": capacity.forwards * managers,
        "D": capacity.defense * managers,
        "G": capacity.goalies * managers,
    }
    if not any(per_position[pos] < need[pos] for pos in ("F", "D", "G")):
        return ""
    return (
        f"(have F{per_position['F']}/D{per_position['D']}/G{per_position['G']}, "
        f"need F{need['F']}/D{need['D']}/G{need['G']})"
    )


def _fit_slot_opponents(
    league_picks: pd.DataFrame | None, warnings: list[str]
) -> FittedLeagueOpponents | None:
    if league_picks is None or league_picks.empty:
        return None
    try:
        return fit_opponent_models(league_picks, OpponentFitConfig())
    except (ValueError, KeyError) as exc:  # pragma: no cover - defensive
        warnings.append(f"slot strategies: fitted opponents unavailable ({exc}); using greedy")
        return None
