"""Combined R3+R4 projection-artifact valuation helpers."""

from __future__ import annotations

from collections.abc import Hashable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

import pandas as pd

from draft_oracle.models.series_sim import simulate_series

_COMBINED_DRAFT_ROUND = 3
_COMBINED_SCORED_ROUNDS = (3, 4)
_EMPTY_LENGTH_PROBS: dict[int, float] = {4: 0.0, 5: 0.0, 6: 0.0, 7: 0.0}
_COMBINED_CHEATSHEET_NOTE = (
    "Combined R3+R4 draft: projections span the conference final and the "
    "conditional Cup Final (weighted by each team's advance probability). In "
    "teams.csv/parquet, e_goalie_points is combined R3+R4; e_wins, e_games, and "
    "e_shutout_wins remain R3-only."
)


class _WinModel(Protocol):
    def predict_matchup(
        self,
        home: dict[str, float],
        away: dict[str, float],
        *,
        is_playoff: bool = False,
        market_home_prob: float | None = None,
    ) -> float: ...


class _ShutoutModel(Protocol):
    def predict_matchup(
        self,
        winner: dict[str, float],
        loser: dict[str, float],
        *,
        backup_save_pct: float | None = None,
        starter_unavailability_risk: float = 0.0,
        goalie_injury_data_available: bool = False,
    ) -> float: ...


class _SeriesMatchup(Protocol):
    win_snapshots: dict[int, dict[str, float]]
    shutout_snapshots: dict[int, dict[str, float]]


@dataclass(frozen=True)
class _TeamCandidate:
    team_id: int
    abbrev: str
    win_snapshot: dict[str, float]
    shutout_snapshot: dict[str, float]


@dataclass(frozen=True)
class _CombinedTeamValue:
    abbrev: str
    p_advance: float
    length_probs: dict[int, float]
    diagnostic: dict[str, Any]


def _predict_hypothetical_series(
    win_model: _WinModel,
    shutout_model: _ShutoutModel,
    win_x: dict[str, float],
    sho_x: dict[str, float],
    win_y: dict[str, float],
    sho_y: dict[str, float],
) -> tuple[float, dict[int, float]]:
    """Goalie points + length distribution for team X in a hypothetical series."""
    x_home = float(win_x.get("points_per_game", 0.0)) >= float(win_y.get("points_per_game", 0.0))
    if x_home:
        top_win, bottom_win, top_sho, bottom_sho = win_x, win_y, sho_x, sho_y
    else:
        top_win, bottom_win, top_sho, bottom_sho = win_y, win_x, sho_y, sho_x
    p_top_home = win_model.predict_matchup(top_win, bottom_win, is_playoff=True)
    p_top_away = 1.0 - win_model.predict_matchup(bottom_win, top_win, is_playoff=True)
    shutout_top = shutout_model.predict_matchup(top_sho, bottom_sho)
    shutout_bottom = shutout_model.predict_matchup(bottom_sho, top_sho)
    outcome = simulate_series(
        p_top_home,
        p_top_away,
        shutout_prob_a=shutout_top,
        shutout_prob_b=shutout_bottom,
    )
    if x_home:
        return outcome.e_goalie_points_a, dict(outcome.length_probs)
    return outcome.e_goalie_points_b, dict(outcome.length_probs)


def _series_groups(
    round_series: pd.DataFrame,
    matchups: Mapping[tuple[int, int, int], _SeriesMatchup],
    season: int,
) -> list[list[_TeamCandidate]] | None:
    groups: list[list[_TeamCandidate]] = []
    for row in round_series.to_dict("records"):
        group = _series_group(row, matchups, season)
        if group is None:
            return None
        groups.append(group)
    return groups


def _series_group(
    row: Mapping[Hashable, Any],
    matchups: Mapping[tuple[int, int, int], _SeriesMatchup],
    season: int,
) -> list[_TeamCandidate] | None:
    top_id_raw = row["top_seed_team_id"]
    bottom_id_raw = row["bottom_seed_team_id"]
    if pd.isna(top_id_raw) or pd.isna(bottom_id_raw):
        return None
    top_id = int(top_id_raw)
    bottom_id = int(bottom_id_raw)
    matchup = matchups.get(_matchup_key(season, top_id, bottom_id))
    if matchup is None:
        return None
    if top_id not in matchup.win_snapshots or bottom_id not in matchup.win_snapshots:
        return None
    return [
        _team_candidate(top_id, str(row["top_seed_abbrev"]), matchup),
        _team_candidate(bottom_id, str(row["bottom_seed_abbrev"]), matchup),
    ]


