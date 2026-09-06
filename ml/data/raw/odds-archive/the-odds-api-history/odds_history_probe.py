"""Bounded NHL feature and outright probes for The Odds API history."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from odds_bookmakers import EU_BOOKMAKERS, US_BOOKMAKERS
from odds_history_client import Client
from odds_history_models import ApiRequest

PROBE_DATE = "2024-04-20T20:00:00Z"
PROBE_HOME = "Carolina Hurricanes"
PROBE_AWAY = "New York Islanders"


def _bookmaker_summary(event: dict[str, Any]) -> dict[str, Any]:
    bookmakers = event.get("bookmakers", [])
    summaries = [
        {
            "key": bookmaker.get("key"),
            "title": bookmaker.get("title"),
            "markets": [market.get("key") for market in bookmaker.get("markets", [])],
            "outcome_counts": {
                str(market.get("key")): len(market.get("outcomes", []))
                for market in bookmaker.get("markets", [])
            },
        }
        for bookmaker in bookmakers
    ]
    return {"count": len(bookmakers), "bookmakers": summaries}


def _bookmaker_regions(event: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {"us": [], "eu": [], "unclassified": []}
    for bookmaker in event.get("bookmakers", []):
        _classify_bookmaker(grouped, bookmaker)
    return grouped


def _classify_bookmaker(
    grouped: dict[str, list[dict[str, Any]]], bookmaker: dict[str, Any]
) -> None:
    item = {"key": bookmaker.get("key"), "title": bookmaker.get("title")}
    key = str(bookmaker.get("key"))
    regions = [
        region
        for region, catalog in (("us", US_BOOKMAKERS), ("eu", EU_BOOKMAKERS))
        if key in catalog
    ]
    if not regions:
        grouped["unclassified"].append(item)
        return
    for region in regions:
        grouped[region].append(item)


def _historical_summary(payload: dict[str, Any]) -> dict[str, Any]:
    events = payload.get("data", [])
    if not isinstance(events, list):
        raise RuntimeError("historical response data is not a list")
    keys = {
        str(bookmaker.get("key")) for event in events for bookmaker in event.get("bookmakers", [])
    }
    return {
        "timestamp": payload.get("timestamp"),
        "previous_timestamp": payload.get("previous_timestamp"),
        "next_timestamp": payload.get("next_timestamp"),
        "event_count": len(events),
        "bookmaker_entries": sum(len(event.get("bookmakers", [])) for event in events),
        "unique_bookmaker_keys": sorted(keys),
    }


def _nhl_sports(sports: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            "key": sport.get("key"),
            "title": sport.get("title"),
            "active": sport.get("active"),
            "has_outrights": sport.get("has_outrights"),
        }
        for sport in sports
        if isinstance(sport, dict) and "icehockey_nhl" in str(sport.get("key", ""))
    ]


def _target_summary(events: list[dict[str, Any]]) -> dict[str, Any]:
    targets = [
        event
        for event in events
        if event.get("home_team") == PROBE_HOME and event.get("away_team") == PROBE_AWAY
    ]
    if len(targets) != 1:
        return {"match_count": len(targets)}
    target = targets[0]
    return {
        "match_count": 1,
        "id": target.get("id"),
        "commence_time": target.get("commence_time"),
        "home_team": target.get("home_team"),
        "away_team": target.get("away_team"),
        **_bookmaker_summary(target),
        "bookmakers_by_documented_region": _bookmaker_regions(target),
    }


def _outright_keys(sports: list[dict[str, Any]]) -> list[str]:
    extra = [
        str(sport["key"])
        for sport in sports
        if sport.get("has_outrights") and sport.get("key") != "icehockey_nhl"
    ]
    return ["icehockey_nhl", *extra]


def _outright_event(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": event.get("id"),
        "sport_title": event.get("sport_title"),
        "commence_time": event.get("commence_time"),
        "home_team": event.get("home_team"),
        "away_team": event.get("away_team"),
        **_bookmaker_summary(event),
    }


def _outright_result(sport_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    if "error_code" in payload:
        return {"sport_key": sport_key, "error": payload}
    events = payload.get("data", [])
    return {
        "sport_key": sport_key,
        **_historical_summary(payload),
        "events": [_outright_event(event) for event in events],
    }


def _fetch_outrights(client: Client, sport_keys: list[str]) -> list[dict[str, Any]]:
    results = []
    for sport_key in sport_keys:
        payload = client.get(
            ApiRequest(
                label=f"outrights probe {sport_key}",
                path=f"/historical/sports/{sport_key}/odds",
                params={
                    "regions": "us,eu",
                    "markets": "outrights",
                    "date": PROBE_DATE,
                    "dateFormat": "iso",
                    "oddsFormat": "decimal",
                },
                output_name=f"probe/outrights-{sport_key}.json.gz",
                estimated_cost=20,
                allowed_statuses=frozenset({200, 422}),
            )
        )
        if not isinstance(payload, dict):
            raise RuntimeError(f"outrights response for {sport_key} is not an object")
        results.append(_outright_result(sport_key, payload))
    return results


def run_probe(client: Client, scratch: Path, max_credits: int) -> None:
    sports = client.get(ApiRequest("sports", "/sports", {"all": "true"}, "probe/sports.json.gz", 0))
    if not isinstance(sports, list):
        raise RuntimeError("sports response is not a list")
    nhl_sports = _nhl_sports(sports)
    outright_keys = _outright_keys(nhl_sports)
    paid_estimate = 60 + 20 * len(outright_keys)
    print(
        f"Probe paid-call worst-case estimate: 60 + 20 x {len(outright_keys)} "
        f"= {paid_estimate} credits (cap {max_credits})",
        flush=True,
    )
    if paid_estimate > max_credits:
        raise RuntimeError("probe estimate exceeds cap")
    featured = _fetch_featured(client)
    summary = {
        "requested_at": PROBE_DATE,
        "nhl_sports": nhl_sports,
        "featured": {
            **_historical_summary(featured),
            "target": _target_summary(featured.get("data", [])),
        },
        "outrights": _fetch_outrights(client, outright_keys),
        "calls": client.calls,
        "estimated_credits": client.estimated,
        "actual_credits": client.actual,
    }
    summary_path = scratch / "probe" / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Probe complete; summary={summary_path}; actual credits={client.actual}")


def _fetch_featured(client: Client) -> dict[str, Any]:
    payload = client.get(
        ApiRequest(
            label="featured-markets probe",
            path="/historical/sports/icehockey_nhl/odds",
            params={
                "regions": "us,eu",
                "markets": "h2h,spreads,totals",
                "date": PROBE_DATE,
                "dateFormat": "iso",
                "oddsFormat": "decimal",
            },
            output_name="probe/featured.json.gz",
            estimated_cost=60,
        )
    )
    if not isinstance(payload, dict):
        raise RuntimeError("featured response is not an object")
    return payload
