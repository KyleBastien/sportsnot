"""League-history comparison helpers for backtest replay."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from draft_oracle.backtest._replay_events import ROUND_TO_DRAFT_EVENT
from draft_oracle.backtest._replay_scoring import ScoreContext, _score_league_roster
from draft_oracle.backtest._replay_types import LeagueComparison, LeagueManagerRoster, RoundResult
from draft_oracle.optimize.opponents import dedupe_duplicate_events, event_keys

ActualLookup = dict[tuple[int, int, int], int]


@dataclass(frozen=True)
class _RoundLeagueScope:
    rnd: RoundResult
    event: str
    scored_rounds: list[int]
    picks: pd.DataFrame
    oracle_points: list[float]


def _league_comparisons(
    rounds: list[RoundResult],
    league_picks: pd.DataFrame | None,
    skater_actual: ActualLookup,
    team_actual: ActualLookup,
) -> list[LeagueComparison]:
    """Compare oracle simulated rosters to real league rosters where seasons overlap."""
    if not _has_league_picks(league_picks):
        return []
    assert league_picks is not None
    prepared = dedupe_duplicate_events(league_picks)
    comparisons: list[LeagueComparison] = []
    for rnd in rounds:
        scope = _round_league_scope(rnd, prepared)
        if scope is None:
            continue
        comparisons.extend(_event_comparisons(scope, skater_actual, team_actual))
    return comparisons


def _has_league_picks(league_picks: pd.DataFrame | None) -> bool:
    return league_picks is not None and not league_picks.empty and "season" in league_picks.columns


def _round_league_scope(rnd: RoundResult, prepared: pd.DataFrame) -> _RoundLeagueScope | None:
    event = ROUND_TO_DRAFT_EVENT.get(rnd.playoff_round)
    if event is None:
        return None
    scoped = _event_picks(prepared, rnd.season, event)
    if scoped.empty:
        return None
    oracle_points = [slot.oracle_points for slot in rnd.slot_results if slot.strategy == "oracle"]
    if not oracle_points:
        return None
    return _RoundLeagueScope(
        rnd=rnd,
        event=event,
        scored_rounds=rnd.scored_rounds or [rnd.playoff_round],
        picks=scoped,
        oracle_points=oracle_points,
    )


def _event_picks(prepared: pd.DataFrame, season: int, event: str) -> pd.DataFrame:
    return prepared.loc[
        (prepared["season"].astype(int) == int(season))
        & (prepared["draft_event"].astype(str) == event)
    ]


def _event_comparisons(
    scope: _RoundLeagueScope, skater_actual: ActualLookup, team_actual: ActualLookup
) -> list[LeagueComparison]:
    return [
        _event_comparison(scope, picks, skater_actual, team_actual)
        for _, picks in scope.picks.groupby(event_keys(scope.picks), sort=True, dropna=False)
    ]


def _event_comparison(
    scope: _RoundLeagueScope,
    picks: pd.DataFrame,
    skater_actual: ActualLookup,
    team_actual: ActualLookup,
) -> LeagueComparison:
    return LeagueComparison(
        season=scope.rnd.season,
        playoff_round=scope.rnd.playoff_round,
        draft_event=scope.event,
        managers=_manager_rosters(scope, picks, skater_actual, team_actual),
        oracle_mean_points=sum(scope.oracle_points) / len(scope.oracle_points),
        oracle_best_points=max(scope.oracle_points),
        league_name=_league_name(picks),
    )


def _manager_rosters(
    scope: _RoundLeagueScope,
    picks: pd.DataFrame,
    skater_actual: ActualLookup,
    team_actual: ActualLookup,
) -> list[LeagueManagerRoster]:
    rosters = [
        LeagueManagerRoster(
            manager=str(manager),
            actual_points=_score_league_roster(
                manager_picks,
                ScoreContext(skater_actual, team_actual, scope.rnd.season_id, scope.scored_rounds),
            ),
        )
        for manager, manager_picks in picks.groupby("manager")
    ]
    return sorted(rosters, key=lambda roster: (-roster.actual_points, roster.manager))


def _league_name(picks: pd.DataFrame) -> str | None:
    if "league_name" not in picks.columns:
        return None
    raw = picks["league_name"].iloc[0]
    if pd.isna(raw):
        return None
    return str(raw)