def _team_candidate(
    team_id: int, abbrev: str, matchup: _SeriesMatchup
) -> _TeamCandidate:
    return _TeamCandidate(
        team_id=team_id,
        abbrev=abbrev,
        win_snapshot=matchup.win_snapshots[team_id],
        shutout_snapshot=matchup.shutout_snapshots[team_id],
    )


def _team_value(
    team: _TeamCandidate,
    opponent_group: list[_TeamCandidate],
    row_by_abbrev: Mapping[str, dict[str, Any]],
    win_model: _WinModel,
    shutout_model: _ShutoutModel,
) -> _CombinedTeamValue | None:
    team_row = row_by_abbrev.get(team.abbrev)
    if team_row is None:
        return None
    p_advance = float(team_row["p_series_win"])
    e_goalie_r3 = float(team_row["e_goalie_points"])
    e_goalie_r4, length_r4 = _next_round_value(
        team, opponent_group, row_by_abbrev, win_model, shutout_model
    )
    combined = e_goalie_r3 + p_advance * e_goalie_r4
    team_row["e_goalie_points"] = combined
    return _CombinedTeamValue(
        abbrev=team.abbrev,
        p_advance=p_advance,
        length_probs=length_r4,
        diagnostic={
            "team_abbrev": team.abbrev,
            "p_advance": round(p_advance, 6),
            "e_goalie_points_r3": round(e_goalie_r3, 6),
            "e_goalie_points_r4": round(e_goalie_r4, 6),
            "e_goalie_points_combined": round(combined, 6),
        },
    )


def _next_round_value(
    team: _TeamCandidate,
    opponent_group: list[_TeamCandidate],
    row_by_abbrev: Mapping[str, dict[str, Any]],
    win_model: _WinModel,
    shutout_model: _ShutoutModel,
) -> tuple[float, dict[int, float]]:
    e_goalie_r4 = 0.0
    length_r4: dict[int, float] = dict(_EMPTY_LENGTH_PROBS)
    for opponent in opponent_group:
        opp_row = row_by_abbrev.get(opponent.abbrev)
        if opp_row is None:
            continue
        weight = float(opp_row["p_series_win"])
        goalie_points, length_probs = _predict_hypothetical_series(
            win_model,
            shutout_model,
            team.win_snapshot,
            team.shutout_snapshot,
            opponent.win_snapshot,
            opponent.shutout_snapshot,
        )
        e_goalie_r4 += weight * goalie_points
        for length, prob in length_probs.items():
            length_r4[length] = length_r4.get(length, 0.0) + weight * prob
    return e_goalie_r4, length_r4


def _apply_combined_valuation(
    team_rows: list[dict[str, Any]],
    round_series: pd.DataFrame,
    matchups: Mapping[tuple[int, int, int], _SeriesMatchup],
    win_model: _WinModel,
    shutout_model: _ShutoutModel,
    season: int,
    warnings: list[str],
) -> tuple[dict[str, tuple[float, dict[int, float]]], list[dict[str, Any]]] | None:
    """Fold conditional next-round (Cup Final) value into a combined R3+R4 draft."""
    groups = _series_groups(round_series, matchups, season)
    if groups is None:
        return None
    if len(groups) != 2:
        warnings.append(
            "combined R3+R4 valuation skipped: expected exactly two conference-final series"
        )
        return None

    row_by_abbrev = {str(row["team_abbrev"]): row for row in team_rows}
    combined_by_abbrev: dict[str, tuple[float, dict[int, float]]] = {}
    diagnostics: list[dict[str, Any]] = []
    for team_group, opponent_group in ((groups[0], groups[1]), (groups[1], groups[0])):
        for team in team_group:
            value = _team_value(team, opponent_group, row_by_abbrev, win_model, shutout_model)
            if value is None:
                continue
            combined_by_abbrev[value.abbrev] = (value.p_advance, value.length_probs)
            diagnostics.append(value.diagnostic)

    return combined_by_abbrev, diagnostics


def _matchup_key(year: int, team_a: int, team_b: int) -> tuple[int, int, int]:
    """Order-independent key matching the series reconstruction lookup."""
    lo, hi = sorted((int(team_a), int(team_b)))
    return (int(year), lo, hi)
