"""Shared fixtures for series simulator model tests."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from draft_oracle.ingest.normalize import normalize_team_games
from draft_oracle.models import HOME_ICE_PATTERN

TEAMS = ["AAA", "BBB", "CCC", "DDD"]
STRENGTH = {"AAA": 3.0, "BBB": 1.0, "CCC": -1.0, "DDD": -3.0}
DEFENCE = {"AAA": 0.7, "BBB": 0.5, "CCC": 0.3, "DDD": 0.1}
SHOTS = 30


def _team_row(
    *,
    season_id: int,
    game_type_id: int,
    game_id: int,
    game_date: str,
    team: str,
    gf: int,
    ga: int,
    is_home: bool,
) -> dict[str, object]:
    won = gf > ga
    return {
        "season_id": season_id,
        "game_type_id": game_type_id,
        "game_id": game_id,
        "game_date": game_date,
        "team_id": TEAMS.index(team) + 1,
        "team_abbrev": team,
        "home_road": "H" if is_home else "R",
        "goals_for": gf,
        "goals_against": ga,
        "shots_against": SHOTS,
        "points": 2 if won else 0,
        "win": won,
        "shutout_win": won and ga == 0,
    }


def _game_rows(
    *,
    season_id: int,
    game_type_id: int,
    game_id: int,
    game_date: str,
    home: str,
    away: str,
    home_goals: int,
    away_goals: int,
) -> list[dict[str, object]]:
    return [
        _team_row(
            season_id=season_id,
            game_type_id=game_type_id,
            game_id=game_id,
            game_date=game_date,
            team=home,
            gf=home_goals,
            ga=away_goals,
            is_home=True,
        ),
        _team_row(
            season_id=season_id,
            game_type_id=game_type_id,
            game_id=game_id,
            game_date=game_date,
            team=away,
            gf=away_goals,
            ga=home_goals,
            is_home=False,
        ),
    ]


def _synthetic_league(end_years: list[int], *, seed: int = 0) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Round-robin regular seasons + one best-of-7 (AAA over DDD) per season."""
    rng = np.random.default_rng(seed)
    team_rows: list[dict[str, object]] = []
    series_rows: list[dict[str, object]] = []
    gid = 5_000_000

    for end_year in end_years:
        season_id = (end_year - 1) * 10000 + end_year
        day = 1
        for _ in range(6):
            for i, home in enumerate(TEAMS):
                for away in TEAMS[i + 1 :]:
                    gid += 1
                    p_home = 1.0 / (1.0 + np.exp(-(STRENGTH[home] - STRENGTH[away] + 0.3)))
                    home_win = bool(rng.random() < p_home)
                    winner = home if home_win else away
                    shutout = bool(rng.random() < DEFENCE[winner])
                    loser_goals = 0 if shutout else 2
                    hg, ag = (3, loser_goals) if home_win else (loser_goals, 3)
                    date = f"{end_year - 1}-11-{day:02d}"
                    day = day + 1 if day < 28 else 1
                    team_rows.extend(
                        _game_rows(
                            season_id=season_id,
                            game_type_id=2,
                            game_id=gid,
                            game_date=date,
                            home=home,
                            away=away,
                            home_goals=hg,
                            away_goals=ag,
                        )
                    )

        # Playoff series: AAA (top seed / home ice) beats DDD 4-1, with one
        # shutout, over five games following the 2-2-1-1-1 hosting pattern.
        top, bottom = "AAA", "DDD"
        game_results = [
            (top, 3, 0),  # game 1 (top home) shutout
            (top, 4, 2),  # game 2 (top home)
            (bottom, 1, 3),  # game 3 (bottom home) upset
            (top, 3, 1),  # game 4 (bottom home)
            (top, 2, 1),  # game 5 (top home) clincher
        ]
        for offset, (winner, wg, lg) in enumerate(game_results):
            gid += 1
            host = top if HOME_ICE_PATTERN[offset] == "A" else bottom
            visitor = bottom if host == top else top
            if winner == host:
                hg, ag = wg, lg
            else:
                hg, ag = lg, wg
            team_rows.extend(
                _game_rows(
                    season_id=season_id,
                    game_type_id=3,
                    game_id=gid,
                    game_date=f"{end_year}-04-{10 + offset:02d}",
                    home=host,
                    away=visitor,
                    home_goals=hg,
                    away_goals=ag,
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
                "bottom_seed_wins": 1,
                "winning_team_id": TEAMS.index(top) + 1,
                "losing_team_id": TEAMS.index(bottom) + 1,
            }
        )

    return pd.DataFrame(team_rows), pd.DataFrame(series_rows)


def _real_team_games(season_label: str | None = None) -> pd.DataFrame:
    archive_dir = Path("data/raw/nhl-archive")
    paths = (
        [archive_dir / f"team-games-{season_label}.csv.gz"]
        if season_label is not None
        else sorted(archive_dir.glob("team-games-*.csv.gz"))
    )
    return pd.concat(
        [normalize_team_games(pd.read_csv(path)) for path in paths],
        ignore_index=True,
    )


def _overlap_row(
    *,
    game_id: str,
    game_date: str,
    team: str,
    team_id: int,
    opp: str,
    gf: int,
    ga: int,
    is_home: bool,
    game_type_id: int = 3,
) -> dict[str, object]:
    won = gf > ga
    return {
        "season_id": 20212022,
        "game_type_id": game_type_id,
        "game_id": game_id,
        "game_date": game_date,
        "team_id": team_id,
        "team_abbrev": team,
        "opponent_team_abbrev": opp,
        "home_road": "H" if is_home else "R",
        "goals_for": gf,
        "goals_against": ga,
        "shots_against": SHOTS,
        "points": 2 if won else 0,
        "win": won,
    }


def _overlap_game(
    *,
    game_id: str,
    game_date: str,
    home: str,
    home_id: int,
    away: str,
    away_id: int,
    hg: int,
    ag: int,
) -> list[dict[str, object]]:
    return [
        _overlap_row(
            game_id=game_id, game_date=game_date, team=home, team_id=home_id,
            opp=away, gf=hg, ga=ag, is_home=True,
        ),
        _overlap_row(
            game_id=game_id, game_date=game_date, team=away, team_id=away_id,
            opp=home, gf=ag, ga=hg, is_home=False,
        ),
    ]


