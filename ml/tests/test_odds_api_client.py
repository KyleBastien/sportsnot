"""Odds API client tests."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from draft_oracle.ingest.nhl_api import NHLApiError
from draft_oracle.ingest.odds import OddsApiEvent as _OddsApiEvent
from draft_oracle.ingest.odds import odds_api_events_to_rows, resolve_team_id
from tests.odds_live_helpers import _odds_api_payload, _odds_api_test_client


def test_odds_api_client_fetches_and_captures_quota(tmp_path: Path) -> None:
    calls: list[int] = [0]

    def handler(request: httpx.Request) -> httpx.Response:
        calls[0] += 1
        assert "apiKey=secret" in str(request.url)
        return httpx.Response(
            200,
            json=_odds_api_payload(),
            headers={"x-requests-remaining": "480", "x-requests-used": "20"},
        )

    client = _odds_api_test_client(tmp_path, handler, api_key="secret")
    events = client.nhl_odds()
    assert len(events) == 1
    assert client.requests_remaining == 480
    assert client.requests_used == 20
    client.nhl_odds()
    assert calls[0] == 1
    client.close()


def test_odds_api_client_requires_key(tmp_path: Path) -> None:
    client = _odds_api_test_client(
        tmp_path, lambda _request: httpx.Response(200, json=[]), api_key=""
    )
    with pytest.raises(NHLApiError):
        client.nhl_odds()
    client.close()


def test_odds_api_events_to_rows_devigs() -> None:
    events = [_OddsApiEvent.model_validate(item) for item in _odds_api_payload()]
    df = odds_api_events_to_rows(events)
    assert len(df) == 1
    row = df.iloc[0]
    assert bool(row["both_sides"])
    assert row["home_team_id"] == resolve_team_id("Carolina Hurricanes")
    assert row["home_implied"] + row["away_implied"] == pytest.approx(1.0, abs=1e-9)
    assert row["favorite_side"] == "home"


def test_odds_api_events_missing_market_flagged() -> None:
    payload = _odds_api_payload()
    payload[0]["bookmakers"] = []
    events = [_OddsApiEvent.model_validate(item) for item in payload]
    df = odds_api_events_to_rows(events)
    assert len(df) == 1
    assert not bool(df.iloc[0]["covered"])
