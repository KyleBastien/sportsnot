from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np

from draft_oracle.models.series_sim import HOME_ICE_PATTERN
from tests._fixture_rows import SkaterRowInput as _SkaterRowInput
from tests._fixture_rows import draw_ga as _draw_ga
from tests._fixture_rows import skater_row as _skater_row

_ROUND_ONE_RESULTS = [
    ("top", 3, 0),
    ("top", 4, 2),
    ("bottom", 3, 1),
    ("bottom", 2, 1),
    ("top", 3, 2),
    ("top", 2, 1),
]


@dataclass(frozen=True)
class _RoundOneSeriesInput:
    gid_start: int
    top: str
    bottom: str
    end_year: int
    season_id: int
    rng: np.random.Generator
    players: dict[int, tuple[str, float, str]]
    team_ids: Mapping[str, int]


@dataclass(frozen=True)
class _RoundOneTeamRowRequest:
    season_id: int
    game_id: int
    game_date: str
    team_id: int
    team: str
    opp: str
    goals_for: int
    goals_against: int
    is_home: bool


def _round1_series_games(
    series: _RoundOneSeriesInput,
) -> tuple[list[dict[str, object]], list[dict[str, object]], int]:
    team_rows: list[dict[str, object]] = []
    skater_rows: list[dict[str, object]] = []
    gid = series.gid_start
    for offset, (winner, winning_goals, losing_goals) in enumerate(_ROUND_ONE_RESULTS):
        gid += 1
        host = series.top if HOME_ICE_PATTERN[offset] == "A" else series.bottom
        visitor = series.bottom if host == series.top else series.top
        home_goals, away_goals = (
            (winning_goals, losing_goals) if winner == host else (losing_goals, winning_goals)
        )
        game_date = f"{series.end_year}-04-{20 + offset:02d}"
        team_rows.extend(
            [
                _team_row(
                    _RoundOneTeamRowRequest(
                        series.season_id,
                        gid,
                        game_date,
                        series.team_ids[host],
                        host,
                        visitor,
                        home_goals,
                        away_goals,
                        True,
                    )
                ),
                _team_row(
                    _RoundOneTeamRowRequest(
                        series.season_id,
                        gid,
                        game_date,
                        series.team_ids[visitor],
                        visitor,
                        host,
                        away_goals,
                        home_goals,
                        False,
                    )
                ),
            ]
        )
        skater_rows.extend(_skater_rows(series, gid, game_date))
    return team_rows, skater_rows, gid


def _team_row(request: _RoundOneTeamRowRequest) -> dict[str, object]:
    won = request.goals_for > request.goals_against
    return {
        "season_id": request.season_id,
        "game_type_id": 3,
        "game_id": request.game_id,
        "game_date": request.game_date,
        "team_id": request.team_id,
        "team_abbrev": request.team,
        "opponent_team_abbrev": request.opp,
        "home_road": "H" if request.is_home else "R",
        "goals_for": request.goals_for,
        "goals_against": request.goals_against,
        "shots_against": 30,
        "points": 2 if won else 0,
        "win": won,
        "shutout_win": won and request.goals_against == 0,
    }


def _skater_rows(
    series: _RoundOneSeriesInput,
    game_id: int,
    game_date: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for team, opp in ((series.top, series.bottom), (series.bottom, series.top)):
        for player_id, (player_team, rate, pos) in series.players.items():
            if player_team != team:
                continue
            goals, assists = _draw_ga(series.rng, rate)
            rows.append(
                _skater_row(
                    _SkaterRowInput(
                        player_id,
                        pos,
                        game_id,
                        game_date,
                        series.season_id,
                        3,
                        team,
                        opp,
                        goals,
                        assists,
                    )
                )
            )
    return rows
