#!/usr/bin/env python3
"""Fetch The Odds API NHL history without placing plaintext inside the repo."""

from __future__ import annotations

import argparse
import csv
import gzip
import http.client
import io
import json
import os
import sys
import tempfile
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

API_HOST = "api.the-odds-api.com"
API_ROOT = "/v4"
PROBE_DATE = "2024-04-20T20:00:00Z"
PROBE_HOME = "Carolina Hurricanes"
PROBE_AWAY = "New York Islanders"
MIN_REMAINING = 5_000
SEASONS = tuple(f"{year}-{str(year + 1)[-2:]}" for year in range(2019, 2026))
HISTORY_FLOOR = datetime(2020, 6, 6, tzinfo=UTC)
PLAYOFF_MARKETS = ("h2h", "spreads", "totals")
REGULAR_MARKETS = ("h2h",)
REGIONS = ("us", "eu")
INDEX_COLUMNS = (
    "gameId",
    "gameTypeId",
    "gameDate",
    "archiveStartTimeUTC",
    "requestedTimestamp",
    "returnedSnapshotTimestamp",
    "rawFile",
    "eventId",
    "commenceTime",
    "startTimeDeltaSeconds",
    "apiHomeName",
    "apiAwayName",
    "archiveHomeName",
    "archiveAwayName",
    "archiveHomeAbbrev",
    "archiveAwayAbbrev",
    "bookmakerCount",
    "hasH2h",
    "hasSpreads",
    "hasTotals",
    "matchStatus",
)
LINES_COLUMNS = (
    "gameId",
    "gameTypeId",
    "gameDate",
    "requestedTimestamp",
    "returnedSnapshotTimestamp",
    "eventId",
    "commenceTime",
    "archiveHomeAbbrev",
    "archiveAwayAbbrev",
    "bookmakerKey",
    "bookmakerTitle",
    "bookmakerLastUpdate",
    "marketKey",
    "marketLastUpdate",
    "outcomeName",
    "price",
    "point",
)
MAX_START_DELTA = timedelta(hours=2)


@dataclass(frozen=True)
class Game:
    season: str
    game_id: str
    game_type_id: str
    game_date: str
    start: datetime
    home_abbrev: str
    away_abbrev: str
    home_name: str
    away_name: str


@dataclass(frozen=True)
class RequestPlan:
    season: str
    game_type_id: str
    requested: datetime
    markets: tuple[str, ...]
    games: tuple[Game, ...]

    @property
    def estimated_cost(self) -> int:
        return 10 * len(self.markets) * len(REGIONS)

    @property
    def requested_iso(self) -> str:
        return isoformat(self.requested)

    @property
    def raw_relative_path(self) -> Path:
        filename = self.requested_iso.replace(":", "-") + ".json.gz"
        return Path("raw") / self.game_type_id / filename


# Current region catalog from The Odds API bookmaker documentation. Some keys
# occur in both regions; report those under both rather than guessing ownership.
US_BOOKMAKERS = {
    "betonlineag",
    "betmgm",
    "betrivers",
    "betus",
    "bovada",
    "draftkings",
    "fanatics",
    "fanduel",
    "lowvig",
    "mybookieag",
    "pointsbetus",
    "superbook",
    "unibet_us",
    "williamhill_us",
    "wynnbet",
}
EU_BOOKMAKERS = {
    "onexbet",
    "sport888",
    "betclic_fr",
    "betclic",
    "betanysports",
    "betfair_ex_eu",
    "betonlineag",
    "betsson",
    "codere_it",
    "betvictor",
    "coolbet",
    "everygame",
    "gtbets",
    "leovegas_se",
    "livescorebet_eu",
    "marathonbet",
    "matchbook",
    "mybookieag",
    "nordicbet",
    "pinnacle",
    "pmu_fr",
    "suprabets",
    "tipico_de",
    "unibet_fr",
    "unibet_it",
    "unibet_nl",
    "unibet_se",
    "williamhill",
    "winamax_de",
    "winamax_fr",
}


