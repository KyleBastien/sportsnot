"""Shared projection-artifact fixtures."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from draft_oracle.models.series_sim import HOME_ICE_PATTERN
from draft_oracle.models.skater_production import SkaterProductionConfig
from draft_oracle.projection_artifact import ProjectArtifactConfig
from tests._fixture_rows import (
    SkaterRowInput as _SkaterRowInput,
)
from tests._fixture_rows import (
    draw_ga as _draw_ga,
)
from tests._fixture_rows import (
    skater_row as _skater_row,
)

TEAMS = ["AAA", "BBB", "CCC", "DDD"]
STRENGTH = {"AAA": 3.0, "BBB": 1.0, "CCC": -1.0, "DDD": -3.0}
TEAM_RATE = {"AAA": 0.9, "BBB": 0.6, "CCC": 0.4, "DDD": 0.2}

def _players() -> tuple[pd.DataFrame, dict[int, tuple[str, float, str]]]:
    players: dict[int, tuple[str, float, str]] = {}
    rows: list[dict[str, object]] = []
    pid = 100
    for team in TEAMS:
        for offset, pos in ((0.25, "F"), (-0.1, "D")):
            players[pid] = (team, TEAM_RATE[team] + offset, pos)
            rows.append(
                {
                    "player_id": pid,
                    "player_name": f"{team}-{pid}",
                    "last_name": f"L{pid}",
                    "birth_date": "1996-01-01",
                    "position_code": "C" if pos == "F" else "D",
                    "position": pos,
                    "shoots_catches": "L",
                    "current_team_abbrev": team,
                }
            )
            pid += 1
    return pd.DataFrame(rows), players

@dataclass(frozen=True)
class _TeamRowsInput:
    game_id: int
    game_date: str
    season_id: int
    game_type_id: int
    home: str
    away: str
    home_goals: int
    away_goals: int


def _team_rows(spec: _TeamRowsInput) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for team, opp, gf, ga, is_home in (
        (spec.home, spec.away, spec.home_goals, spec.away_goals, True),
        (spec.away, spec.home, spec.away_goals, spec.home_goals, False),
    ):
        won = gf > ga
        rows.append(
            {
                "season_id": spec.season_id,
                "game_type_id": spec.game_type_id,
                "game_id": spec.game_id,
                "game_date": spec.game_date,
                "team_id": TEAMS.index(team) + 1,
                "team_abbrev": team,
                "opponent_team_abbrev": opp,
                "home_road": "H" if is_home else "R",
                "goals_for": gf,
                "goals_against": ga,
                "shots_against": 30,
                "points": 2 if won else 0,
                "win": won,
                "shutout_win": won and ga == 0,
            }
        )
    return rows

def _synthetic_archive(
    end_years: list[int], *, seed: int = 0, n_reg: int = 36
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Round-robin regular seasons + a first-round AAA-over-DDD best-of-7 each year."""
    rng = np.random.default_rng(seed)
    players_df, players = _players()
    sk_rows: list[dict[str, object]] = []
    tg_rows: list[dict[str, object]] = []
    series_rows: list[dict[str, object]] = []
    gid = 6_000_000

    for end_year in end_years:
        season_id = (end_year - 1) * 10000 + end_year
        day, month = 1, 11
        for _ in range(n_reg // (len(TEAMS) - 1)):
            for i, home in enumerate(TEAMS):
                for away in TEAMS[i + 1 :]:
                    gid += 1
                    date = f"{end_year - 1}-{month:02d}-{day:02d}"
                    day += 1
                    if day > 27:
                        day, month = 1, (12 if month == 11 else 11)
                    home_win = STRENGTH[home] + 0.3 >= STRENGTH[away]
                    hg, ag = (3, 1) if home_win else (1, 3)
                    tg_rows.extend(
                        _team_rows(
                            _TeamRowsInput(
                                game_id=gid,
                                game_date=date,
                                season_id=season_id,
                                game_type_id=2,
                                home=home,
                                away=away,
                                home_goals=hg,
                                away_goals=ag,
                            )
                        )
                    )
                    for team, opp in ((home, away), (away, home)):
                        for p, (t, rate, pos) in players.items():
                            if t != team:
                                continue
                            g, a = _draw_ga(rng, rate)
                            sk_rows.append(
                                _skater_row(
                                    _SkaterRowInput(
                                        p,
                                        pos,
                                        gid,
                                        date,
                                        season_id,
                                        2,
                                        team,
                                        opp,
                                        g,
                                        a,
                                    )
                                )
                            )

        top, bottom = "AAA", "DDD"
        results = [
            (top, 3, 0),
            (top, 4, 2),
            (bottom, 3, 1),
            (bottom, 2, 1),
            (top, 3, 2),
            (top, 2, 1),
        ]
        for offset, (winner, wg, lg) in enumerate(results):
            gid += 1
            host = top if HOME_ICE_PATTERN[offset] == "A" else bottom
            visitor = bottom if host == top else top
            hg, ag = (wg, lg) if winner == host else (lg, wg)
            date = f"{end_year}-04-{20 + offset:02d}"
            tg_rows.extend(
                _team_rows(
                    _TeamRowsInput(
                        game_id=gid,
                        game_date=date,
                        season_id=season_id,
                        game_type_id=3,
                        home=host,
                        away=visitor,
                        home_goals=hg,
                        away_goals=ag,
                    )
                )
            )
            for team, opp in ((top, bottom), (bottom, top)):
                for p, (t, rate, pos) in players.items():
                    if t != team:
                        continue
                    g, a = _draw_ga(rng, rate)
                    sk_rows.append(
                        _skater_row(
                            _SkaterRowInput(
                                p,
                                pos,
                                gid,
                                date,
                                season_id,
                                3,
                                team,
                                opp,
                                g,
                                a,
                            )
                        )
                    )
        series_rows.append(
            {
                "year": end_year,
                "season_id": season_id,
                "series_letter": "A",
                "series_abbrev": "AAADDD",
                "playoff_round": 1,
                "top_seed_team_id": TEAMS.index(top) + 1,
                "top_seed_abbrev": top,
                "top_seed_wins": 4,
                "bottom_seed_team_id": TEAMS.index(bottom) + 1,
                "bottom_seed_abbrev": bottom,
                "bottom_seed_wins": 2,
                "winning_team_id": TEAMS.index(top) + 1,
                "losing_team_id": TEAMS.index(bottom) + 1,
            }
        )

    return (
        pd.DataFrame(sk_rows),
        pd.DataFrame(tg_rows),
        players_df,
        pd.DataFrame(series_rows),
    )


_PRODUCTION_CONFIG = SkaterProductionConfig(
    seed=20260827,
    n_val_seasons=1,
    n_test_seasons=1,
    min_confident_games=5,
)

_PROJECT_ARTIFACT_CONFIG = ProjectArtifactConfig(
    seed=20260827,
    n_sims=300,
    production_config=_PRODUCTION_CONFIG,
)

_ARCHIVE = _synthetic_archive([2018, 2019, 2020, 2021, 2022], seed=1)
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


@dataclass(frozen=True)
class _RoundOneGameInput:
    winner: str
    wg: int
    lg: int
    offset: int
    gid: int
    series: _RoundOneSeriesInput


@dataclass(frozen=True)
class _RoundOneGameSpec:
    offset: int
    winner: str
    wg: int
    lg: int


def _round1_game_inputs(spec: _RoundOneSeriesInput) -> list[_RoundOneGameInput]:
    return [
        _RoundOneGameInput(
            winner,
            wg,
            lg,
            offset,
            spec.gid_start + offset + 1,
            spec,
        )
        for offset, (winner, wg, lg) in enumerate(_ROUND_ONE_RESULTS)
    ]


def _round1_series_games(
    spec: _RoundOneSeriesInput,
) -> tuple[list[dict[str, object]], list[dict[str, object]], int]:
    """Emit a completed best-of-7 round-1 series (top wins 4-2) + its skater rows."""
    rounds = [_round1_game_rows(game) for game in _round1_game_inputs(spec)]
    tg_rows = [row for game_rows, _skater_rows in rounds for row in game_rows]
    sk_rows = [row for _game_rows, skater_rows in rounds for row in skater_rows]
    return tg_rows, sk_rows, spec.gid_start + len(_ROUND_ONE_RESULTS)


def _round1_game_rows(
    spec: _RoundOneGameInput,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    host = spec.series.top if HOME_ICE_PATTERN[spec.offset] == "A" else spec.series.bottom
    visitor = spec.series.bottom if host == spec.series.top else spec.series.top
    hg, ag = (spec.wg, spec.lg) if spec.winner == host else (spec.lg, spec.wg)
    date = f"{spec.series.end_year}-04-{20 + spec.offset:02d}"
    game_rows = _team_rows(
        _TeamRowsInput(
            game_id=spec.gid,
            game_date=date,
            season_id=spec.series.season_id,
            game_type_id=3,
            home=host,
            away=visitor,
            home_goals=hg,
            away_goals=ag,
        )
    )
    skater_rows = _round1_game_skaters(spec.series, spec.gid, date)
    return game_rows, skater_rows


def _round1_game_skaters(
    series: _RoundOneSeriesInput,
    gid: int,
    date: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for team, opp in ((series.top, series.bottom), (series.bottom, series.top)):
        for p, (t, rate, pos) in series.players.items():
            if t != team:
                continue
            g, a = _draw_ga(series.rng, rate)
            rows.append(
                _skater_row(
                    _SkaterRowInput(
                        p,
                        pos,
                        gid,
                        date,
                        series.season_id,
                        3,
                        team,
                        opp,
                        g,
                        a,
                    )
                )
            )
    return rows


def _pre_round_archive(
    end_years: list[int], *, seed: int = 3
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Archive with completed round-1 (two series) and a round-2 bracket but NO round-2 games.

    Each season: a round-robin regular season, round-1 series AAA-over-DDD and
    BBB-over-CCC, and (target-season only) a round-2 AAA-vs-BBB series row with zero
    games -- the genuine pre-round decision point (CODE_REVIEW M-1).
    """
    rng = np.random.default_rng(seed)
    players_df, players = _players()
    sk_rows: list[dict[str, object]] = []
    tg_rows: list[dict[str, object]] = []
    series_rows: list[dict[str, object]] = []
    gid = 7_000_000
    target = end_years[-1]

    for end_year in end_years:
        season_id = (end_year - 1) * 10000 + end_year
        day, month = 1, 11
        for _ in range(36 // (len(TEAMS) - 1)):
            for i, home in enumerate(TEAMS):
                for away in TEAMS[i + 1 :]:
                    gid += 1
                    date = f"{end_year - 1}-{month:02d}-{day:02d}"
                    day += 1
                    if day > 27:
                        day, month = 1, (12 if month == 11 else 11)
                    home_win = STRENGTH[home] + 0.3 >= STRENGTH[away]
                    hg, ag = (3, 1) if home_win else (1, 3)
                    tg_rows.extend(
                        _team_rows(
                            _TeamRowsInput(
                                game_id=gid,
                                game_date=date,
                                season_id=season_id,
                                game_type_id=2,
                                home=home,
                                away=away,
                                home_goals=hg,
                                away_goals=ag,
                            )
                        )
                    )
                    for team, opp in ((home, away), (away, home)):
                        for p, (t, rate, pos) in players.items():
                            if t != team:
                                continue
                            g, a = _draw_ga(rng, rate)
                            sk_rows.append(
                                _skater_row(
                                    _SkaterRowInput(
                                        p,
                                        pos,
                                        gid,
                                        date,
                                        season_id,
                                        2,
                                        team,
                                        opp,
                                        g,
                                        a,
                                    )
                                )
                            )

        for top, bottom in (("AAA", "DDD"), ("BBB", "CCC")):
            new_tg, new_sk, gid = _round1_series_games(
                _RoundOneSeriesInput(gid, top, bottom, end_year, season_id, rng, players)
            )
            tg_rows.extend(new_tg)
            sk_rows.extend(new_sk)
            series_rows.append(
                {
                    "year": end_year,
                    "season_id": season_id,
                    "series_letter": top,
                    "series_abbrev": top + bottom,
                    "playoff_round": 1,
                    "top_seed_team_id": TEAMS.index(top) + 1,
                    "top_seed_abbrev": top,
                    "top_seed_wins": 4,
                    "bottom_seed_team_id": TEAMS.index(bottom) + 1,
                    "bottom_seed_abbrev": bottom,
                    "bottom_seed_wins": 2,
                    "winning_team_id": TEAMS.index(top) + 1,
                    "losing_team_id": TEAMS.index(bottom) + 1,
                }
            )

        if end_year == target:
            series_rows.append(
                {
                    "year": end_year,
                    "season_id": season_id,
                    "series_letter": "R2",
                    "series_abbrev": "AAABBB",
                    "playoff_round": 2,
                    "top_seed_team_id": TEAMS.index("AAA") + 1,
                    "top_seed_abbrev": "AAA",
                    "top_seed_wins": 0,
                    "bottom_seed_team_id": TEAMS.index("BBB") + 1,
                    "bottom_seed_abbrev": "BBB",
                    "bottom_seed_wins": 0,
                    "winning_team_id": None,
                    "losing_team_id": None,
                }
            )

    return (
        pd.DataFrame(sk_rows),
        pd.DataFrame(tg_rows),
        players_df,
        pd.DataFrame(series_rows),
    )
