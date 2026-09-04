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
from tests._projection_round_one import _round1_series_games, _RoundOneSeriesInput

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
_PRE_ROUND_TEAM_IDS = {team: TEAMS.index(team) + 1 for team in TEAMS}
_PRE_ROUND_SERIES = (("AAA", "DDD"), ("BBB", "CCC"))


@dataclass(frozen=True)
class _PreRoundRegularSeasonRequest:
    sk_rows: list[dict[str, object]]
    tg_rows: list[dict[str, object]]
    players: dict[int, tuple[str, float, str]]
    rng: np.random.Generator
    end_year: int
    gid_start: int


@dataclass(frozen=True)
class _PreRoundSeasonRequest:
    sk_rows: list[dict[str, object]]
    tg_rows: list[dict[str, object]]
    series_rows: list[dict[str, object]]
    players: dict[int, tuple[str, float, str]]
    rng: np.random.Generator
    end_year: int
    target: int
    gid_start: int


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
        gid = _append_pre_round_season(
            _PreRoundSeasonRequest(
                sk_rows,
                tg_rows,
                series_rows,
                players,
                rng,
                end_year,
                target,
                gid,
            )
        )

    return (
        pd.DataFrame(sk_rows),
        pd.DataFrame(tg_rows),
        players_df,
        pd.DataFrame(series_rows),
    )


def _append_pre_round_season(request: _PreRoundSeasonRequest) -> int:
    season_id, gid = _append_pre_round_regular_season(
        _PreRoundRegularSeasonRequest(
            request.sk_rows,
            request.tg_rows,
            request.players,
            request.rng,
            request.end_year,
            request.gid_start,
        )
    )
    for top, bottom in _PRE_ROUND_SERIES:
        new_tg, new_sk, gid = _round1_series_games(
            _RoundOneSeriesInput(
                gid_start=gid,
                top=top,
                bottom=bottom,
                end_year=request.end_year,
                season_id=season_id,
                rng=request.rng,
                players=request.players,
                team_ids=_PRE_ROUND_TEAM_IDS,
            )
        )
        request.tg_rows.extend(new_tg)
        request.sk_rows.extend(new_sk)
        request.series_rows.append(
            _completed_round_one_series_row(request.end_year, season_id, top, bottom)
        )
    _append_pending_round_two_series(
        request.series_rows,
        request.end_year,
        season_id,
        request.target,
    )
    return gid


def _append_pre_round_regular_season(
    request: _PreRoundRegularSeasonRequest,
) -> tuple[int, int]:
    season_id = (request.end_year - 1) * 10000 + request.end_year
    gid = request.gid_start
    day, month = 1, 11
    for _ in range(36 // (len(TEAMS) - 1)):
        for i, home in enumerate(TEAMS):
            for away in TEAMS[i + 1 :]:
                gid += 1
                date = f"{request.end_year - 1}-{month:02d}-{day:02d}"
                day += 1
                if day > 27:
                    day, month = 1, (12 if month == 11 else 11)
                _append_pre_round_game(
                    request.sk_rows,
                    request.tg_rows,
                    request.players,
                    request.rng,
                    gid=gid,
                    date=date,
                    season_id=season_id,
                    home=home,
                    away=away,
                )
    return season_id, gid


def _append_pre_round_game(
    sk_rows: list[dict[str, object]],
    tg_rows: list[dict[str, object]],
    players: dict[int, tuple[str, float, str]],
    rng: np.random.Generator,
    *,
    gid: int,
    date: str,
    season_id: int,
    home: str,
    away: str,
) -> None:
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
        for player_id, (player_team, rate, pos) in players.items():
            if player_team != team:
                continue
            goals, assists = _draw_ga(rng, rate)
            sk_rows.append(
                _skater_row(
                    _SkaterRowInput(
                        player_id,
                        pos,
                        gid,
                        date,
                        season_id,
                        2,
                        team,
                        opp,
                        goals,
                        assists,
                    )
                )
            )


def _completed_round_one_series_row(
    end_year: int,
    season_id: int,
    top: str,
    bottom: str,
) -> dict[str, object]:
    return {
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


def _append_pending_round_two_series(
    series_rows: list[dict[str, object]],
    end_year: int,
    season_id: int,
    target: int,
) -> None:
    if end_year != target:
        return
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