def load_env_value(name: str) -> str:
    value = os.environ.get(name)
    if value:
        return value
    env_path = Path(__file__).resolve().parents[4] / ".env"
    if env_path.exists():
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, candidate = line.split("=", 1)
            if key.strip() == name:
                value = candidate.strip().strip('"').strip("'")
                if value:
                    return value
    raise RuntimeError(f"{name} is missing from environment and ml/.env")


def quota_headers(headers: dict[str, str]) -> dict[str, int | None]:
    def parsed(name: str) -> int | None:
        value = headers.get(name)
        return int(value) if value is not None else None

    return {
        "remaining": parsed("x-requests-remaining"),
        "used": parsed("x-requests-used"),
        "last": parsed("x-requests-last"),
    }


class Client:
    def __init__(
        self,
        api_key: str,
        scratch: Path,
        max_credits: int,
        *,
        request_log: Path | None = None,
        progress_every: int = 1,
        delay: float = 0.0,
    ) -> None:
        self.api_key = api_key
        self.scratch = scratch
        self.max_credits = max_credits
        self.request_log = request_log
        self.progress_every = progress_every
        self.delay = delay
        self.estimated = 0
        self.actual = 0
        self.network_calls = 0
        self.calls: list[dict[str, Any]] = []

    def get(
        self,
        label: str,
        path: str,
        params: dict[str, str],
        output_name: str,
        estimated_cost: int,
        allowed_statuses: frozenset[int] = frozenset({200}),
    ) -> dict[str, Any]:
        if self.estimated + estimated_cost > self.max_credits:
            raise RuntimeError(
                f"credit guard: {self.estimated + estimated_cost} exceeds {self.max_credits}"
            )
        self.estimated += estimated_cost
        if self.delay:
            time.sleep(self.delay)
        query = urlencode({"apiKey": self.api_key, **params})
        connection = http.client.HTTPSConnection(API_HOST, timeout=180)
        try:
            connection.request(
                "GET",
                f"{API_ROOT}{path}?{query}",
                headers={
                    "Accept": "application/json",
                    "Accept-Encoding": "identity",
                    "User-Agent": "sportsnot-odds-archive/1",
                },
            )
            response = connection.getresponse()
            body = response.read()
            headers = {key.lower(): value for key, value in response.getheaders()}
            status = response.status
        except Exception as exc:
            raise RuntimeError(
                f"{label}: request failed ({type(exc).__name__}); URL suppressed"
            ) from None
        finally:
            connection.close()

        output = self.scratch / output_name
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(gzip.compress(body, mtime=0))
        quota = quota_headers(headers)
        last = quota["last"]
        if last is not None:
            self.actual += last
        record = {
            "label": label,
            "status": status,
            "estimated_cost": estimated_cost,
            "quota": quota,
            "raw_file": output_name,
            "path": path,
            "params": params,
        }
        self.calls.append(record)
        self.network_calls += 1
        if self.request_log is not None:
            self.request_log.parent.mkdir(parents=True, exist_ok=True)
            with self.request_log.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, sort_keys=True) + "\n")
        if (
            self.progress_every == 1
            or self.network_calls == 1
            or self.network_calls % self.progress_every == 0
        ):
            print(
                f"{label}: HTTP {status}; x-requests-remaining={quota['remaining']}; "
                f"x-requests-used={quota['used']}; x-requests-last={quota['last']}",
                flush=True,
            )
        remaining = quota["remaining"]
        if remaining is not None and remaining < MIN_REMAINING:
            raise RuntimeError(f"quota guard: remaining {remaining} below {MIN_REMAINING}")
        if self.actual > self.max_credits:
            raise RuntimeError(f"credit guard: actual {self.actual} exceeds {self.max_credits}")
        if status not in allowed_statuses:
            raise RuntimeError(
                f"{label}: HTTP {status}; response saved outside repo; URL suppressed"
            )
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            raise RuntimeError(
                f"{label}: non-JSON response saved outside repo; URL suppressed"
            ) from None
        if not isinstance(parsed, dict | list):
            raise RuntimeError(f"{label}: unexpected JSON root")
        return parsed


