"""Historical series matchup reconstruction helpers."""

from __future__ import annotations

from collections.abc import Hashable, Mapping
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from draft_oracle.features.elo import (
    EloConfig,
    expected_score,
    regress_to_mean,
    update_rating,
)
from draft_oracle.models._games import pivot_decided_games
from draft_oracle.models._skater_rounds import (
    QUALIFYING_ROUND_GAME_DIGIT,
    _playoff_round_digit,
    _series_round_map,
    playoff_round_cutoffs,
)
from draft_oracle.models.game_win import (
    PLAYOFF_GAME_TYPE,
    REGULAR_SEASON_GAME_TYPE,
    TeamState,
)
from draft_oracle.models.shutout import ShutoutTeamState


@dataclass
class _MatchupRecord:
    """Captured pre-series team snapshots + observed playoff shutouts for a matchup."""

    win_snapshots: dict[int, dict[str, float]] = field(default_factory=dict)
    shutout_snapshots: dict[int, dict[str, float]] = field(default_factory=dict)
    observed_shutouts: int = 0
    playoff_games: int = 0


def _pivot_all_games(team_games: pd.DataFrame) -> pd.DataFrame:
    """Adapt shared decided-game rows to series replay's column contract."""
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
        "home_team_id",
        "away_team_id",
        "home_abbrev",
        "away_abbrev",
        "home_goals",
        "away_goals",
        "home_points",
        "away_points",
        "home_shots_against",
        "away_shots_against",
        "home_win",
    ]
    return games.loc[:, columns]


def _matchup_key(year: int, team_a: int, team_b: int) -> tuple[int, int, int]:
    """Order-independent key for a season's matchup between two team ids."""
    lo, hi = sorted((int(team_a), int(team_b)))
    return (int(year), lo, hi)


@dataclass
class _MatchupPlan:
    """A real best-of-seven matchup's declared round cutoff and its two teams."""

    cutoff: pd.Timestamp
    year: int
    id_a: int
    id_b: int
    abbrev_a: str
    abbrev_b: str
    frozen: bool = False


@dataclass
class _ReplayState:
    """Mutable reconstruction state for one chronological game replay."""

    elo_config: EloConfig
    win_states: dict[str, TeamState] = field(default_factory=dict)
    shutout_states: dict[str, ShutoutTeamState] = field(default_factory=dict)
    matchups: dict[tuple[int, int, int], _MatchupRecord] = field(default_factory=dict)
    plans: list[_MatchupPlan] | None = None
    last_season: int | None = None


@dataclass(frozen=True)
class _GameTeams:
    """State objects and scalar facts for both teams in one game row."""

    home_abbrev: str
    away_abbrev: str
    home_win: TeamState
    away_win: TeamState
    home_shutout: ShutoutTeamState
    away_shutout: ShutoutTeamState
    home_won: bool
    home_goals: int
    away_goals: int


def _matchup_cutoff_plan(
    team_games: pd.DataFrame, series: pd.DataFrame
) -> list[_MatchupPlan]:
    """Every real series' pre-round freeze target: its declared round-start cutoff.

    Freezing a matchup's pre-series snapshot at the *round's* start (not the
    matchup's own first game) keeps a slower series from absorbing games played on
    or after the declared ``as_of_cutoff`` when rounds overlap (CODE_REVIEW m-3). A
    round with no games yet (a genuine pre-round build) freezes at the previous
    round's completion boundary instead of its own first game (CODE_REVIEW M-1).
    """
    round_map = _series_round_map(series)
    round_starts = playoff_round_cutoffs(team_games, series)

    abbrev_to_id: dict[tuple[int, str], int] = {}
    tg = team_games[["season_id", "team_abbrev", "team_id"]]
    for rec in tg.drop_duplicates().to_dict("records"):
        abbrev_to_id[(int(rec["season_id"]), str(rec["team_abbrev"]))] = int(
            rec["team_id"]
        )

    plans: list[_MatchupPlan] = []
    for (season_id, pair), rnd in round_map.items():
        cutoff_str = round_starts.get(season_id, {}).get(rnd)
        if cutoff_str is None:
            continue
        id_a = abbrev_to_id.get((season_id, pair[0]))
        id_b = abbrev_to_id.get((season_id, pair[1]))
        if id_a is None or id_b is None:
            continue
        plans.append(
            _MatchupPlan(
                cutoff=pd.Timestamp(cutoff_str),
                year=season_id % 10000,
                id_a=id_a,
                id_b=id_b,
                abbrev_a=pair[0],
                abbrev_b=pair[1],
            )
        )
    plans.sort(key=lambda p: p.cutoff)
    return plans


