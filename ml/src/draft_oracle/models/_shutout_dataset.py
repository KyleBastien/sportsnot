"""Leakage-free shutout modelling dataset assembly."""

from __future__ import annotations

from collections.abc import Hashable, Mapping
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from draft_oracle.models._games import pivot_decided_games
from draft_oracle.models.game_win import REGULAR_SEASON_GAME_TYPE

# League-average team save percentage; the neutral prior for the backup split when
# no per-goalie data is available (the archive has none -- SPEC section 1).
NEUTRAL_SAVE_PCT = 0.9


@dataclass
class ShutoutTeamState:
    """Mutable per-team running regular-season state accumulated from earlier games."""

    games: int = 0
    goals_for: int = 0
    goals_against: int = 0
    shots_against: int = 0
    shutout_wins: int = 0
    recent: list[tuple[int, int]] = field(default_factory=list)
    last_n: int = 15

    def snapshot(self) -> dict[str, float]:
        """Pre-game goaltending + offence proxies from the state accumulated so far."""
        if self.games == 0:
            return {
                "save_pct_season": 0.0,
                "save_pct_l15": 0.0,
                "team_shutout_rate": 0.0,
                "goals_for_per_game": 0.0,
            }
        recent_ga = sum(ga for ga, _ in self.recent)
        recent_sa = sum(sa for _, sa in self.recent)
        return {
            "save_pct_season": _save_pct(self.goals_against, self.shots_against),
            "save_pct_l15": _save_pct(recent_ga, recent_sa),
            "team_shutout_rate": self.shutout_wins / self.games,
            "goals_for_per_game": self.goals_for / self.games,
        }

    def record_regular_season(
        self, *, goals_for: int, goals_against: int, shots_against: int, won: bool
    ) -> None:
        """Fold a completed regular-season game into the running counters."""
        self.games += 1
        self.goals_for += goals_for
        self.goals_against += goals_against
        self.shots_against += shots_against
        self.shutout_wins += int(won and goals_against == 0)
        self.recent.append((goals_against, shots_against))
        if len(self.recent) > self.last_n:
            self.recent = self.recent[-self.last_n :]

    def reset_season(self) -> None:
        """Clear per-season counters at a season boundary."""
        self.games = 0
        self.goals_for = 0
        self.goals_against = 0
        self.shots_against = 0
        self.shutout_wins = 0
        self.recent = []


@dataclass
class _ShutoutReplay:
    states: dict[str, ShutoutTeamState]
    rows: list[dict[str, float]]
    last_n: int
    last_season: int | None = None


@dataclass(frozen=True)
class _GameTeams:
    home: ShutoutTeamState
    away: ShutoutTeamState
    home_goals: int
    away_goals: int
    home_won: bool


@dataclass(frozen=True)
class _WinnerFrame:
    winner: ShutoutTeamState
    loser: ShutoutTeamState
    goals_against: int
    pregame_games: int


def _save_pct(goals_against: float, shots_against: float) -> float:
    """Team save percentage ``1 - GA / shots-against`` (``0.0`` with no shots)."""
    if shots_against <= 0:
        return 0.0
    return 1.0 - (float(goals_against) / float(shots_against))


def shutout_feature_row(
    winner: dict[str, float],
    loser: dict[str, float],
    *,
    backup_save_pct: float | None = None,
    starter_unavailability_risk: float = 0.0,
    goalie_injury_data_available: bool = False,
) -> dict[str, float]:
    """Build the model feature row for a winner/loser matchup from state snapshots."""
    return {
        "winner_save_pct_season": winner["save_pct_season"],
        "winner_save_pct_l15": winner["save_pct_l15"],
        "winner_team_shutout_rate": winner["team_shutout_rate"],
        "opponent_goals_for_per_game": loser["goals_for_per_game"],
        "backup_save_pct": (
            NEUTRAL_SAVE_PCT if backup_save_pct is None else float(backup_save_pct)
        ),
        "goalie_split_available": 0.0 if backup_save_pct is None else 1.0,
        "starter_unavailability_risk": float(starter_unavailability_risk),
        "goalie_injury_data_available": 1.0 if goalie_injury_data_available else 0.0,
    }