def bookmaker_summary(event: dict[str, Any]) -> dict[str, Any]:
    bookmakers = event.get("bookmakers", [])
    summaries = []
    for bookmaker in bookmakers:
        markets = bookmaker.get("markets", [])
        summaries.append(
            {
                "key": bookmaker.get("key"),
                "title": bookmaker.get("title"),
                "markets": [market.get("key") for market in markets],
                "outcome_counts": {
                    str(market.get("key")): len(market.get("outcomes", [])) for market in markets
                },
            }
        )
    return {
        "count": len(bookmakers),
        "bookmakers": summaries,
    }


def classify_bookmakers(event: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {
        "us": [],
        "eu": [],
        "unclassified": [],
    }
    for bookmaker in event.get("bookmakers", []):
        item = {"key": bookmaker.get("key"), "title": bookmaker.get("title")}
        key = str(bookmaker.get("key"))
        classified = False
        if key in US_BOOKMAKERS:
            grouped["us"].append(item)
            classified = True
        if key in EU_BOOKMAKERS:
            grouped["eu"].append(item)
            classified = True
        if not classified:
            grouped["unclassified"].append(item)
    return grouped


def historical_summary(payload: dict[str, Any]) -> dict[str, Any]:
    events = payload.get("data", [])
    if not isinstance(events, list):
        raise RuntimeError("historical response data is not a list")
    return {
        "timestamp": payload.get("timestamp"),
        "previous_timestamp": payload.get("previous_timestamp"),
        "next_timestamp": payload.get("next_timestamp"),
        "event_count": len(events),
        "bookmaker_entries": sum(len(event.get("bookmakers", [])) for event in events),
        "unique_bookmaker_keys": sorted(
            {
                str(bookmaker.get("key"))
                for event in events
                for bookmaker in event.get("bookmakers", [])
            }
        ),
    }


def isoformat(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise RuntimeError(f"timestamp lacks timezone: {value}")
    return parsed.astimezone(UTC)


def read_csv_gz(path: Path) -> list[dict[str, str]]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def game_names_by_id(team_rows: list[dict[str, str]]) -> dict[str, tuple[str, str]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in team_rows:
        grouped[row["gameId"]].append(row)
    names: dict[str, tuple[str, str]] = {}
    for game_id, rows in grouped.items():
        home = [row for row in rows if row["homeRoad"] == "H"]
        away = [row for row in rows if row["homeRoad"] == "R"]
        if len(rows) != 2 or len(home) != 1 or len(away) != 1:
            raise RuntimeError(
                f"{game_id}: expected one home and one road team row, found {len(rows)}"
            )
        names[game_id] = (home[0]["teamFullName"], away[0]["teamFullName"])
    return names


def load_season_games(archive: Path, season: str) -> list[Game]:
    time_path = archive / f"game-times-{season}.csv.gz"
    team_path = archive / f"team-games-{season}.csv.gz"
    names = game_names_by_id(read_csv_gz(team_path))
    games = []
    for row in read_csv_gz(time_path):
        game_id = row["gameId"]
        if game_id not in names:
            raise RuntimeError(f"{season} {game_id}: missing team-game names")
        home_name, away_name = names[game_id]
        games.append(
            Game(
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
        )
    return games


def build_request_plans(archive: Path) -> list[RequestPlan]:
    games_by_season = {season: load_season_games(archive, season) for season in SEASONS}
    plans = []
    for season in SEASONS:
        grouped: dict[datetime, list[Game]] = defaultdict(list)
        for game in games_by_season[season]:
            if game.game_type_id != "3":
                continue
            start_minute = game.start.replace(second=0, microsecond=0)
            grouped[start_minute - timedelta(minutes=60)].append(game)
        plans.extend(
            RequestPlan(
                season=season,
                game_type_id="3",
                requested=requested,
                markets=PLAYOFF_MARKETS,
                games=tuple(sorted(games, key=lambda game: game.game_id)),
            )
            for requested, games in sorted(grouped.items())
        )

    for season in SEASONS:
        by_game_date: dict[str, list[Game]] = defaultdict(list)
        for game in games_by_season[season]:
            if game.game_type_id != "2" or game.start < HISTORY_FLOOR:
                continue
            by_game_date[game.game_date].append(game)
        for games in dict(sorted(by_game_date.items())).values():
            earliest = min(game.start for game in games).replace(second=0, microsecond=0)
            plans.append(
                RequestPlan(
                    season=season,
                    game_type_id="2",
                    requested=earliest - timedelta(minutes=60),
                    markets=REGULAR_MARKETS,
                    games=tuple(sorted(games, key=lambda game: game.game_id)),
                )
            )
    return plans


def assert_scratch_outside_repo(scratch: Path) -> None:
    repo = Path(__file__).resolve().parents[5]
    try:
        scratch.resolve().relative_to(repo)
    except ValueError:
        return
    raise RuntimeError("scratch directory must be outside repository")


def load_historical_payload(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(gzip.decompress(path.read_bytes()))
    except (OSError, json.JSONDecodeError):
        raise RuntimeError(f"invalid historical response file: {path}") from None
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise RuntimeError(f"unexpected historical response shape: {path}")
    if not isinstance(payload.get("timestamp"), str):
        raise RuntimeError(f"missing snapshot timestamp: {path}")
    return payload


def print_bulk_estimate(plans: list[RequestPlan], prior_credits: int, cap: int) -> None:
    playoff = [plan for plan in plans if plan.game_type_id == "3"]
    regular = [plan for plan in plans if plan.game_type_id == "2"]
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


def event_time_delta(event: dict[str, Any], game: Game) -> timedelta | None:
    value = event.get("commence_time")
    if not isinstance(value, str):
        return None
    try:
        return abs(parse_timestamp(value) - game.start)
    except (RuntimeError, ValueError):
        return None


def match_event(
    events: list[dict[str, Any]], game: Game
) -> tuple[dict[str, Any] | None, str, int | None]:
    candidates = [
        event
        for event in events
        if event.get("home_team") == game.home_name and event.get("away_team") == game.away_name
    ]
    unique_candidates: list[dict[str, Any]] = []
    for candidate in candidates:
        if candidate not in unique_candidates:
            unique_candidates.append(candidate)
    removed_identical_duplicates = len(candidates) - len(unique_candidates)
    timed = [
        (delta, event)
        for event in unique_candidates
        if (delta := event_time_delta(event, game)) is not None and delta <= MAX_START_DELTA
    ]
    if not timed:
        return None, "no_exact_team_and_time_match", None
    timed.sort(key=lambda item: (item[0], str(item[1].get("id", ""))))
    best_delta, best_event = timed[0]
    if len(timed) > 1 and timed[1][0] == best_delta:
        return None, "ambiguous_exact_team_and_time_match", None
    if removed_identical_duplicates:
        status = "matched_after_identical_duplicate_dedup"
    elif len(unique_candidates) == 1:
        status = "matched"
    else:
        status = "matched_nearest_start"
    return best_event, status, int(best_delta.total_seconds())


def bool_text(value: bool) -> str:
    return "true" if value else "false"


def blank_index_row(
    plan: RequestPlan,
    game: Game,
    status: str,
    returned_snapshot: str = "",
) -> dict[str, Any]:
    return {
        "gameId": game.game_id,
        "gameTypeId": game.game_type_id,
        "gameDate": game.game_date,
        "archiveStartTimeUTC": isoformat(game.start),
        "requestedTimestamp": plan.requested_iso,
        "returnedSnapshotTimestamp": returned_snapshot,
        "rawFile": plan.raw_relative_path.as_posix(),
        "eventId": "",
        "commenceTime": "",
        "startTimeDeltaSeconds": "",
        "apiHomeName": "",
        "apiAwayName": "",
        "archiveHomeName": game.home_name,
        "archiveAwayName": game.away_name,
        "archiveHomeAbbrev": game.home_abbrev,
        "archiveAwayAbbrev": game.away_abbrev,
        "bookmakerCount": 0,
        "hasH2h": "false",
        "hasSpreads": "false",
        "hasTotals": "false",
        "matchStatus": status,
    }


def index_row(
    plan: RequestPlan,
    game: Game,
    payload: dict[str, Any],
    event: dict[str, Any],
    status: str,
    delta_seconds: int,
) -> dict[str, Any]:
    bookmakers = event.get("bookmakers", [])
    market_keys = {
        str(market.get("key"))
        for bookmaker in bookmakers
        for market in bookmaker.get("markets", [])
    }
    row = blank_index_row(plan, game, status, str(payload["timestamp"]))
    row.update(
        {
            "returnedSnapshotTimestamp": payload["timestamp"],
            "eventId": event.get("id", ""),
            "commenceTime": event.get("commence_time", ""),
            "startTimeDeltaSeconds": delta_seconds,
            "apiHomeName": event.get("home_team", ""),
            "apiAwayName": event.get("away_team", ""),
            "bookmakerCount": len(bookmakers),
            "hasH2h": bool_text("h2h" in market_keys),
            "hasSpreads": bool_text("spreads" in market_keys),
            "hasTotals": bool_text("totals" in market_keys),
        }
    )
    return row


def line_rows(
    plan: RequestPlan,
    game: Game,
    payload: dict[str, Any],
    event: dict[str, Any],
) -> list[dict[str, Any]]:
    rows = []
    for bookmaker in event.get("bookmakers", []):
        for market in bookmaker.get("markets", []):
            for outcome in market.get("outcomes", []):
                rows.append(
                    {
                        "gameId": game.game_id,
                        "gameTypeId": game.game_type_id,
                        "gameDate": game.game_date,
                        "requestedTimestamp": plan.requested_iso,
                        "returnedSnapshotTimestamp": payload["timestamp"],
                        "eventId": event.get("id", ""),
                        "commenceTime": event.get("commence_time", ""),
                        "archiveHomeAbbrev": game.home_abbrev,
                        "archiveAwayAbbrev": game.away_abbrev,
                        "bookmakerKey": bookmaker.get("key", ""),
                        "bookmakerTitle": bookmaker.get("title", ""),
                        "bookmakerLastUpdate": bookmaker.get("last_update", ""),
                        "marketKey": market.get("key", ""),
                        "marketLastUpdate": market.get("last_update", ""),
                        "outcomeName": outcome.get("name", ""),
                        "price": outcome.get("price", ""),
                        "point": outcome.get("point", ""),
                    }
                )
    return rows


def write_csv_gz(path: Path, columns: tuple[str, ...], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with (
        path.open("wb") as raw,
        gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as compressed,
        io.TextIOWrapper(compressed, encoding="utf-8", newline="") as text,
    ):
        writer = csv.DictWriter(text, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def build_plaintext_tables(scratch: Path, plans: list[RequestPlan]) -> dict[str, dict[str, int]]:
    indexes: dict[str, list[dict[str, Any]]] = defaultdict(list)
    lines: dict[str, list[dict[str, Any]]] = defaultdict(list)
    stats: dict[str, dict[str, int]] = {
        season: {
            "games": 0,
            "matched": 0,
            "unmatched": 0,
            "line_rows": 0,
        }
        for season in SEASONS
    }
    for plan in plans:
        payload = load_historical_payload(scratch / plan.season / plan.raw_relative_path)
        events = payload["data"]
        for game in plan.games:
            stats[plan.season]["games"] += 1
            event, status, delta_seconds = match_event(events, game)
            if event is None or delta_seconds is None:
                indexes[plan.season].append(
                    blank_index_row(plan, game, status, str(payload["timestamp"]))
                )
                stats[plan.season]["unmatched"] += 1
                continue
            indexes[plan.season].append(
                index_row(plan, game, payload, event, status, delta_seconds)
            )
            extracted = line_rows(plan, game, payload, event)
            lines[plan.season].extend(extracted)
            stats[plan.season]["matched"] += 1
            stats[plan.season]["line_rows"] += len(extracted)

    for season in SEASONS:
        indexes[season].sort(key=lambda row: (row["gameDate"], row["gameId"]))
        lines[season].sort(
            key=lambda row: (
                row["gameDate"],
                row["gameId"],
                row["bookmakerKey"],
                row["marketKey"],
                row["outcomeName"],
                str(row["point"]),
            )
        )
        season_dir = scratch / season
        write_csv_gz(season_dir / "index.csv.gz", INDEX_COLUMNS, indexes[season])
        write_csv_gz(season_dir / "lines.csv.gz", LINES_COLUMNS, lines[season])
    return stats


def run_bulk(args: argparse.Namespace) -> None:
    scratch = args.scratch.resolve()
    assert_scratch_outside_repo(scratch)
    archive = Path(__file__).resolve().parents[2] / "nhl-archive"
    plans = build_request_plans(archive)
    print_bulk_estimate(plans, args.prior_credits, args.max_credits)
    scratch.mkdir(parents=True, exist_ok=True)
    request_log = scratch / "_request-log.jsonl"
    client = Client(
        load_env_value("ODDS_API_KEY"),
        scratch,
        args.max_credits - args.prior_credits,
        request_log=request_log,
        progress_every=args.progress_every,
        delay=args.delay,
    )
    reused = 0
    fetched = 0
    for number, plan in enumerate(plans, start=1):
        raw_path = scratch / plan.season / plan.raw_relative_path
        if raw_path.exists():
            load_historical_payload(raw_path)
            reused += 1
            continue
        client.get(
            f"bulk {number}/{len(plans)} {plan.season} type={plan.game_type_id}",
            "/historical/sports/icehockey_nhl/odds",
            {
                "regions": ",".join(REGIONS),
                "markets": ",".join(plan.markets),
                "date": plan.requested_iso,
                "dateFormat": "iso",
                "oddsFormat": "decimal",
            },
            (Path(plan.season) / plan.raw_relative_path).as_posix(),
            estimated_cost=plan.estimated_cost,
        )
        fetched += 1
    stats = build_plaintext_tables(scratch, plans)
    manifest = {
        "seasons": list(SEASONS),
        "requests": len(plans),
        "estimated_bulk_credits": sum(plan.estimated_cost for plan in plans),
        "prior_probe_credits": args.prior_credits,
        "fetched_this_run": fetched,
        "reused": reused,
        "network_credits_this_run": client.actual,
        "stats": stats,
    }
    (scratch / "_bulk-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2, sort_keys=True), flush=True)


def run_probe(args: argparse.Namespace) -> None:
    scratch = args.scratch.resolve()
    repo = Path(__file__).resolve().parents[5]
    try:
        scratch.relative_to(repo)
    except ValueError:
        pass
    else:
        raise RuntimeError("scratch directory must be outside repository")

    client = Client(load_env_value("ODDS_API_KEY"), scratch, args.max_credits)
    sports = client.get(
        "sports",
        "/sports",
        {"all": "true"},
        "probe/sports.json.gz",
        estimated_cost=0,
    )
    if not isinstance(sports, list):
        raise RuntimeError("sports response is not a list")
    nhl_sports = [
        {
            "key": sport.get("key"),
            "title": sport.get("title"),
            "active": sport.get("active"),
            "has_outrights": sport.get("has_outrights"),
        }
        for sport in sports
        if "icehockey_nhl" in str(sport.get("key", ""))
    ]
    outright_sport_keys = ["icehockey_nhl"] + [
        str(sport["key"])
        for sport in nhl_sports
        if sport.get("has_outrights") and sport.get("key") != "icehockey_nhl"
    ]
    paid_estimate = 60 + 20 * len(outright_sport_keys)
    print(
        f"Probe paid-call worst-case estimate: 60 + 20 x {len(outright_sport_keys)} "
        f"= {paid_estimate} credits (cap {args.max_credits})",
        flush=True,
    )
    if paid_estimate > args.max_credits:
        raise RuntimeError("probe estimate exceeds cap")

    featured = client.get(
        "featured-markets probe",
        "/historical/sports/icehockey_nhl/odds",
        {
            "regions": "us,eu",
            "markets": "h2h,spreads,totals",
            "date": PROBE_DATE,
            "dateFormat": "iso",
            "oddsFormat": "decimal",
        },
        "probe/featured.json.gz",
        estimated_cost=60,
    )
    if not isinstance(featured, dict):
        raise RuntimeError("featured response is not an object")
    featured_events = featured.get("data", [])
    targets = [
        event
        for event in featured_events
        if event.get("home_team") == PROBE_HOME and event.get("away_team") == PROBE_AWAY
    ]
    target_summary: dict[str, Any]
    if len(targets) == 1:
        target = targets[0]
        target_summary = {
            "match_count": 1,
            "id": target.get("id"),
            "commence_time": target.get("commence_time"),
            "home_team": target.get("home_team"),
            "away_team": target.get("away_team"),
            **bookmaker_summary(target),
            "bookmakers_by_documented_region": classify_bookmakers(target),
        }
    else:
        target_summary = {"match_count": len(targets)}

    outright_results = []
    for sport_key in outright_sport_keys:
        payload = client.get(
            f"outrights probe {sport_key}",
            f"/historical/sports/{sport_key}/odds",
            {
                "regions": "us,eu",
                "markets": "outrights",
                "date": PROBE_DATE,
                "dateFormat": "iso",
                "oddsFormat": "decimal",
            },
            f"probe/outrights-{sport_key}.json.gz",
            estimated_cost=20,
            allowed_statuses=frozenset({200, 422}),
        )
        if not isinstance(payload, dict):
            raise RuntimeError(f"outrights response for {sport_key} is not an object")
        if "error_code" in payload:
            outright_results.append(
                {
                    "sport_key": sport_key,
                    "error": payload,
                }
            )
            continue
        events = payload.get("data", [])
        outright_results.append(
            {
                "sport_key": sport_key,
                **historical_summary(payload),
                "events": [
                    {
                        "id": event.get("id"),
                        "sport_title": event.get("sport_title"),
                        "commence_time": event.get("commence_time"),
                        "home_team": event.get("home_team"),
                        "away_team": event.get("away_team"),
                        **bookmaker_summary(event),
                    }
                    for event in events
                ],
            }
        )

    summary = {
        "requested_at": PROBE_DATE,
        "nhl_sports": nhl_sports,
        "featured": {
            **historical_summary(featured),
            "target": target_summary,
        },
        "outrights": outright_results,
        "calls": client.calls,
        "estimated_credits": client.estimated,
        "actual_credits": client.actual,
    }
    summary_path = scratch / "probe" / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Probe complete; summary={summary_path}; actual credits={client.actual}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    probe = subparsers.add_parser("probe")
    probe.add_argument(
        "--scratch",
        type=Path,
        default=Path(tempfile.gettempdir()) / "odds-history",
    )
    probe.add_argument("--max-credits", type=int, default=300)
    bulk = subparsers.add_parser("bulk")
    bulk.add_argument(
        "--scratch",
        type=Path,
        default=Path(tempfile.gettempdir()) / "odds-history",
    )
    bulk.add_argument("--max-credits", type=int, default=90_000)
    bulk.add_argument("--prior-credits", type=int, default=0)
    bulk.add_argument("--progress-every", type=int, default=25)
    bulk.add_argument("--delay", type=float, default=0.2)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.command == "probe":
            run_probe(args)
            return 0
        if args.command == "bulk":
            run_bulk(args)
            return 0
        raise RuntimeError(f"unsupported command: {args.command}")
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