def _freeze_due_matchups(state: _ReplayState, as_of: pd.Timestamp) -> None:
    """Freeze pre-series snapshots for every planned matchup whose cutoff has arrived."""
    if state.plans is None:
        return
    for plan in state.plans:
        if plan.frozen or plan.cutoff > as_of:
            continue
        a_win = state.win_states.setdefault(
            plan.abbrev_a, TeamState(elo=state.elo_config.initial)
        )
        b_win = state.win_states.setdefault(
            plan.abbrev_b, TeamState(elo=state.elo_config.initial)
        )
        a_sho = state.shutout_states.setdefault(plan.abbrev_a, ShutoutTeamState())
        b_sho = state.shutout_states.setdefault(plan.abbrev_b, ShutoutTeamState())
        key = _matchup_key(plan.year, plan.id_a, plan.id_b)
        matchup = state.matchups.setdefault(key, _MatchupRecord())
        matchup.win_snapshots[plan.id_a] = a_win.snapshot()
        matchup.win_snapshots[plan.id_b] = b_win.snapshot()
        matchup.shutout_snapshots[plan.id_a] = a_sho.snapshot()
        matchup.shutout_snapshots[plan.id_b] = b_sho.snapshot()
        plan.frozen = True


def _reset_new_season_state(state: _ReplayState, season: int) -> None:
    """Regress and reset regular-season counters when replay crosses a season."""
    if state.last_season is None or season == state.last_season:
        state.last_season = season
        return

    for win_state in state.win_states.values():
        win_state.elo = regress_to_mean(
            win_state.elo,
            state.elo_config.initial,
            state.elo_config.season_regression,
        )
        win_state.reg_games = 0
        win_state.reg_points = 0
        win_state.reg_goals_for = 0
        win_state.reg_goals_against = 0
        win_state.reg_wins = 0
    for shutout_state in state.shutout_states.values():
        shutout_state.reset_season()
    state.last_season = season


def _game_teams(state: _ReplayState, record: Mapping[Hashable, Any]) -> _GameTeams:
    home_abbrev = str(record["home_abbrev"])
    away_abbrev = str(record["away_abbrev"])
    return _GameTeams(
        home_abbrev=home_abbrev,
        away_abbrev=away_abbrev,
        home_win=state.win_states.setdefault(
            home_abbrev, TeamState(elo=state.elo_config.initial)
        ),
        away_win=state.win_states.setdefault(
            away_abbrev, TeamState(elo=state.elo_config.initial)
        ),
        home_shutout=state.shutout_states.setdefault(home_abbrev, ShutoutTeamState()),
        away_shutout=state.shutout_states.setdefault(away_abbrev, ShutoutTeamState()),
        home_won=bool(record["home_win"]),
        home_goals=int(record["home_goals"]),
        away_goals=int(record["away_goals"]),
    )


def _is_real_playoff_series_game(record: Mapping[Hashable, Any]) -> bool:
    if int(record["game_type_id"]) != PLAYOFF_GAME_TYPE:
        return False
    return _playoff_round_digit(record["game_id"]) != QUALIFYING_ROUND_GAME_DIGIT


def _count_playoff_game(
    state: _ReplayState,
    record: Mapping[Hashable, Any],
    teams: _GameTeams,
) -> None:
    if not _is_real_playoff_series_game(record):
        return

    year = int(record["season_end_year"])
    home_id = int(record["home_team_id"])
    away_id = int(record["away_team_id"])
    key = _matchup_key(year, home_id, away_id)
    matchup = state.matchups.get(key)
    if matchup is None and state.plans is None:
        matchup = _MatchupRecord()
        matchup.win_snapshots[home_id] = teams.home_win.snapshot()
        matchup.win_snapshots[away_id] = teams.away_win.snapshot()
        matchup.shutout_snapshots[home_id] = teams.home_shutout.snapshot()
        matchup.shutout_snapshots[away_id] = teams.away_shutout.snapshot()
        state.matchups[key] = matchup
    if matchup is None:
        return

    matchup.playoff_games += 1
    if _is_observed_shutout(teams):
        matchup.observed_shutouts += 1


