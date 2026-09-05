"""Build paid-request plans from authoritative NHL archive game times."""

from __future__ import annotations

import csv
import gzip
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from odds_archive_common import parse_timestamp
from odds_history_models import (
    HISTORY_FLOOR,
    PLAYOFF_MARKETS,
    REGULAR_MARKETS,
    SEASONS,
    Game,
    RequestPlan,
)


def _read_csv_gz(path: Path) -> list[dict[str, str]]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _game_names_by_id(team_rows: list[dict[str, str]]) -> dict[str, tuple[str, str]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in team_rows:
        grouped[row["gameId"]].append(row)
    return {game_id: _home_away_names(game_id, rows) for game_id, rows in grouped.items()}


def _home_away_names(game_id: str, rows: list[dict[str, str]]) -> tuple[str, str]:
    home = [row for row in rows if row["homeRoad"] == "H"]
    away = [row for row in rows if row["homeRoad"] == "R"]
    valid_counts = (len(rows), len(home), len(away)) == (2, 1, 1)
    if not valid_counts:
        raise RuntimeError(f"{game_id}: expected one home and one road team row, found {len(rows)}")
    return home[0]["teamFullName"], away[0]["teamFullName"]


def _game_from_row(season: str, row: dict[str, str], names: dict[str, tuple[str, str]]) -> Game:
    game_id = row["gameId"]
    if game_id not in names:
        raise RuntimeError(f"{season} {game_id}: missing team-game names")
    home_name, away_name = names[game_id]
    return Game(
        season=season,
        game_id=game_id,
        game_type_id=row["gameTypeId"],
        game_date=row["gameDate"],
        start=parse_timestamp(row["startTimeUTC"]),
        home_abbrev=row["homeAbbrev"],
        away_abbrev=row["awayAbbrev"],
        home_name=home_name,
        away_name=away_name,
    )


def _load_season_games(archive: Path, season: str) -> list[Game]:
    time_rows = _read_csv_gz(archive / f"game-times-{season}.csv.gz")
    team_rows = _read_csv_gz(archive / f"team-games-{season}.csv.gz")
    names = _game_names_by_id(team_rows)
    return [_game_from_row(season, row, names) for row in time_rows]


def _playoff_plans(season: str, games: list[Game]) -> list[RequestPlan]:
    grouped: dict[datetime, list[Game]] = defaultdict(list)
    for game in games:
        if game.game_type_id == "3":
            start_minute = game.start.replace(second=0, microsecond=0)
            grouped[start_minute - timedelta(minutes=60)].append(game)
    return [
        RequestPlan(
            season=season,
            game_type_id="3",
            requested=requested,
            markets=PLAYOFF_MARKETS,
            games=tuple(sorted(group, key=lambda game: game.game_id)),
        )
        for requested, group in sorted(grouped.items())
    ]


def _regular_plans(season: str, games: list[Game]) -> list[RequestPlan]:
    grouped: dict[str, list[Game]] = defaultdict(list)
    for game in games:
        if game.game_type_id == "2" and game.start >= HISTORY_FLOOR:
            grouped[game.game_date].append(game)
    return [_regular_day_plan(season, group) for group in dict(sorted(grouped.items())).values()]


def _regular_day_plan(season: str, games: list[Game]) -> RequestPlan:
    earliest = min(game.start for game in games).replace(second=0, microsecond=0)
    return RequestPlan(
        season=season,
        game_type_id="2",
        requested=earliest - timedelta(minutes=60),
        markets=REGULAR_MARKETS,
        games=tuple(sorted(games, key=lambda game: game.game_id)),
    )


def build_request_plans(archive: Path) -> list[RequestPlan]:
    games = {season: _load_season_games(archive, season) for season in SEASONS}
    playoff = [
        plan
        for season in SEASONS
        for plan in _playoff_plans(season, games[season])
    ]
    regular = [
        plan
        for season in SEASONS
        for plan in _regular_plans(season, games[season])
    ]
    return playoff + regular


def print_bulk_estimate(plans: list[RequestPlan], prior_credits: int, cap: int) -> None:
    playoff, regular = _plans_by_type(plans)
    playoff_cost = sum(plan.estimated_cost for plan in playoff)
    regular_cost = sum(plan.estimated_cost for plan in regular)
    bulk_cost = playoff_cost + regular_cost
    total = prior_credits + bulk_cost
    print(
        "FULL BULK ESTIMATE: "
        f"playoffs={len(playoff)} requests/{playoff_cost} credits; "
        f"regular={len(regular)} requests/{regular_cost} credits; "
        f"bulk={len(plans)} requests/{bulk_cost} credits; "
        f"prior={prior_credits}; whole-job={total}; cap={cap}",
        flush=True,
    )
    if total > cap:
        raise RuntimeError(f"credit estimate {total} exceeds cap {cap}")


def _plans_by_type(plans: list[RequestPlan]) -> tuple[list[RequestPlan], list[RequestPlan]]:
    playoff: list[RequestPlan] = []
    regular: list[RequestPlan] = []
    for plan in plans:
        target = playoff if plan.game_type_id == "3" else regular
        target.append(plan)
    return playoff, regular
