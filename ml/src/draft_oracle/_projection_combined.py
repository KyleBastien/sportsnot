"""Combined R3+R4 projection-artifact valuation helpers."""

from __future__ import annotations

from collections.abc import Hashable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

import pandas as pd

from draft_oracle.models.series_sim import simulate_series
from draft_oracle.models.shutout import ShutoutFeatureContext

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
        context: ShutoutFeatureContext | None = None,
    ) -> float: ...


class _SeriesMatchup(Protocol):
    win_snapshots: dict[int, dict[str, float]]
    shutout_snapshots: dict[int, dict[str, float]]


TeamRow = dict[str, Any]
DiagnosticRow = dict[str, Any]


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
    diagnostic: DiagnosticRow


@dataclass(frozen=True)
class _CombinedModels:
    win: _WinModel
    shutout: _ShutoutModel


@dataclass(frozen=True)
class _SeriesContext:
    matchups: Mapping[tuple[int, int, int], _SeriesMatchup]
    season: int


@dataclass(frozen=True)
class CombinedValuationInput:
    team_rows: list[TeamRow]
    round_series: pd.DataFrame
    matchups: Mapping[tuple[int, int, int], _SeriesMatchup]
    win_model: _WinModel
    shutout_model: _ShutoutModel
    season: int
    warnings: list[str]

    @property
    def models(self) -> _CombinedModels:
        return _CombinedModels(self.win_model, self.shutout_model)

    @property
    def series_context(self) -> _SeriesContext:
        return _SeriesContext(self.matchups, self.season)


def _predict_hypothetical_series(
    models: _CombinedModels,
    team: _TeamCandidate,
    opponent: _TeamCandidate,
) -> tuple[float, dict[int, float]]:
    """Goalie points + length distribution for ``team`` in a hypothetical series."""
    team_home, top, bottom = _home_order(team, opponent)
    p_top_home = models.win.predict_matchup(top.win_snapshot, bottom.win_snapshot, is_playoff=True)
    p_top_away = 1.0 - models.win.predict_matchup(
        bottom.win_snapshot, top.win_snapshot, is_playoff=True
    )
    shutout_top = models.shutout.predict_matchup(top.shutout_snapshot, bottom.shutout_snapshot)
    shutout_bottom = models.shutout.predict_matchup(bottom.shutout_snapshot, top.shutout_snapshot)
    outcome = simulate_series(
        p_top_home,
        p_top_away,
        shutout_prob_a=shutout_top,
        shutout_prob_b=shutout_bottom,
    )
    if team_home:
        return outcome.e_goalie_points_a, dict(outcome.length_probs)
    return outcome.e_goalie_points_b, dict(outcome.length_probs)


def _home_order(
    team: _TeamCandidate,
    opponent: _TeamCandidate,
) -> tuple[bool, _TeamCandidate, _TeamCandidate]:
    team_ppg = float(team.win_snapshot.get("points_per_game", 0.0))
    opponent_ppg = float(opponent.win_snapshot.get("points_per_game", 0.0))
    if team_ppg >= opponent_ppg:
        return True, team, opponent
    return False, opponent, team


def _series_groups(
    round_series: pd.DataFrame,
    context: _SeriesContext,
) -> list[list[_TeamCandidate]] | None:
    groups: list[list[_TeamCandidate]] = []
    for row in round_series.to_dict("records"):
        group = _series_group(row, context)
        if group is None:
            return None
        groups.append(group)
    return groups


def _series_group(
    row: Mapping[Hashable, Any],
    context: _SeriesContext,
) -> list[_TeamCandidate] | None:
    top_id_raw = row["top_seed_team_id"]
    bottom_id_raw = row["bottom_seed_team_id"]
    if pd.isna(top_id_raw) or pd.isna(bottom_id_raw):
        return None
    top_id = int(top_id_raw)
    bottom_id = int(bottom_id_raw)
    matchup = context.matchups.get(_matchup_key(context.season, top_id, bottom_id))
    if matchup is None:
        return None
    if top_id not in matchup.win_snapshots or bottom_id not in matchup.win_snapshots:
        return None
    return [
        _team_candidate(top_id, str(row["top_seed_abbrev"]), matchup),
        _team_candidate(bottom_id, str(row["bottom_seed_abbrev"]), matchup),
    ]


def _team_candidate(
    team_id: int,
    abbrev: str,
    matchup: _SeriesMatchup,
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
    row_by_abbrev: Mapping[str, TeamRow],
    models: _CombinedModels,
) -> _CombinedTeamValue | None:
    team_row = row_by_abbrev.get(team.abbrev)
    if team_row is None:
        return None
    p_advance = float(team_row["p_series_win"])
    e_goalie_r3 = float(team_row["e_goalie_points"])
    e_goalie_r4, length_r4 = _next_round_value(
        team, opponent_group, row_by_abbrev, models
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
    row_by_abbrev: Mapping[str, TeamRow],
    models: _CombinedModels,
) -> tuple[float, dict[int, float]]:
    e_goalie_r4 = 0.0
    length_r4: dict[int, float] = dict(_EMPTY_LENGTH_PROBS)
    for opponent in opponent_group:
        opp_row = row_by_abbrev.get(opponent.abbrev)
        if opp_row is None:
            continue
        weight = float(opp_row["p_series_win"])
        goalie_points, length_probs = _predict_hypothetical_series(models, team, opponent)
        e_goalie_r4 += weight * goalie_points
        for length, prob in length_probs.items():
            length_r4[length] = length_r4.get(length, 0.0) + weight * prob
    return e_goalie_r4, length_r4


def _apply_combined_valuation(
    request: CombinedValuationInput,
) -> tuple[dict[str, tuple[float, dict[int, float]]], list[DiagnosticRow]] | None:
    """Fold conditional next-round (Cup Final) value into a combined R3+R4 draft."""
    groups = _series_groups(request.round_series, request.series_context)
    if groups is None:
        return None
    if len(groups) != 2:
        request.warnings.append(
            "combined R3+R4 valuation skipped: expected exactly two conference-final series"
        )
        return None

    row_by_abbrev = {str(row["team_abbrev"]): row for row in request.team_rows}
    combined_by_abbrev: dict[str, tuple[float, dict[int, float]]] = {}
    diagnostics: list[DiagnosticRow] = []
    for team_group, opponent_group in ((groups[0], groups[1]), (groups[1], groups[0])):
        for team in team_group:
            value = _team_value(team, opponent_group, row_by_abbrev, request.models)
            if value is None:
                continue
            combined_by_abbrev[value.abbrev] = (value.p_advance, value.length_probs)
            diagnostics.append(value.diagnostic)

    return combined_by_abbrev, diagnostics


def _matchup_key(year: int, team_a: int, team_b: int) -> tuple[int, int, int]:
    """Order-independent key matching the series reconstruction lookup."""
    lo, hi = sorted((int(team_a), int(team_b)))
    return (int(year), lo, hi)