def _pivot_games(team_games: pd.DataFrame) -> pd.DataFrame:
    """Adapt shared decided-game rows to shutout's column contract."""
    games = pivot_decided_games(team_games).rename(
        columns={
            "home_team_abbrev": "home_abbrev",
            "away_team_abbrev": "away_abbrev",
        }
    )
    columns = [
        "game_id",
        "season_id",
        "season_end_year",
        "game_type_id",
        "game_date",
        "home_abbrev",
        "away_abbrev",
        "home_goals",
        "away_goals",
        "home_shots_against",
        "away_shots_against",
        "home_win",
    ]
    return games.loc[:, columns]


def build_shutout_dataset(
    team_games: pd.DataFrame,
    *,
    last_n: int = 15,
    min_pregame_games: int = 5,
) -> pd.DataFrame:
    """Assemble the winner-framed shutout modelling frame with pre-game features."""
    replay = _ShutoutReplay(states={}, rows=[], last_n=last_n)
    for record in _pivot_games(team_games).to_dict("records"):
        _replay_shutout_game(replay, record)

    dataset = pd.DataFrame(replay.rows)
    if dataset.empty:
        return dataset
    keep = dataset["winner_pregame_games"] >= min_pregame_games
    return dataset.loc[keep].reset_index(drop=True)


def _replay_shutout_game(
    replay: _ShutoutReplay,
    record: Mapping[Hashable, Any],
) -> None:
    _reset_if_new_season(replay, int(record["season_id"]))
    teams = _game_teams(replay, record)
    winner = _winner_frame(teams)
    _append_shutout_row(replay.rows, record, winner)
    _record_regular_season_game(record, teams)


def _reset_if_new_season(replay: _ShutoutReplay, season: int) -> None:
    if replay.last_season is None or season == replay.last_season:
        replay.last_season = season
        return
    for state in replay.states.values():
        state.reset_season()
    replay.last_season = season


def _game_teams(replay: _ShutoutReplay, record: Mapping[Hashable, Any]) -> _GameTeams:
    home_abbrev = str(record["home_abbrev"])
    away_abbrev = str(record["away_abbrev"])
    return _GameTeams(
        home=replay.states.setdefault(home_abbrev, ShutoutTeamState(last_n=replay.last_n)),
        away=replay.states.setdefault(away_abbrev, ShutoutTeamState(last_n=replay.last_n)),
        home_goals=int(record["home_goals"]),
        away_goals=int(record["away_goals"]),
        home_won=bool(record["home_win"]),
    )


def _winner_frame(teams: _GameTeams) -> _WinnerFrame:
    if teams.home_won:
        return _WinnerFrame(
            winner=teams.home,
            loser=teams.away,
            goals_against=teams.away_goals,
            pregame_games=teams.home.games,
        )
    return _WinnerFrame(
        winner=teams.away,
        loser=teams.home,
        goals_against=teams.home_goals,
        pregame_games=teams.away.games,
    )


def _append_shutout_row(
    rows: list[dict[str, float]],
    record: Mapping[Hashable, Any],
    winner: _WinnerFrame,
) -> None:
    row = shutout_feature_row(winner.winner.snapshot(), winner.loser.snapshot())
    row["game_id"] = float(record["game_id"])
    row["season_end_year"] = float(record["season_end_year"])
    row["game_type_id"] = float(record["game_type_id"])
    row["is_shutout"] = float(winner.goals_against == 0)
    row["winner_pregame_games"] = float(winner.pregame_games)
    rows.append(row)


def _record_regular_season_game(
    record: Mapping[Hashable, Any],
    teams: _GameTeams,
) -> None:
    if int(record["game_type_id"]) != REGULAR_SEASON_GAME_TYPE:
        return
    teams.home.record_regular_season(
        goals_for=teams.home_goals,
        goals_against=teams.away_goals,
        shots_against=int(record["home_shots_against"]),
        won=teams.home_won,
    )
    teams.away.record_regular_season(
        goals_for=teams.away_goals,
        goals_against=teams.home_goals,
        shots_against=int(record["away_shots_against"]),
        won=not teams.home_won,
    )
