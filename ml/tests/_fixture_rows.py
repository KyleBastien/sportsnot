"""Shared synthetic row builders for projection/backtest fixtures."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class SkaterRowInput:
    player_id: int
    pos: str
    game_id: int
    game_date: str
    season_id: int
    game_type_id: int
    team: str
    opp: str
    goals: int
    assists: int


def skater_row(spec: SkaterRowInput) -> dict[str, object]:
    return {
        'season_id': spec.season_id,
        'game_type_id': spec.game_type_id,
        'game_id': spec.game_id,
        'game_date': spec.game_date,
        'player_id': spec.player_id,
        'player_name': f'{spec.team}-{spec.player_id}',
        'position_code': 'C' if spec.pos == 'F' else 'D',
        'position': spec.pos,
        'shoots_catches': 'L',
        'team_abbrev': spec.team,
        'opponent_team_abbrev': spec.opp,
        'home_road': 'H',
        'goals': spec.goals,
        'assists': spec.assists,
        'points': spec.goals + spec.assists,
        'shots': spec.goals * 3 + 2,
        'toi_seconds': 1000,
        'pp_goals': 0,
        'pp_points': 0,
        'sh_goals': 0,
        'sh_points': 0,
        'ev_goals': spec.goals,
        'ev_points': spec.goals + spec.assists,
        'plus_minus': 0,
        'penalty_minutes': 0,
        'game_winning_goals': 0,
        'ot_goals': 0,
        'shooting_pct': 0.1,
        'faceoff_win_pct': 0.5,
    }


def draw_ga(rng: np.random.Generator, rate: float) -> tuple[int, int]:
    clipped = max(rate * 0.5, 0.01)
    return int(rng.poisson(clipped)), int(rng.poisson(clipped))
