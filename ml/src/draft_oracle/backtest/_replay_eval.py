"""Backtest projection and series-evaluation helpers."""

from __future__ import annotations

from collections.abc import Hashable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import pandas as pd

from draft_oracle.backtest._replay_types import ProjectionEval, SeriesEval
from draft_oracle.models.series_sim import simulate_series


@dataclass(frozen=True)
class _ProjectionEvalRequest:
    result: Any
    skater_actual: dict[tuple[int, int, int], int]
    team_actual: dict[tuple[int, int, int], int]
    season_id: int
    scored_rounds: Sequence[int]


def _round_series(series: pd.DataFrame, season: int, playoff_round: int) -> pd.DataFrame:
    """The ``series`` rows for one backtested season+round."""
    return series.loc[
        (series["year"].astype(int) == int(season))
        & (series["playoff_round"].astype("Int64") == int(playoff_round))
    ]


def _market_series_prob(
    odds: pd.DataFrame | None, top_id: int, bottom_id: int, season: int
) -> float | None:
    """Market-implied ``P(top seed wins the series)`` from the series' game-1 line.

    Locates the *first* (pre-series) playoff game between the two teams that season,
    reads the de-vigged implied win probability for the top seed from that single
    game-1 moneyline, and runs it through the exact best-of-7 series model. Only the
    game-1 line — set before any series game is played — informs the number, so this is
    a genuine *as-of-round-start* benchmark: in-series (game 2+) closing lines are never
    averaged in (CODE_REVIEW M-5). The game-1 probability is applied symmetrically to
    both venues because only one venue's line (the top seed's home opener) exists before
    the series starts. ``None`` when no committed odds cover the matchup. This is a
    post-hoc calibration measurement of the series model under market inputs — it is
    never used to make a pick.
    """
    if odds is None or odds.empty:
        return None
    scoped = odds.loc[
        (odds["season_end_year"].astype(int) == int(season))
        & odds["is_playoff"].fillna(False).astype(bool)
        & (
            ((odds["home_team_id"] == top_id) & (odds["away_team_id"] == bottom_id))
            | ((odds["home_team_id"] == bottom_id) & (odds["away_team_id"] == top_id))
        )
    ].dropna(subset=["home_implied", "away_implied"])
    if scoped.empty:
        return None
    # Game 1 is the earliest-dated game between the two teams; ``game_date`` is an ISO
    # string so a lexical minimum is chronological. Restricting to that date drops every
    # mid-series closing line.
    game_one_date = scoped["game_date"].min()
    game_one = scoped.loc[scoped["game_date"] == game_one_date]
    top_home = game_one.loc[game_one["home_team_id"] == top_id, "home_implied"].astype(float)
    top_away = game_one.loc[game_one["away_team_id"] == top_id, "away_implied"].astype(float)
    top_probs = pd.concat([top_home, top_away])
    if top_probs.empty:
        return None
    p_top_game_one = float(top_probs.mean())
    return simulate_series(p_top_game_one, p_top_game_one).p_a_win_series


def _build_projection_eval(request: _ProjectionEvalRequest) -> ProjectionEval:
    """Pair every as-of projection with its realized outcome across the scored rounds."""
    skaters: list[tuple[int, float, float]] = []
    for rec in request.result.skaters.to_dict("records"):
        pid = int(rec["player_id"])
        projected = float(rec["expected_points"])
        actual = float(
            sum(
                request.skater_actual.get((request.season_id, rnd, pid), 0)
                for rnd in request.scored_rounds
            )
        )
        skaters.append((pid, projected, actual))
    teams: list[tuple[int, float, float]] = []
    for rec in request.result.teams.to_dict("records"):
        tid = int(rec["team_id"])
        projected = float(rec["e_goalie_points"])
        actual = float(
            sum(
                request.team_actual.get((request.season_id, rnd, tid), 0)
                for rnd in request.scored_rounds
            )
        )
        teams.append((tid, projected, actual))
    return ProjectionEval(skaters=skaters, teams=teams)


def _build_series_evals(
    result: Any,
    round_series: pd.DataFrame,
    odds: pd.DataFrame | None,
    *,
    season: int,
) -> list[SeriesEval]:
    """Per-series stat-only + market-aware win probabilities vs. the actual winner."""
    stat_by_team = {
        int(rec["team_id"]): float(rec["p_series_win"]) for rec in result.teams.to_dict("records")
    }
    evals: list[SeriesEval] = []
    for row in round_series.to_dict("records"):
        ids = _series_ids(row)
        if ids is None:
            continue
        top_id, bottom_id, winner_id = ids
        if top_id not in stat_by_team:
            continue
        top_won = 1 if winner_id == top_id else 0
        evals.append(
            SeriesEval(
                top_id=top_id,
                bottom_id=bottom_id,
                top_seed_abbrev=str(row.get("top_seed_abbrev", "")),
                bottom_seed_abbrev=str(row.get("bottom_seed_abbrev", "")),
                top_won=top_won,
                p_top_stat=stat_by_team[top_id],
                p_top_market=_market_series_prob(odds, top_id, bottom_id, season),
            )
        )
    return evals


def _series_ids(row: Mapping[Hashable, Any]) -> tuple[int, int, int] | None:
    """Typed team ids for one series row, or ``None`` when the row is incomplete."""
    top_raw = row.get("top_seed_team_id")
    bottom_raw = row.get("bottom_seed_team_id")
    winner_raw = row.get("winning_team_id")
    missing_ids = [pd.isna(value) for value in (top_raw, bottom_raw, winner_raw)]
    if any(missing_ids):
        return None
    assert top_raw is not None and bottom_raw is not None and winner_raw is not None
    return int(top_raw), int(bottom_raw), int(winner_raw)
