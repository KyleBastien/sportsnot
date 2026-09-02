"""Actual-result scoring helpers for historical backtest replay."""

from __future__ import annotations

from collections.abc import Hashable, Mapping, Sequence
from typing import Any

import pandas as pd

from draft_oracle.models.skater_production import (
    PLAYOFF_GAME_TYPE,
    _assign_rounds,
    _series_round_map,
    skater_round_production,
)
from draft_oracle.optimize.simulator import DraftState
from draft_oracle.rules import goalie_series_points, player_points

ActualLookup = dict[tuple[int, int, int], int]
AssetKey = tuple[str, int]


def skater_actual_points(
    skater_games: pd.DataFrame, series: pd.DataFrame
) -> ActualLookup:
    """``(season_id, playoff_round, player_id) -> actual round points``."""
    production = skater_round_production(skater_games, series)
    out: ActualLookup = {}
    for rec in production.to_dict("records"):
        key = (int(rec["season_id"]), int(rec["playoff_round"]), int(rec["player_id"]))
        out[key] = player_points(int(rec["round_goals"]), int(rec["round_assists"]))
    return out


def team_actual_goalie_points(
    team_games: pd.DataFrame, series: pd.DataFrame
) -> ActualLookup:
    """``(season_id, playoff_round, team_id) -> actual goalie-slot points``."""
    po = team_games.loc[team_games["game_type_id"] == PLAYOFF_GAME_TYPE].copy()
    if po.empty:
        return {}
    po["playoff_round"] = _assign_rounds(po, _series_round_map(series))
    po = po.dropna(subset=["playoff_round"])
    grouped = po.groupby(["season_id", "playoff_round", "team_id"], as_index=False).agg(
        wins=("win", "sum"),
        shutout_wins=("shutout_win", "sum"),
    )
    out: ActualLookup = {}
    for rec in grouped.to_dict("records"):
        key = (int(rec["season_id"]), int(rec["playoff_round"]), int(rec["team_id"]))
        out[key] = goalie_series_points(int(rec["wins"]), int(rec["shutout_wins"]))
    return out


def _score_active_roster(
    state: DraftState,
    manager: str,
    skater_actual: ActualLookup,
    team_actual: ActualLookup,
    *,
    season_id: int,
    scored_rounds: Sequence[int],
) -> float:
    """Actual points of ``manager``'s active roster (F/D/G; IR slots excluded)."""
    total = 0.0
    for slot in state.roster_slots(manager):
        if slot.position in ("IR_F", "IR_D"):
            continue
        if slot.player_id is not None:
            total += _actual_points(skater_actual, season_id, scored_rounds, slot.player_id)
        elif slot.team_id is not None:
            total += _actual_points(team_actual, season_id, scored_rounds, slot.team_id)
    return total


def _score_league_roster(
    picks: pd.DataFrame,
    skater_actual: ActualLookup,
    team_actual: ActualLookup,
    *,
    season_id: int,
    scored_rounds: Sequence[int],
) -> float:
    """Actual active-roster points of one league manager's real picks."""
    total = 0.0
    seen: set[AssetKey] = set()
    for rec in picks.to_dict("records"):
        asset = _scored_asset(rec)
        if asset is None or asset in seen:
            continue
        seen.add(asset)
        total += _asset_points(asset, skater_actual, team_actual, season_id, scored_rounds)
    return total


def _scored_asset(rec: Mapping[Hashable, Any]) -> AssetKey | None:
    if _inactive_pick(rec):
        return None
    position = str(rec.get("position", ""))
    team_id = rec.get("team_id")
    player_id = rec.get("player_id")
    if position == "G" and not pd.isna(team_id):
        return ("team", int(team_id))
    if not pd.isna(player_id):
        return ("player", int(player_id))
    return None


def _inactive_pick(rec: Mapping[Hashable, Any]) -> bool:
    position = str(rec.get("position", ""))
    points_excluded = bool(rec.get("points_excluded"))
    ir_activated = bool(rec.get("ir_activated"))
    return points_excluded or (position in ("IR_F", "IR_D") and not ir_activated)


def _asset_points(
    asset: AssetKey,
    skater_actual: ActualLookup,
    team_actual: ActualLookup,
    season_id: int,
    scored_rounds: Sequence[int],
) -> float:
    kind, asset_id = asset
    if kind == "team":
        return _actual_points(team_actual, season_id, scored_rounds, asset_id)
    return _actual_points(skater_actual, season_id, scored_rounds, asset_id)


def _actual_points(
    lookup: ActualLookup, season_id: int, scored_rounds: Sequence[int], asset_id: int
) -> float:
    return float(sum(lookup.get((season_id, rnd, asset_id), 0) for rnd in scored_rounds))
