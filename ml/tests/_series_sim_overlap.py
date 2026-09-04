from __future__ import annotations

from dataclasses import dataclass


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


def _overlap_game(spec: _OverlapGameInput) -> list[dict[str, object]]:
    return [_home_overlap_row(spec), _away_overlap_row(spec)]


def _home_overlap_row(spec: _OverlapGameInput) -> dict[str, object]:
    return _overlap_row(
        game_id=spec.game_id,
        game_date=spec.game_date,
        team_id=spec.home_id,
        team=spec.home,
        opp=spec.away,
        goals_for=spec.hg,
        goals_against=spec.ag,
        is_home=True,
    )


def _away_overlap_row(spec: _OverlapGameInput) -> dict[str, object]:
    return _overlap_row(
        game_id=spec.game_id,
        game_date=spec.game_date,
        team_id=spec.away_id,
        team=spec.away,
        opp=spec.home,
        goals_for=spec.ag,
        goals_against=spec.hg,
        is_home=False,
    )


def _overlap_row(
    *,
    game_id: str,
    game_date: str,
    team_id: int,
    team: str,
    opp: str,
    goals_for: int,
    goals_against: int,
    is_home: bool,
) -> dict[str, object]:
    won = goals_for > goals_against
    return {
        "season_id": 20212022,
        "game_type_id": 3,
        "game_id": game_id,
        "game_date": game_date,
        "team_id": team_id,
        "team_abbrev": team,
        "opponent_team_abbrev": opp,
        "home_road": "H" if is_home else "R",
        "goals_for": goals_for,
        "goals_against": goals_against,
        "shots_against": 30,
        "points": 2 if won else 0,
        "win": won,
    }
