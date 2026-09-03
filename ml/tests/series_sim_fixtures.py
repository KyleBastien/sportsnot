"""Shared fixtures for series simulator model tests."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from draft_oracle.ingest.normalize import normalize_team_games
from draft_oracle.models import HOME_ICE_PATTERN

TEAMS = ["AAA", "BBB", "CCC", "DDD"]
STRENGTH = {"AAA": 3.0, "BBB": 1.0, "CCC": -1.0, "DDD": -3.0}
DEFENCE = {"AAA": 0.7, "BBB": 0.5, "CCC": 0.3, "DDD": 0.1}
SHOTS = 30


@dataclass(frozen=True)
class _TeamRowInput:
    season_id: int
    game_type_id: int
    game_id: int
    game_date: str
    team: str
    gf: int
    ga: int
    is_home: bool


@dataclass(frozen=True)
class _GameRowsInput:
    season_id: int
    game_type_id: int
    game_id: int
    game_date: str
    home: str
    away: str
    home_goals: int
    away_goals: int


@dataclass(frozen=True)
class _OverlapRowInput:
    game_id: str
    game_date: str
    team: str
    team_id: int
    opp: str
    gf: int
    ga: int
    is_home: bool
    game_type_id: int = 3


@dataclass(frozen=True)
class _OverlapGameInput:
    game_id: str
    game_date: str
    home: str
    home_id: int
    away: str
    away_id: int
    hg: int
    ag: int


def _team_row(spec: _TeamRowInput) -> dict[str, object]:
    won = spec.gf > spec.ga
    return {
        "season_id": spec.season_id,
        "game_type_id": spec.game_type_id,
        "game_id": spec.game_id,
        "game_date": spec.game_date,
        "team_id": TEAMS.index(spec.team) + 1,
        "team_abbrev": spec.team,
        "home_road": "H" if spec.is_home else "R",
        "goals_for": spec.gf,
        "goals_against": spec.ga,
        "shots_against": SHOTS,
        "points": 2 if won else 0,
        "win": won,
        "shutout_win": won and spec.ga == 0,
    }


def _game_rows(game: _GameRowsInput) -> list[dict[str, object]]:
    return [
        _team_row(
            _TeamRowInput(
                game.season_id,
                game.game_type_id,
                game.game_id,
                game.game_date,
                game.home,
                game.home_goals,
                game.away_goals,
                True,
            )
        ),
        _team_row(
            _TeamRowInput(
                game.season_id,
                game.game_type_id,
                game.game_id,
                game.game_date,
                game.away,
                game.away_goals,
                game.home_goals,
                False,
            )
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
                            _GameRowsInput(season_id, 2, gid, date, home, away, hg, ag)
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
                    _GameRowsInput(
                        season_id,
                        3,
                        gid,
                        f"{end_year}-04-{10 + offset:02d}",
                        host,
                        visitor,
                        hg,
                        ag,
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
                "bottom_seed_wins": 1,
                "winning_team_id": TEAMS.index(top) + 1,
                "losing_team_id": TEAMS.index(bottom) + 1,
            }
        )

    return pd.DataFrame(team_rows), pd.DataFrame(series_rows)


def _real_team_games(season_label: str | None = None) -> pd.DataFrame:
    archive_dir = Path("data/raw/nhl-archive")
    paths = _archive_paths(archive_dir, season_label)
    return pd.concat(_archive_frames(paths), ignore_index=True)


def _archive_paths(archive_dir: Path, season_label: str | None) -> list[Path]:
    if season_label is not None:
        return [archive_dir / f"team-games-{season_label}.csv.gz"]
    return sorted(archive_dir.glob("team-games-*.csv.gz"))


def _archive_frames(paths: list[Path]) -> list[pd.DataFrame]:
    return [normalize_team_games(pd.read_csv(path)) for path in paths]


def _overlap_row(spec: _OverlapRowInput) -> dict[str, object]:
    won = spec.gf > spec.ga
    return {
        "season_id": 20212022,
        "game_type_id": spec.game_type_id,
        "game_id": spec.game_id,
        "game_date": spec.game_date,
        "team_id": spec.team_id,
        "team_abbrev": spec.team,
        "opponent_team_abbrev": spec.opp,
        "home_road": "H" if spec.is_home else "R",
        "goals_for": spec.gf,
        "goals_against": spec.ga,
        "shots_against": SHOTS,
        "points": 2 if won else 0,
        "win": won,
    }


def _overlap_game(
    spec: _OverlapGameInput,
) -> list[dict[str, object]]:
    return [
        _overlap_row(
            _OverlapRowInput(
                spec.game_id,
                spec.game_date,
                spec.home,
                spec.home_id,
                spec.away,
                spec.hg,
                spec.ag,
                True,
            )
        ),
        _overlap_row(
            _OverlapRowInput(
                spec.game_id,
                spec.game_date,
                spec.away,
                spec.away_id,
                spec.home,
                spec.ag,
                spec.hg,
                False,
            )
        ),
    ]
