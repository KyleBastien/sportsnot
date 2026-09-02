"""Odds table build and live-client tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pandas as pd
import pytest

from draft_oracle.ingest.nhl_api import NHLApiError
from draft_oracle.ingest.odds import (
    EspnGameOddsClient,
    OddsApiClient,
    build_odds_table,
    espn_summary_to_rows,
    odds_api_events_to_rows,
    resolve_team_id,
)
from draft_oracle.ingest.odds import OddsApiEvent as _OddsApiEvent
from tests.test_odds import _favorite_csv, _write_sbr_workbook

# ── build_odds_table (Parquet round-trip) ────────────────────────────────


def test_build_odds_table_writes_parquet(tmp_path: Path) -> None:
    archive = tmp_path / "odds-archive"
    archive.mkdir()
    _write_sbr_workbook(
        archive / "nhl-odds-2016-17.xlsx",
        [
            [1012, 1, "V", "Toronto", 2, 2, 0, 4, 114, 121, 1.5, -245, 5.5, -110, 5.5, 105],
            [1012, 2, "H", "Ottawa", 2, 1, 1, 5, -134, -141, -1.5, 205, 5.5, -110, 5.5, -125],
        ],
    )
    out = tmp_path / "normalized"
    result = build_odds_table(archive_dir=archive, out_dir=out)
    assert result.game_rows == 1
    assert result.covered_rows == 1
    assert (out / "odds.parquet").exists()
    assert (out / "odds_by_source.parquet").exists()
    loaded = pd.read_parquet(out / "odds.parquet")
    assert len(loaded) == 1
    assert loaded.iloc[0]["home_team_id"] == resolve_team_id("Ottawa")


def test_build_odds_table_reports_unattributed_rows(tmp_path: Path) -> None:
    archive = tmp_path / "odds-archive"
    completion = archive / "espn-2025-26-completion"
    completion.mkdir(parents=True)
    frame = _favorite_csv(
        [
            {
                "game_id": 401874176,
                "date": "2026-06-15 00:00:00+00:00",
                "season": 2026,
                "team_name": "Vegas Golden Knights",
                "is_home": 1,
                "spread": float("nan"),
                "favorite_moneyline": -115,
            },
            {
                "game_id": 401874176,
                "date": "2026-06-15 00:00:00+00:00",
                "season": 2026,
                "team_name": "Carolina Hurricanes",
                "is_home": 0,
                "spread": float("nan"),
                "favorite_moneyline": -115,
            },
        ]
    )
    frame.to_csv(completion / "games.csv", index=False)

    result = build_odds_table(archive_dir=archive, out_dir=tmp_path / "normalized")

    assert result.unattributed_uncovered_rows == 1


# ── Live: The Odds API (MockTransport, no network) ───────────────────────


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

    client = OddsApiClient(
        cache_dir=tmp_path / "cache",
        api_key="secret",
        delay=0.0,
        retry_backoff=0.0,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=_noop_sleep,
    )
    events = client.nhl_odds()
    assert len(events) == 1
    assert client.requests_remaining == 480
    assert client.requests_used == 20
    # Second call is served from cache -> no extra network hit.
    client.nhl_odds()
    assert calls[0] == 1
    client.close()


def test_odds_api_client_requires_key(tmp_path: Path) -> None:
    client = OddsApiClient(
        cache_dir=tmp_path / "cache",
        api_key="",
        delay=0.0,
        client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=[]))),
        sleep=_noop_sleep,
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
    payload[0]["bookmakers"] = []  # no prices
    events = [_OddsApiEvent.model_validate(item) for item in payload]
    df = odds_api_events_to_rows(events)
    assert len(df) == 1
    assert not bool(df.iloc[0]["covered"])  # flagged, not imputed


# ── Live: ESPN summary (MockTransport + payload conversion) ──────────────


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


def test_espn_summary_to_rows_home_favorite() -> None:
    df = espn_summary_to_rows(_espn_summary_payload(favorite_home=True))
    assert len(df) == 1
    row = df.iloc[0]
    assert row["favorite_side"] == "home"
    assert not bool(row["both_sides"])
    assert row["home_implied"] > row["away_implied"]


def test_espn_summary_to_rows_missing_pickcenter_flagged() -> None:
    payload = _espn_summary_payload(favorite_home=True)
    payload["pickcenter"] = []
    df = espn_summary_to_rows(payload)
    assert len(df) == 1
    assert not bool(df.iloc[0]["covered"])


@pytest.mark.parametrize("spread", [None, ""])
def test_espn_summary_to_rows_missing_spread_and_flags_is_unattributed(
    spread: object,
) -> None:
    payload = _espn_summary_payload(favorite_home=True)
    pickcenter = payload["pickcenter"][0]
    pickcenter["spread"] = spread
    pickcenter["homeTeamOdds"]["favorite"] = False
    pickcenter["awayTeamOdds"]["favorite"] = False
    pickcenter["moneyLine"] = -160

    row = espn_summary_to_rows(payload).iloc[0]

    assert row["favorite_side"] is None
    assert not bool(row["covered"])


def test_espn_summary_to_rows_omitted_spread_and_flags_is_unattributed() -> None:
    payload = _espn_summary_payload(favorite_home=True)
    pickcenter = payload["pickcenter"][0]
    del pickcenter["spread"]
    pickcenter["homeTeamOdds"]["favorite"] = False
    pickcenter["awayTeamOdds"]["favorite"] = False
    pickcenter["moneyLine"] = -160

    row = espn_summary_to_rows(payload).iloc[0]

    assert row["favorite_side"] is None
    assert not bool(row["covered"])


def test_espn_summary_to_rows_favorite_flag_overrides_spread() -> None:
    payload = _espn_summary_payload(favorite_home=True)
    pickcenter = payload["pickcenter"][0]
    pickcenter["spread"] = 1.5

    row = espn_summary_to_rows(payload).iloc[0]

    assert row["favorite_side"] == "home"
    assert bool(row["covered"])


def test_espn_game_odds_client_uses_transport(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/summary")
        return httpx.Response(200, json=_espn_summary_payload(favorite_home=False))

    client = EspnGameOddsClient(
        cache_dir=tmp_path / "cache",
        delay=0.0,
        retry_backoff=0.0,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=_noop_sleep,
    )
    df = client.game_odds(401874176)
    assert len(df) == 1
    assert df.iloc[0]["favorite_side"] == "away"
    client.close()
