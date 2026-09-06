"""Exact NHL archive-to-Odds-API event matching and flat-row conversion."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from odds_archive_common import isoformat, parse_timestamp
from odds_history_models import MAX_START_DELTA, Game, RequestPlan


@dataclass(frozen=True)
class MatchResult:
    event: dict[str, Any] | None
    status: str
    delta_seconds: int | None


@dataclass(frozen=True)
class LineContext:
    plan: RequestPlan
    game: Game
    payload: dict[str, Any]
    event: dict[str, Any]


def _event_time_delta(event: dict[str, Any], game: Game) -> timedelta | None:
    value = event.get("commence_time")
    if not isinstance(value, str):
        return None
    try:
        return abs(parse_timestamp(value) - game.start)
    except (RuntimeError, ValueError):
        return None


def _unique_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    for event in events:
        if event not in unique:
            unique.append(event)
    return unique


def _match_status(candidate_count: int, unique_count: int) -> str:
    if candidate_count > unique_count:
        return "matched_after_identical_duplicate_dedup"
    if unique_count == 1:
        return "matched"
    return "matched_nearest_start"


def _timed_candidates(
    events: list[dict[str, Any]], game: Game
) -> list[tuple[timedelta, dict[str, Any]]]:
    timed = []
    for event in events:
        delta = _event_time_delta(event, game)
        if delta is not None and delta <= MAX_START_DELTA:
            timed.append((delta, event))
    return sorted(timed, key=lambda item: (item[0], str(item[1].get("id", ""))))


def _is_ambiguous(timed: list[tuple[timedelta, dict[str, Any]]]) -> bool:
    return len(timed) > 1 and timed[0][0] == timed[1][0]


def match_event(events: list[dict[str, Any]], game: Game) -> MatchResult:
    candidates = [
        event
        for event in events
        if event.get("home_team") == game.home_name and event.get("away_team") == game.away_name
    ]
    unique = _unique_events(candidates)
    timed = _timed_candidates(unique, game)
    if not timed:
        return MatchResult(None, "no_exact_team_and_time_match", None)
    best_delta, best_event = timed[0]
    if _is_ambiguous(timed):
        return MatchResult(None, "ambiguous_exact_team_and_time_match", None)
    status = _match_status(len(candidates), len(unique))
    return MatchResult(best_event, status, int(best_delta.total_seconds()))


def _bool_text(value: bool) -> str:
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
    match: MatchResult,
) -> dict[str, Any]:
    if match.event is None or match.delta_seconds is None:
        raise RuntimeError("cannot create matched index row from unmatched result")
    event = match.event
    bookmakers = event.get("bookmakers", [])
    market_keys = {
        str(market.get("key"))
        for bookmaker in bookmakers
        for market in bookmaker.get("markets", [])
    }
    row = blank_index_row(plan, game, match.status, str(payload["timestamp"]))
    row.update(
        {
            "eventId": event.get("id", ""),
            "commenceTime": event.get("commence_time", ""),
            "startTimeDeltaSeconds": match.delta_seconds,
            "apiHomeName": event.get("home_team", ""),
            "apiAwayName": event.get("away_team", ""),
            "bookmakerCount": len(bookmakers),
            "hasH2h": _bool_text("h2h" in market_keys),
            "hasSpreads": _bool_text("spreads" in market_keys),
            "hasTotals": _bool_text("totals" in market_keys),
        }
    )
    return row


def _line_row(
    context: LineContext,
    bookmaker: dict[str, Any],
    market: dict[str, Any],
    outcome: dict[str, Any],
) -> dict[str, Any]:
    return {
        "gameId": context.game.game_id,
        "gameTypeId": context.game.game_type_id,
        "gameDate": context.game.game_date,
        "requestedTimestamp": context.plan.requested_iso,
        "returnedSnapshotTimestamp": context.payload["timestamp"],
        "eventId": context.event.get("id", ""),
        "commenceTime": context.event.get("commence_time", ""),
        "archiveHomeAbbrev": context.game.home_abbrev,
        "archiveAwayAbbrev": context.game.away_abbrev,
        "bookmakerKey": bookmaker.get("key", ""),
        "bookmakerTitle": bookmaker.get("title", ""),
        "bookmakerLastUpdate": bookmaker.get("last_update", ""),
        "marketKey": market.get("key", ""),
        "marketLastUpdate": market.get("last_update", ""),
        "outcomeName": outcome.get("name", ""),
        "price": outcome.get("price", ""),
        "point": outcome.get("point", ""),
    }


def line_rows(
    plan: RequestPlan,
    game: Game,
    payload: dict[str, Any],
    event: dict[str, Any],
) -> list[dict[str, Any]]:
    context = LineContext(plan, game, payload, event)
    return [
        _line_row(context, bookmaker, market, outcome)
        for bookmaker in event.get("bookmakers", [])
        for market in bookmaker.get("markets", [])
        for outcome in market.get("outcomes", [])
    ]
