"""Row builders for projection artifacts."""

from __future__ import annotations

from collections.abc import Hashable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

import pandas as pd

from draft_oracle.models.projections import (
    SkaterRoundRequest,
    _row_seed,
    project_skater_combined,
    project_skater_round,
)
from draft_oracle.models.series_sim import simulate_series


class _ProjectionConfig(Protocol):
    @property
    def seed(self) -> int: ...

    @property
    def n_sims(self) -> int: ...

    @property
    def horizon(self) -> int: ...


def _matchup_key(year: int, team_a: int, team_b: int) -> tuple[int, int, int]:
    """Order-independent key matching the series reconstruction lookup."""
    lo, hi = sorted((int(team_a), int(team_b)))
    return (int(year), lo, hi)


@dataclass(frozen=True)
class _BuildTeamRowsRequest:
    round_series: pd.DataFrame
    matchups: dict[tuple[int, int, int], Any]
    win_model: Any
    shutout_model: Any
    season: int
    playoff_round: int
    warnings: list[str]


def _build_team_rows(
    request: _BuildTeamRowsRequest,
) -> tuple[list[dict[str, Any]], dict[str, dict[int, float]]]:
    """Predict each round matchup; return team rows + per-team length distributions."""
    team_rows: list[dict[str, Any]] = []
    length_by_abbrev: dict[str, dict[int, float]] = {}

    for row in request.round_series.to_dict("records"):
        ids = _seed_team_ids(row)
        if ids is None:
            request.warnings.append(
                f"series {row.get('series_abbrev')} missing a seed team id; skipped"
            )
            continue
        top_id, bottom_id = ids
        top_abbrev = str(row["top_seed_abbrev"])
        bottom_abbrev = str(row["bottom_seed_abbrev"])

        matchup = request.matchups.get(_matchup_key(request.season, top_id, bottom_id))
        if _missing_matchup_snapshots(matchup, top_id, bottom_id):
            request.warnings.append(
                f"no pre-series snapshot for {top_abbrev} vs {bottom_abbrev}; series skipped"
            )
            continue

        outcome, shutout_top, shutout_bottom = _predict_matchup_series(
            request.win_model,
            request.shutout_model,
            matchup,
            top_id,
            bottom_id,
        )
        length_by_abbrev[top_abbrev] = dict(outcome.length_probs)
        length_by_abbrev[bottom_abbrev] = dict(outcome.length_probs)
        team_rows.extend(
            [
                _team_row(
                    _TeamRowRequest(
                        top_id,
                        top_abbrev,
                        bottom_abbrev,
                        True,
                        request.playoff_round,
                        outcome.p_a_win_series,
                        outcome.e_wins_a,
                        outcome.e_games,
                        outcome.e_goalie_points_a,
                        outcome.e_wins_a * float(shutout_top),
                    )
                ),
                _team_row(
                    _TeamRowRequest(
                        bottom_id,
                        bottom_abbrev,
                        top_abbrev,
                        False,
                        request.playoff_round,
                        outcome.p_b_win_series,
                        outcome.e_wins_b,
                        outcome.e_games,
                        outcome.e_goalie_points_b,
                        outcome.e_wins_b * float(shutout_bottom),
                    )
                ),
            ]
        )

    return team_rows, length_by_abbrev


def _seed_team_ids(row: Mapping[Hashable, Any]) -> tuple[int, int] | None:
    top_id_raw = row["top_seed_team_id"]
    bottom_id_raw = row["bottom_seed_team_id"]
    if pd.isna(top_id_raw) or pd.isna(bottom_id_raw):
        return None
    return int(top_id_raw), int(bottom_id_raw)


def _missing_matchup_snapshots(matchup: Any, top_id: int, bottom_id: int) -> bool:
    return (
        matchup is None
        or top_id not in matchup.win_snapshots
        or bottom_id not in matchup.win_snapshots
    )


