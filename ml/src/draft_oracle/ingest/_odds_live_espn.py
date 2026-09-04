"""ESPN summary parsing helpers for live odds."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class _FavoritePrice:
    moneyline: float | None
    side: str | None


def espn_summary_to_rows(
    summary: Mapping[str, Any],
    *,
    source_label: str,
) -> pd.DataFrame:
    """Convert one ESPN ``summary`` payload into a favorite-only odds row."""
    from draft_oracle.ingest.odds import (
        _empty_odds_frame,
        _favorite_only_row,
        _finalize,
        _uncovered_row,
    )

    game = _espn_summary_game(summary, source_label=source_label)
    if game is None:
        return _empty_odds_frame()
    favorite = _espn_pickcenter_favorite(summary.get("pickcenter"))
    if favorite.moneyline is None or favorite.side is None:
        return _finalize([_uncovered_row(game)])
    return _finalize(
        [
            _favorite_only_row(
                game,
                favorite_ml=favorite.moneyline,
                favorite_side=favorite.side,
            )
        ]
    )


def _espn_summary_game(
    summary: Mapping[str, Any],
    *,
    source_label: str,
) -> Any:
    from draft_oracle.ingest.odds import OddsRowGame, _parse_utc_date, resolve_team_id

    competition = _first_espn_competition(summary)
    if competition is None:
        return None
    home_name, away_name = _espn_competitor_names(competition)
    game_date = _parse_utc_date(competition.get("date"))
    if home_name is None or away_name is None or game_date is None:
        return None
    home_id = resolve_team_id(home_name)
    away_id = resolve_team_id(away_name)
    if home_id is None or away_id is None:
        return None
    season_end_year = game_date.year if game_date.month < 8 else game_date.year + 1
    return OddsRowGame(
        source=source_label,
        season_end_year=season_end_year,
        game_date=game_date,
        away_id=away_id,
        home_id=home_id,
        away_name=away_name,
        home_name=home_name,
        neutral=False,
    )


def _first_espn_competition(summary: Mapping[str, Any]) -> dict[str, Any] | None:
    competitions = _dig(summary, "header", "competitions")
    if not isinstance(competitions, list) or not competitions:
        return None
    first = competitions[0]
    return first if isinstance(first, dict) else None


def _espn_competitor_names(competition: Mapping[str, Any]) -> tuple[str | None, str | None]:
    competitors = competition.get("competitors", [])
    if not isinstance(competitors, list):
        return None, None
    names = {
        side: name
        for side, name in (_espn_competitor_side_name(item) for item in competitors)
        if side is not None
    }
    return names.get("home"), names.get("away")


def _espn_competitor_side_name(competitor: object) -> tuple[str | None, str | None]:
    if not isinstance(competitor, Mapping):
        return None, None
    team = competitor.get("team", {})
    name = team.get("displayName") if isinstance(team, Mapping) else None
    side = competitor.get("homeAway")
    return str(side) if side is not None else None, str(name) if name is not None else None


def _espn_pickcenter_favorite(pickcenter: object) -> _FavoritePrice:
    from draft_oracle.ingest.odds import _american, _pickcenter_favorite_side

    if not isinstance(pickcenter, list) or not pickcenter:
        return _FavoritePrice(None, None)
    first = pickcenter[0]
    if not isinstance(first, Mapping):
        return _FavoritePrice(None, None)
    favorite_ml = _pickcenter_favorite_ml(first)
    favorite_side = _pickcenter_favorite_side(first)
    home_relative_spread = _american(first.get("spread"))
    if favorite_side is None and home_relative_spread not in (None, 0.0):
        favorite_side = "home" if home_relative_spread < 0 else "away"
    return _FavoritePrice(favorite_ml, favorite_side)


def _pickcenter_favorite_ml(pickcenter: Mapping[str, Any]) -> float | None:
    """Extract favorite's moneyline from ESPN ``pickcenter`` entry."""
    from draft_oracle.ingest.odds import _american

    for side_key in ("homeTeamOdds", "awayTeamOdds"):
        coerced = _favorite_side_moneyline(pickcenter.get(side_key))
        if coerced is not None:
            return coerced
    return _american(pickcenter.get("moneyLine"))


def _favorite_side_moneyline(side: object) -> float | None:
    from draft_oracle.ingest.odds import _american

    if not isinstance(side, Mapping) or not side.get("favorite"):
        return None
    return _american(side.get("moneyLine"))


def _dig(obj: Any, *keys: str) -> Any:
    """Safely walk nested mappings; return ``None`` on any miss."""
    current = obj
    for key in keys:
        if not isinstance(current, Mapping) or key not in current:
            return None
        current = current[key]
    return current
