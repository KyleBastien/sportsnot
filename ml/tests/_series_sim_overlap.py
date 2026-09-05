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


@dataclass(frozen=True)
class _OverlapRowRequest:
    game_id: str
    game_date: str
    team_id: int
    team: str
    opp: str
    goals_for: int
    goals_against: int
    is_home: bool


def _overlap_game(spec: _OverlapGameInput) -> list[dict[str, object]]:
    return [_home_overlap_row(spec), _away_overlap_row(spec)]


def _home_overlap_row(spec: _OverlapGameInput) -> dict[str, object]:
    return _overlap_row(
        _OverlapRowRequest(
            spec.game_id,
            spec.game_date,
            spec.home_id,
            spec.home,
            spec.away,
            spec.hg,
            spec.ag,
            True,
        )
    )


def _away_overlap_row(spec: _OverlapGameInput) -> dict[str, object]:
    return _overlap_row(
        _OverlapRowRequest(
            spec.game_id,
            spec.game_date,
            spec.away_id,
            spec.away,
            spec.home,
            spec.ag,
            spec.hg,
            False,
        )
    )


def _overlap_row(request: _OverlapRowRequest) -> dict[str, object]:
    won = request.goals_for > request.goals_against
    return {
        "season_id": 20212022,
        "game_type_id": 3,
        "game_id": request.game_id,
        "game_date": request.game_date,
        "team_id": request.team_id,
        "team_abbrev": request.team,
        "opponent_team_abbrev": request.opp,
        "home_road": "H" if request.is_home else "R",
        "goals_for": request.goals_for,
        "goals_against": request.goals_against,
        "shots_against": 30,
        "points": 2 if won else 0,
        "win": won,
    }
