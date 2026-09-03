"""Backtest opponent-model selection helpers."""

from __future__ import annotations

import pandas as pd

from draft_oracle.backtest._replay_types import BacktestConfig
from draft_oracle.optimize.opponents import (
    FittedLeagueOpponents,
    OpponentFitConfig,
    fit_opponent_models,
)
from draft_oracle.optimize.simulator import GreedyOpponentModel, OpponentModel


def _top_managers(fitted: FittedLeagueOpponents, limit: int) -> list[str]:
    """The ``limit`` most active historical managers (deterministic tie-break)."""
    ranked = sorted(fitted.manager_pick_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [manager for manager, _ in ranked[:limit]]


def _fit_opponents_for_season(
    league_picks: pd.DataFrame | None, season: int, config: BacktestConfig
) -> FittedLeagueOpponents | None:
    """Fit opponents leave-one-season-out; ``None`` when history omits the season.

    The fitted model trains on every league season *except* the one being
    backtested, so a season never informs its own opponents (SPEC section 6). If the
    league history does not cover ``season`` (or nothing is left after excluding it),
    the caller falls back to the greedy opponent.
    """
    if league_picks is None or "season" not in league_picks.columns:
        return None
    seasons = {int(s) for s in league_picks["season"].unique()}
    if season not in seasons:
        return None
    train = league_picks.loc[league_picks["season"].astype(int) != season]
    if train.empty:
        return None
    return fit_opponent_models(train, OpponentFitConfig(temperature=config.opponent_temperature))


def _managers_and_opponents(
    fitted: FittedLeagueOpponents | None, config: BacktestConfig
) -> tuple[list[str], OpponentModel | dict[str, OpponentModel], str]:
    """Resolve the manager ids, opponent policy, and a label for the round."""
    if fitted is not None:
        managers_list = _top_managers(fitted, config.managers)
        while len(managers_list) < config.managers:
            managers_list.append(f"seat{len(managers_list) + 1}")
        return managers_list, fitted.as_mapping(managers_list), "fitted-league"
    managers_list = [f"seat{i + 1}" for i in range(config.managers)]
    greedy = GreedyOpponentModel(temperature=config.opponent_temperature)
    return managers_list, greedy, "greedy"
