"""Shared normalization of paired team-game rows into decided games."""

from __future__ import annotations

import warnings

import pandas as pd

__all__ = ["pivot_decided_games"]


def pivot_decided_games(team_games: pd.DataFrame) -> pd.DataFrame:
    """Return one canonical row per game with exactly one archive winner.

    The normalized NHL archive stores one row per team. Home/road pairing belongs
    here so every model uses the same winner rule. The archive's ``win`` column is
    authoritative because shootout goals are absent from ``goals_for`` and can leave
    the two goal totals equal.
    """
    frame = team_games.copy()
    frame["game_date"] = pd.to_datetime(frame["game_date"])
    home = frame.loc[frame["home_road"] == "H"]
    away = frame.loc[frame["home_road"] == "R"]
    merged = home.merge(away, on="game_id", suffixes=("_home", "_away"))

    home_won = merged["win_home"].fillna(False).astype(bool)
    away_won = merged["win_away"].fillna(False).astype(bool)
    decided = home_won.ne(away_won)
    undecided_count = int((~decided).sum())
    if undecided_count:
        warnings.warn(
            "pivot_decided_games excluded "
            f"{undecided_count} games without exactly one archive winner",
            RuntimeWarning,
            stacklevel=2,
        )

    merged = merged.loc[decided].copy()
    home_won = home_won.loc[decided]
    games = pd.DataFrame(
        {
            "game_id": merged["game_id"],
            "season_id": merged["season_id_home"].astype(int),
            "season_end_year": (merged["season_id_home"] % 10000).astype(int),
            "game_type_id": merged["game_type_id_home"].astype(int),
            "game_date": merged["game_date_home"],
            "home_team_id": merged["team_id_home"].astype(int),
            "away_team_id": merged["team_id_away"].astype(int),
            "home_team_abbrev": merged["team_abbrev_home"],
            "away_team_abbrev": merged["team_abbrev_away"],
            "home_goals": merged["goals_for_home"].astype(int),
            "away_goals": merged["goals_for_away"].astype(int),
            "home_points": merged["points_home"].fillna(0).astype(int),
            "away_points": merged["points_away"].fillna(0).astype(int),
            "home_win": home_won.astype(int),
        }
    )
    if "shots_against_home" in merged.columns:
        games["home_shots_against"] = merged["shots_against_home"].fillna(0).astype(int)
        games["away_shots_against"] = merged["shots_against_away"].fillna(0).astype(int)
    return games.sort_values(["game_date", "game_id"], kind="stable").reset_index(drop=True)
