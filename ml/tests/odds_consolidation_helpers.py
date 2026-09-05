"""Shared odds-consolidation test helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import cast

import pandas as pd

from draft_oracle.ingest.odds import (
    SOURCE_SBR,
    parse_espn_completion,
    parse_sbr_archive,
    parse_sbr_workbook,
    resolve_team_id,
)
from tests.test_odds import _write_sbr_workbook


@dataclass(frozen=True)
class _KagglePair:
    game_id: int
    date: str
    season: int
    home: str
    away: str
    price: object


def parse_sbr_workbook_from_rows(
    tmp_path: Path, season: str, rows: list[list[object]]
) -> pd.DataFrame:
    path = tmp_path / f"nhl-odds-{season}.xlsx"
    _write_sbr_workbook(path, rows)
    return parse_sbr_workbook(path)


def _default_archive_dir() -> Path:
    from draft_oracle.ingest.normalize import DEFAULT_ARCHIVE_DIR

    return DEFAULT_ARCHIVE_DIR


def _covered_committed_odds_source() -> pd.DataFrame:
    from draft_oracle.ingest.odds import DEFAULT_ODDS_ARCHIVE_DIR

    sbr = parse_sbr_archive(DEFAULT_ODDS_ARCHIVE_DIR)
    espn = parse_espn_completion(DEFAULT_ODDS_ARCHIVE_DIR / "espn-2025-26-completion" / "games.csv")
    return pd.concat([sbr, espn], ignore_index=True)


def _committed_archive_games() -> pd.DataFrame:
    from draft_oracle.ingest.normalize import load_archive_team_games, normalize_team_games
    from draft_oracle.models.game_win import _pivot_games

    labels = ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]
    team_games = normalize_team_games(load_archive_team_games(_default_archive_dir(), labels))
    games = _pivot_games(team_games)
    games["season_end_year"] = games["season_end_year"].astype(int)
    return games


def _archive_dates_by_matchup(
    games: pd.DataFrame,
) -> dict[tuple[int, int, int], list[pd.Timestamp]]:
    archive_dates: dict[tuple[int, int, int], list[pd.Timestamp]] = {}
    a_season = games["season_end_year"].astype(int).tolist()
    a_home = games["home_team_id"].astype(int).tolist()
    a_away = games["away_team_id"].astype(int).tolist()
    a_date = pd.to_datetime(games["game_date"]).tolist()
    for season, home_id, away_id, when in zip(a_season, a_home, a_away, a_date, strict=True):
        key = (int(season), int(home_id), int(away_id))
        archive_dates.setdefault(key, []).append(pd.Timestamp(when))
    return archive_dates


def _attach_rate(
    odds: pd.DataFrame,
    games: pd.DataFrame,
    archive_dates: dict[tuple[int, int, int], list[pd.Timestamp]],
    seasons: list[int],
) -> tuple[int, float]:
    from draft_oracle.models.game_win import _attach_market

    odds = odds.copy()
    odds["season_end_year"] = odds["season_end_year"].astype(int)
    covered = odds.loc[odds["covered"] & odds["season_end_year"].isin(seasons)].copy()
    covered["game_date"] = pd.to_datetime(covered["game_date"])
    joined = _attach_market(games, odds)
    joined["season_end_year"] = joined["season_end_year"].astype(int)
    hit = joined.loc[:, ["season_end_year", "game_date", "home_team_id", "away_team_id"]].copy()
    hit["_hit"] = joined["market_home_prob"].notna()
    merged = covered.merge(
        hit, on=["season_end_year", "game_date", "home_team_id", "away_team_id"], how="left"
    )
    merged["_hit"] = merged["_hit"].fillna(value=False)
    genuine = merged.loc[_genuine_archive_mask(merged, archive_dates)]
    return len(genuine), float(genuine["_hit"].mean())


def _genuine_archive_mask(
    merged: pd.DataFrame, archive_dates: dict[tuple[int, int, int], list[pd.Timestamp]]
) -> list[bool]:
    return [
        _has_nearby_archive_date(archive_dates, (int(sy), int(hid), int(aid)), pd.Timestamp(gd))
        for sy, gd, hid, aid in zip(
            merged["season_end_year"],
            merged["game_date"],
            merged["home_team_id"],
            merged["away_team_id"],
            strict=True,
        )
    ]


def _has_nearby_archive_date(
    archive_dates: dict[tuple[int, int, int], list[pd.Timestamp]],
    key: tuple[int, int, int],
    game_date: pd.Timestamp,
) -> bool:
    return any(
        abs((game_date - archive_date).days) <= 1 for archive_date in archive_dates.get(key, [])
    )


def _sbr_late_april_regular(*, home: str, away: str, price: int) -> list[dict[str, object]]:
    """A late-April (post Apr-1) two-sided SBR-style row for season 2022."""
    from draft_oracle.ingest.odds import OddsRowGame, _two_sided_row

    home_id = resolve_team_id(home)
    away_id = resolve_team_id(away)
    assert home_id is not None and away_id is not None
    game = OddsRowGame(
        source=SOURCE_SBR,
        season_end_year=2022,
        game_date=date(2022, 4, 29),
        away_id=away_id,
        home_id=home_id,
        away_name=away,
        home_name=home,
        neutral=False,
    )
    return [
        _two_sided_row(
            game,
            away_ml=float(-price + 20),
            home_ml=float(price),
        )
    ]


def _archive_type(
    row: pd.Series,
    types: dict[tuple[int, int, int], dict[date, int]],
) -> int | None:
    from draft_oracle.ingest.odds import _lookup_game_type

    parsed = date.fromisoformat(str(row["game_date"]))
    return _lookup_game_type(
        types,
        int(row["season_end_year"]),
        int(row["home_team_id"]),
        int(row["away_team_id"]),
        parsed,
    )


def _playoff_label_mismatches(
    rows: pd.DataFrame,
    types: dict[tuple[int, int, int], dict[date, int]],
) -> tuple[int, int]:
    counts = [_playoff_label_mismatch(row, types) for _, row in rows.iterrows()]
    wrong_regular = sum(regular for regular, _playoff in counts)
    wrong_playoff = sum(playoff for _regular, playoff in counts)
    return wrong_regular, wrong_playoff


def _playoff_label_mismatch(
    row: pd.Series,
    types: dict[tuple[int, int, int], dict[date, int]],
) -> tuple[int, int]:
    type_id = _archive_type(row, types)
    if type_id is None:
        return 0, 0
    flagged = bool(row["is_playoff"])
    return int(type_id == 2 and flagged), int(type_id == 3 and not flagged)


def _unmatched_covered_rows(
    covered: pd.DataFrame,
    types: dict[tuple[int, int, int], dict[date, int]],
) -> int:
    return sum(1 for _, row in covered.iterrows() if _archive_type(row, types) is None)


def _kaggle_pair(pair: _KagglePair | None = None, **kwargs: object) -> list[dict[str, object]]:
    pair = pair or _KagglePair(
        game_id=int(cast("int", kwargs["game_id"])),
        date=str(kwargs["date"]),
        season=int(cast("int", kwargs["season"])),
        home=str(kwargs["home"]),
        away=str(kwargs["away"]),
        price=kwargs["price"],
    )
    return [
        {
            "game_id": pair.game_id,
            "date": pair.date,
            "season": pair.season,
            "team_name": pair.home,
            "is_home": 1,
            "spread": -1.5,
            "favorite_moneyline": pair.price,
        },
        {
            "game_id": pair.game_id,
            "date": pair.date,
            "season": pair.season,
            "team_name": pair.away,
            "is_home": 0,
            "spread": 1.5,
            "favorite_moneyline": pair.price,
        },
    ]


_KAGGLE_MATCHUPS = [
    ("Boston Bruins", "Toronto Maple Leafs"),
    ("Carolina Hurricanes", "Vegas Golden Knights"),
    ("Colorado Avalanche", "Dallas Stars"),
    ("Edmonton Oilers", "Calgary Flames"),
    ("Florida Panthers", "Tampa Bay Lightning"),
    ("Los Angeles Kings", "Anaheim Ducks"),
    ("Minnesota Wild", "Winnipeg Jets"),
    ("Nashville Predators", "St. Louis Blues"),
    ("New York Rangers", "New Jersey Devils"),
    ("Ottawa Senators", "Montreal Canadiens"),
]