def _team_row(
    request: _TeamRowRequest,
) -> dict[str, Any]:
    return {
        "team_id": request.team_id,
        "team_abbrev": request.team_abbrev,
        "opponent_abbrev": request.opponent_abbrev,
        "is_top_seed": request.is_top_seed,
        "playoff_round": request.playoff_round,
        "p_series_win": request.p_series_win,
        "e_wins": request.e_wins,
        "e_games": request.e_games,
        "e_goalie_points": request.e_goalie_points,
        "e_shutout_wins": request.e_shutout_wins,
    }


@dataclass(frozen=True)
class _TeamRowRequest:
    team_id: int
    team_abbrev: str
    opponent_abbrev: str
    is_top_seed: bool
    playoff_round: int
    p_series_win: float
    e_wins: float
    e_games: float
    e_goalie_points: float
    e_shutout_wins: float


def _predict_matchup_series(
    win_model: Any,
    shutout_model: Any,
    matchup: Any,
    top_id: int,
    bottom_id: int,
) -> tuple[Any, float, float]:
    top_win = matchup.win_snapshots[top_id]
    bottom_win = matchup.win_snapshots[bottom_id]
    top_sho = matchup.shutout_snapshots[top_id]
    bottom_sho = matchup.shutout_snapshots[bottom_id]
    p_top_home = win_model.predict_matchup(top_win, bottom_win, is_playoff=True)
    p_top_away = 1.0 - win_model.predict_matchup(bottom_win, top_win, is_playoff=True)
    shutout_top = shutout_model.predict_matchup(top_sho, bottom_sho)
    shutout_bottom = shutout_model.predict_matchup(bottom_sho, top_sho)
    return (
        simulate_series(
            p_top_home,
            p_top_away,
            shutout_prob_a=shutout_top,
            shutout_prob_b=shutout_bottom,
        ),
        shutout_top,
        shutout_bottom,
    )


def _build_skater_rows(
    projected: pd.DataFrame,
    length_by_abbrev: dict[str, dict[int, float]],
    injured_ids: set[int],
    *,
    season_id: int,
    playoff_round: int,
    config: _ProjectionConfig,
    combined_by_abbrev: dict[str, tuple[float, dict[int, float]]] | None = None,
) -> list[dict[str, Any]]:
    """Project each eligible skater's round points with a seeded Monte Carlo."""
    rows: list[dict[str, Any]] = []
    for rec in projected.to_dict("records"):
        team_abbrev = str(rec["team_abbrev"])
        length_probs = length_by_abbrev.get(team_abbrev)
        if length_probs is None:
            continue
        player_id = int(rec["player_id"])
        ppg = float(rec["projected_points_per_game"])
        combined = combined_by_abbrev.get(team_abbrev) if combined_by_abbrev else None
        if combined is not None:
            p_advance, next_length_probs = combined
            projection = project_skater_combined(
                ppg,
                length_probs,
                p_advance,
                next_length_probs,
                seed=_row_seed(config.seed, season_id, playoff_round, player_id),
                n_sims=config.n_sims,
                horizon=config.horizon,
            )
        else:
            projection = project_skater_round(
                SkaterRoundRequest(ppg, length_probs),
                seed=_row_seed(config.seed, season_id, playoff_round, player_id),
                n_sims=config.n_sims,
                horizon=config.horizon,
            )
        rows.append(
            {
                "player_id": player_id,
                "player_name": str(rec.get("player_name", "")),
                "team_abbrev": team_abbrev,
                "position": str(rec["position"]),
                "expected_points": projection.expected_points,
                "p10": projection.p10,
                "p50": projection.p50,
                "p90": projection.p90,
                "pts_per_game": projection.pts_per_game,
                "expected_games": projection.expected_games,
                "availability_multiplier": projection.availability_multiplier,
                "injured": player_id in injured_ids,
                "low_confidence": bool(rec.get("low_confidence", False)),
                "ir_stash_ev": float("nan"),
                "ir_stash_value": float("nan"),
                "ir_verdict": "",
            }
        )
    return rows
