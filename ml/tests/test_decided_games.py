"""Construction guards for the shared archive decided-game pivot."""

from __future__ import annotations

import inspect

import pandas as pd
import pytest

from draft_oracle.models import game_win, series_sim, shutout
from draft_oracle.models._games import pivot_decided_games


def _team_row(*, home: bool, won: bool) -> dict[str, object]:
    return {
        "season_id": 20202021,
        "game_type_id": 2,
        "game_id": 2020020007,
        "game_date": "2021-01-14",
        "team_id": 1 if home else 2,
        "team_abbrev": "NJD" if home else "BOS",
        "home_road": "H" if home else "R",
        "goals_for": 2,
        "points": 2 if won else 1,
        "shots_against": 30,
        "win": won,
    }


def test_shared_pivot_uses_archive_winner_for_tied_shootout_goals() -> None:
    team_games = pd.DataFrame([_team_row(home=True, won=False), _team_row(home=False, won=True)])

    games = pivot_decided_games(team_games)

    assert len(games) == 1
    assert games.iloc[0]["home_goals"] == games.iloc[0]["away_goals"] == 2
    assert games.iloc[0]["home_win"] == 0


def test_shared_pivot_warns_and_excludes_missing_archive_winner() -> None:
    team_games = pd.DataFrame([_team_row(home=True, won=False), _team_row(home=False, won=False)])

    with pytest.warns(RuntimeWarning, match="without exactly one archive winner"):
        games = pivot_decided_games(team_games)

    assert games.empty


def test_all_model_pivots_delegate_to_one_shared_helper() -> None:
    adapters = (game_win._pivot_games, series_sim._pivot_all_games, shutout._pivot_games)

    assert game_win.__dict__["pivot_decided_games"] is pivot_decided_games
    assert series_sim.__dict__["pivot_decided_games"] is pivot_decided_games
    assert shutout.__dict__["pivot_decided_games"] is pivot_decided_games
    for adapter in adapters:
        source = inspect.getsource(adapter)
        assert "pivot_decided_games(team_games)" in source
        assert ".merge(" not in source
        assert "win_home" not in source
