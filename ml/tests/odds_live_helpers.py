"""Shared live-odds test fixtures."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

from draft_oracle.ingest.odds import EspnGameOddsClient, OddsApiClient


def _noop_sleep(_seconds: float) -> None:
    return None


def _odds_api_payload() -> list[dict[str, object]]:
    return [
        {
            "id": "evt1",
            "commence_time": "2026-05-01T23:00:00Z",
            "home_team": "Carolina Hurricanes",
            "away_team": "Vegas Golden Knights",
            "bookmakers": [
                {
                    "key": "draftkings",
                    "markets": [
                        {
                            "key": "h2h",
                            "outcomes": [
                                {"name": "Carolina Hurricanes", "price": -160},
                                {"name": "Vegas Golden Knights", "price": 140},
                            ],
                        }
                    ],
                }
            ],
        }
    ]


def _odds_api_test_client(
    tmp_path: Path,
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    api_key: str,
) -> OddsApiClient:
    return OddsApiClient(
        cache_dir=tmp_path / "cache",
        api_key=api_key,
        delay=0.0,
        retry_backoff=0.0,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=_noop_sleep,
    )


def _espn_summary_payload(favorite_home: bool) -> dict[str, Any]:
    spread = -1.5 if favorite_home else 1.5
    return {
        "header": {
            "competitions": [
                {
                    "date": "2026-05-01T23:00:00Z",
                    "competitors": [
                        {"homeAway": "home", "team": {"displayName": "Carolina Hurricanes"}},
                        {"homeAway": "away", "team": {"displayName": "Vegas Golden Knights"}},
                    ],
                }
            ]
        },
        "pickcenter": [
            {
                "spread": spread,
                "homeTeamOdds": {"favorite": favorite_home, "moneyLine": -160},
                "awayTeamOdds": {"favorite": not favorite_home, "moneyLine": -160},
            }
        ],
    }


def _clear_pickcenter_favorite_flags(pickcenter: dict[str, Any]) -> None:
    pickcenter["homeTeamOdds"]["favorite"] = False
    pickcenter["awayTeamOdds"]["favorite"] = False
    pickcenter["moneyLine"] = -160


def _espn_game_test_client(
    tmp_path: Path, handler: Callable[[httpx.Request], httpx.Response]
) -> EspnGameOddsClient:
    return EspnGameOddsClient(
        cache_dir=tmp_path / "cache",
        delay=0.0,
        retry_backoff=0.0,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=_noop_sleep,
    )