def _is_observed_shutout(teams: _GameTeams) -> bool:
    return (teams.home_won and teams.away_goals == 0) or (
        not teams.home_won and teams.home_goals == 0
    )


def _update_game_states(
    state: _ReplayState,
    record: Mapping[Hashable, Any],
    teams: _GameTeams,
) -> None:
    _update_elo(state, teams)
    if int(record["game_type_id"]) == REGULAR_SEASON_GAME_TYPE:
        _record_regular_season_game(record, teams)


def _update_elo(state: _ReplayState, teams: _GameTeams) -> None:
    exp_home = expected_score(
        teams.home_win.elo,
        teams.away_win.elo,
        state.elo_config.home_advantage,
    )
    actual_home = 1.0 if teams.home_won else 0.0
    teams.home_win.elo = update_rating(
        teams.home_win.elo,
        exp_home,
        actual_home,
        state.elo_config.k,
    )
    teams.away_win.elo = update_rating(
        teams.away_win.elo,
        1.0 - exp_home,
        1.0 - actual_home,
        state.elo_config.k,
    )


def _record_regular_season_game(
    record: Mapping[Hashable, Any],
    teams: _GameTeams,
) -> None:
    teams.home_win.record_regular_season(
        points=int(record["home_points"]),
        goals_for=teams.home_goals,
        goals_against=teams.away_goals,
        won=teams.home_won,
    )
    teams.away_win.record_regular_season(
        points=int(record["away_points"]),
        goals_for=teams.away_goals,
        goals_against=teams.home_goals,
        won=not teams.home_won,
    )
    teams.home_shutout.record_regular_season(
        goals_for=teams.home_goals,
        goals_against=teams.away_goals,
        shots_against=int(record["home_shots_against"]),
        won=teams.home_won,
    )
    teams.away_shutout.record_regular_season(
        goals_for=teams.away_goals,
        goals_against=teams.home_goals,
        shots_against=int(record["away_shots_against"]),
        won=not teams.home_won,
    )


def reconstruct_series_matchups(
    team_games: pd.DataFrame,
    *,
    series: pd.DataFrame | None = None,
    elo_config: EloConfig | None = None,
) -> dict[tuple[int, int, int], _MatchupRecord]:
    """Replay all games once, capturing pre-series states + observed shutouts.

    A single chronological pass maintains, per team, the win model's
    :class:`~draft_oracle.models.game_win.TeamState` (Elo + offensive proxies) and
    the shutout model's :class:`~draft_oracle.models.shutout.ShutoutTeamState`
    (goaltending proxies), using the exact same update rules as those models so the
    features line up.

    When ``series`` is supplied each matchup's pre-series snapshot is frozen at its
    **round's declared start cutoff** (the earliest game of that round), so a series
    that starts later than its round cannot absorb games played on or after that
    cutoff (CODE_REVIEW m-3). Without ``series`` the legacy per-series freeze (at the
    matchup's own first game) is used. In both modes the 2019-20 bubble qualifying
    round and round-robin games (``game_id`` round digit ``0``) never form or count
    toward a matchup (CODE_REVIEW m-6); they still feed Elo like any played game.
    Snapshots read only games strictly before the freeze point, so there is no
    leakage (SPEC section 6).
    """
    state = _ReplayState(
        elo_config=elo_config or EloConfig(),
        plans=_matchup_cutoff_plan(team_games, series) if series is not None else None,
    )
    for record in _pivot_all_games(team_games).to_dict("records"):
        _replay_game(state, record)

    _freeze_due_matchups(state, pd.Timestamp.max)
    return state.matchups


def _replay_game(state: _ReplayState, record: Mapping[Hashable, Any]) -> None:
    _reset_new_season_state(state, int(record["season_id"]))
    teams = _game_teams(state, record)
    _freeze_due_matchups(state, pd.Timestamp(record["game_date"]))
    _count_playoff_game(state, record, teams)
    _update_game_states(state, record, teams)
