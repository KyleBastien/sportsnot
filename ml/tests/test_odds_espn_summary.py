"""ESPN summary odds tests."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from draft_oracle.ingest.odds import espn_summary_to_rows
from tests.odds_live_helpers import (
    _clear_pickcenter_favorite_flags,
    _espn_game_test_client,
    _espn_summary_payload,
)


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
    _clear_pickcenter_favorite_flags(pickcenter)

    row = espn_summary_to_rows(payload).iloc[0]

    assert row["favorite_side"] is None
    assert not bool(row["covered"])


def test_espn_summary_to_rows_omitted_spread_and_flags_is_unattributed() -> None:
    payload = _espn_summary_payload(favorite_home=True)
    pickcenter = payload["pickcenter"][0]
    del pickcenter["spread"]
    _clear_pickcenter_favorite_flags(pickcenter)

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

    client = _espn_game_test_client(tmp_path, handler)
    df = client.game_odds(401874176)
    assert len(df) == 1
    assert df.iloc[0]["favorite_side"] == "away"
    client.close()
