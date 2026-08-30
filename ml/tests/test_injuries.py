"""Unit tests for ESPN injury ingestion + manual overrides (US-008).

No test touches the network: an ``httpx.MockTransport`` serves recorded fixture
JSON and backoff sleeps are stubbed out (SPEC §7 — fixtures only). Coverage:
status normalization, override merge precedence, and source-failure fallback.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pandas as pd
import pytest

from draft_oracle.ingest.entity_match import build_player_index
from draft_oracle.ingest.injuries import (
    STATUS_DAY_TO_DAY,
    STATUS_HEALTHY,
    STATUS_IR,
    STATUS_OUT,
    EspnInjuriesClient,
    EspnInjuriesResponse,
    InjuryOverride,
    apply_overrides,
    build_injuries_table,
    injuries_response_to_rows,
    load_injury_overrides,
    normalize_status,
    resolve_espn_player_id,
)
from draft_oracle.ingest.nhl_api import NHLApiError
from draft_oracle.ingest.odds import resolve_team_id
from draft_oracle.projection_artifact import _injured_player_ids

FIXTURES = Path(__file__).parent / "fixtures" / "injuries"


def _load_feed() -> dict[str, object]:
    with (FIXTURES / "injuries_feed.json").open("r", encoding="utf-8") as handle:
        data: dict[str, object] = json.load(handle)
    return data


def _noop_sleep(_seconds: float) -> None:
    return None


def _feed_rows() -> pd.DataFrame:
    response = EspnInjuriesResponse.model_validate(_load_feed())
    return injuries_response_to_rows(response)


# ── Status normalization ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("status_raw", "type_name", "expected"),
    [
        ("Out", "INJURY_STATUS_OUT", STATUS_OUT),
        ("Out", None, STATUS_OUT),
        ("Suspension", None, STATUS_OUT),
        ("Injured Reserve", "INJURY_STATUS_INJURED_RESERVE", STATUS_IR),
        ("IR", None, STATUS_IR),
        ("Long Term Injured Reserve", None, STATUS_IR),
        ("Day-To-Day", "INJURY_STATUS_DAY_TO_DAY", STATUS_DAY_TO_DAY),
        ("Day To Day", None, STATUS_DAY_TO_DAY),
        ("Questionable", None, STATUS_DAY_TO_DAY),
        ("GTD", None, STATUS_DAY_TO_DAY),
        ("Active", "INJURY_STATUS_ACTIVE", STATUS_HEALTHY),
        ("Healthy", None, STATUS_HEALTHY),
        ("", None, STATUS_HEALTHY),
        (None, None, STATUS_HEALTHY),
    ],
)
def test_normalize_status(status_raw: str | None, type_name: str | None, expected: str) -> None:
    assert normalize_status(status_raw, type_name) == expected


def test_normalize_status_type_name_wins_over_text() -> None:
    # The explicit type name is authoritative even when the free text disagrees.
    assert normalize_status("healthy scratch", "INJURY_STATUS_OUT") == STATUS_OUT


def test_normalize_status_unknown_nonempty_is_day_to_day() -> None:
    assert normalize_status("Mystery", None) == STATUS_DAY_TO_DAY


# ── Feed → normalized rows ───────────────────────────────────────────────


def test_feed_rows_parse_and_resolve_team_and_position() -> None:
    df = _feed_rows()
    assert len(df) == 3
    carlo = df[df["player_id"] == 3904175].iloc[0]
    assert carlo["player_name"] == "Brandon Carlo"
    assert carlo["position"] == "D"
    assert carlo["team_id"] == resolve_team_id("Boston Bruins")
    assert carlo["team_abbrev"] == "BOS"
    assert carlo["status"] == STATUS_OUT
    assert carlo["return_date"] == "2026-05-01"
    assert carlo["detail"] == "Lower Body"
    assert carlo["source"] == "espn"

    draisaitl = df[df["player_id"] == 8477934].iloc[0]
    assert draisaitl["status"] == STATUS_IR
    assert draisaitl["team_id"] == resolve_team_id("Edmonton Oilers")


def test_feed_rows_skip_entries_without_athlete_id() -> None:
    feed = {
        "injuries": [
            {
                "displayName": "Boston Bruins",
                "injuries": [{"status": "Out", "athlete": {"fullName": "Nameless"}}],
            }
        ]
    }
    df = injuries_response_to_rows(EspnInjuriesResponse.model_validate(feed))
    assert df.empty


# ── Override merge precedence (final authority) ──────────────────────────


def test_override_by_espn_id_rewrites_row() -> None:
    df = _feed_rows()
    overrides = [
        InjuryOverride(player="Brandon Carlo", espn_id=3904175, status=STATUS_HEALTHY, remove=True)
    ]
    # remove wins -> Carlo dropped
    merged = apply_overrides(df, overrides)
    assert 3904175 not in set(merged["player_id"])


def test_override_by_espn_id_updates_status_and_return() -> None:
    df = _feed_rows()
    overrides = [InjuryOverride(espn_id=4233563, status=STATUS_OUT, return_date="2026-06-01")]
    merged = apply_overrides(df, overrides)
    row = merged[merged["player_id"] == 4233563].iloc[0]
    assert row["status"] == STATUS_OUT
    assert row["return_date"] == "2026-06-01"
    assert row["source"] == "override"


def test_override_by_name_matches_accent_insensitive() -> None:
    df = _feed_rows()
    overrides = [InjuryOverride(player="brandon carlo", status=STATUS_DAY_TO_DAY)]
    merged = apply_overrides(df, overrides)
    row = merged[merged["player_id"] == 3904175].iloc[0]
    assert row["status"] == STATUS_DAY_TO_DAY
    assert row["source"] == "override"


def test_unmatched_override_is_injected_as_new_row() -> None:
    df = _feed_rows()
    overrides = [
        InjuryOverride(
            player="Connor McDavid",
            espn_id=8478402,
            status=STATUS_OUT,
            team="Edmonton Oilers",
            return_date="2026-05-10",
        )
    ]
    merged = apply_overrides(df, overrides)
    assert len(merged) == 4
    row = merged[merged["player_id"] == 8478402].iloc[0]
    assert row["player_name"] == "Connor McDavid"
    assert row["status"] == STATUS_OUT
    assert row["team_id"] == resolve_team_id("Edmonton Oilers")
    assert row["source"] == "override"


def test_override_precedence_espn_id_over_name() -> None:
    # espn_id targets a different player than the name -> id wins.
    df = _feed_rows()
    overrides = [InjuryOverride(player="Jeremy Swayman", espn_id=8477934, status=STATUS_OUT)]
    merged = apply_overrides(df, overrides)
    # Draisaitl (id 8477934) got overridden, not Swayman.
    assert merged[merged["player_id"] == 8477934].iloc[0]["status"] == STATUS_OUT
    assert merged[merged["player_id"] == 4233563].iloc[0]["status"] == STATUS_DAY_TO_DAY


def test_load_injury_overrides_missing_file_is_empty(tmp_path: Path) -> None:
    assert load_injury_overrides(tmp_path / "nope.yaml") == []


def test_load_injury_overrides_parses_and_normalizes(tmp_path: Path) -> None:
    path = tmp_path / "injuries.yaml"
    path.write_text(
        "overrides:\n"
        "  - player: Connor McDavid\n"
        "    espn_id: 8478402\n"
        "    status: Out\n"
        "    return_date: '2026-05-10'\n",
        encoding="utf-8",
    )
    overrides = load_injury_overrides(path)
    assert len(overrides) == 1
    assert overrides[0].espn_id == 8478402
    assert overrides[0].status == STATUS_OUT  # normalized from "Out"


# ── Client (MockTransport, no network) ───────────────────────────────────


def test_client_fetches_and_caches(tmp_path: Path) -> None:
    calls = [0]

    def handler(request: httpx.Request) -> httpx.Response:
        calls[0] += 1
        assert request.url.path.endswith("/injuries")
        return httpx.Response(200, json=_load_feed())

    client = EspnInjuriesClient(
        cache_dir=tmp_path / "cache",
        delay=0.0,
        retry_backoff=0.0,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=_noop_sleep,
    )
    first = client.injuries()
    assert len(first.injuries) == 2
    client.injuries()  # served from cache
    assert calls[0] == 1
    client.close()


def test_client_raises_loudly_on_persistent_failure(tmp_path: Path) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "unavailable"})

    client = EspnInjuriesClient(
        cache_dir=tmp_path / "cache",
        delay=0.0,
        retry_backoff=0.0,
        max_attempts=2,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=_noop_sleep,
    )
    with client, pytest.raises(NHLApiError):
        client.injuries()


# ── build_injuries_table: end-to-end + graceful degradation ──────────────


def _live_client(tmp_path: Path) -> EspnInjuriesClient:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_load_feed())

    return EspnInjuriesClient(
        cache_dir=tmp_path / "cache",
        delay=0.0,
        retry_backoff=0.0,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=_noop_sleep,
    )


def _failing_client(tmp_path: Path) -> EspnInjuriesClient:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    return EspnInjuriesClient(
        cache_dir=tmp_path / "cache",
        delay=0.0,
        retry_backoff=0.0,
        max_attempts=2,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=_noop_sleep,
    )


def test_build_writes_table_and_merges_overrides(tmp_path: Path) -> None:
    overrides_path = tmp_path / "injuries.yaml"
    overrides_path.write_text(
        "overrides:\n  - player: Brandon Carlo\n    status: healthy\n    remove: true\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "normalized"
    result = build_injuries_table(
        client=_live_client(tmp_path),
        overrides_path=overrides_path,
        out_dir=out_dir,
    )
    assert not result.degraded
    assert result.source_rows == 3
    assert result.total_rows == 2  # Carlo removed by override
    df = pd.read_parquet(out_dir / "injuries.parquet")
    assert 3904175 not in set(df["player_id"])


def test_build_degrades_to_last_known_on_source_failure(tmp_path: Path) -> None:
    overrides_path = tmp_path / "injuries.yaml"
    overrides_path.write_text("overrides: []\n", encoding="utf-8")
    out_dir = tmp_path / "normalized"

    # First, a successful run seeds injuries.parquet (the last-known table).
    ok = build_injuries_table(
        client=_live_client(tmp_path),
        overrides_path=overrides_path,
        out_dir=out_dir,
    )
    assert ok.total_rows == 3

    # Now the source fails: pipeline continues on last-known data + a warning.
    degraded = build_injuries_table(
        client=_failing_client(tmp_path / "cache2"),
        overrides_path=overrides_path,
        out_dir=out_dir,
    )
    assert degraded.degraded
    assert degraded.total_rows == 3
    assert any("failed" in w for w in degraded.warnings)
    df = pd.read_parquet(out_dir / "injuries.parquet")
    # Live rows are relabeled "last_known" when reused after a failure.
    assert set(df["source"]) == {"last_known"}


def test_build_no_fetch_uses_last_known_without_degraded_flag(tmp_path: Path) -> None:
    overrides_path = tmp_path / "injuries.yaml"
    overrides_path.write_text("overrides: []\n", encoding="utf-8")
    out_dir = tmp_path / "normalized"
    build_injuries_table(
        client=_live_client(tmp_path), overrides_path=overrides_path, out_dir=out_dir
    )

    offline = build_injuries_table(overrides_path=overrides_path, out_dir=out_dir, fetch=False)
    assert not offline.degraded
    assert offline.total_rows == 3
    assert any("fetch disabled" in w for w in offline.warnings)


def test_build_empty_start_when_no_source_and_no_last_known(tmp_path: Path) -> None:
    out_dir = tmp_path / "normalized"
    result = build_injuries_table(
        overrides_path=tmp_path / "missing.yaml", out_dir=out_dir, fetch=False
    )
    assert result.total_rows == 0
    assert (out_dir / "injuries.parquet").is_file()


# ── ESPN athlete id -> NHL player id mapping (CODE_REVIEW M-11) ───────────


def _nhl_players() -> pd.DataFrame:
    """Realistic players dimension: NHL ids in the 8.4M+ range, name+team+position.

    Includes a genuine same-name collision (two ``Sebastian Aho``) so the team +
    position disambiguation is exercised, mirroring the archive.
    """
    return pd.DataFrame(
        [
            # NHL ids live in [8.4M, 8.5M]; ESPN athlete ids are ~4-5M (disjoint).
            {"player_id": 8478443, "player_name": "Brandon Carlo", "position": "D",
             "current_team_abbrev": "BOS"},
            {"player_id": 8477934, "player_name": "Leon Draisaitl", "position": "F",
             "current_team_abbrev": "EDM"},
            # Two Sebastian Aho: a CAR forward and a NYI defenseman.
            {"player_id": 8478427, "player_name": "Sebastian Aho", "position": "F",
             "current_team_abbrev": "CAR"},
            {"player_id": 8480222, "player_name": "Sebastian Aho", "position": "D",
             "current_team_abbrev": "NYI"},
        ]
    )


def _mapping_feed() -> dict[str, object]:
    """ESPN feed keyed on ~4-5M athlete ids that must map to 8.4M+ NHL ids."""
    return {
        "injuries": [
            {
                "id": "6",
                "displayName": "Boston Bruins",
                "abbreviation": "BOS",
                "injuries": [
                    {
                        "status": "Out",
                        "athlete": {
                            "id": "3904175",  # ESPN id, disjoint from NHL 8478443
                            "fullName": "Brandon Carlo",
                            "position": {"abbreviation": "D"},
                        },
                        "type": {"name": "INJURY_STATUS_OUT"},
                        "details": {"type": "Lower Body", "returnDate": "2026-05-01"},
                    }
                ],
            },
            {
                "id": "12",
                "displayName": "Carolina Hurricanes",
                "abbreviation": "CAR",
                "injuries": [
                    {
                        "status": "Injured Reserve",
                        "athlete": {
                            "id": "4197149",  # ESPN id for the CAR Sebastian Aho
                            "fullName": "Sebastian Aho",
                            "position": {"abbreviation": "C"},
                        },
                        "type": {"name": "INJURY_STATUS_INJURED_RESERVE"},
                        "details": {"type": "Upper Body", "returnDate": None},
                    }
                ],
            },
        ]
    }


def test_resolve_espn_player_id_maps_disjoint_id_ranges() -> None:
    players = _nhl_players()
    index = build_player_index(players[players["position"].isin(("F", "D"))])
    team_by_id = {
        int(rec["player_id"]): rec["current_team_abbrev"]
        for rec in players.to_dict("records")
    }
    # Carlo: exact name, unique -> NHL id (not the ESPN 3904175).
    carlo = resolve_espn_player_id("Brandon Carlo", "BOS", "D", index, team_by_id)
    assert carlo.player_id == 8478443
    # Same-name collision disambiguated by team -> the CAR forward, not NYI D.
    aho = resolve_espn_player_id("Sebastian Aho", "CAR", "C", index, team_by_id)
    assert aho.player_id == 8478427
    assert aho.method == "team"


def test_resolve_espn_player_id_goalie_and_unresolved_are_not_guessed() -> None:
    players = _nhl_players()
    index = build_player_index(players[players["position"].isin(("F", "D"))])
    team_by_id = {
        int(rec["player_id"]): rec["current_team_abbrev"]
        for rec in players.to_dict("records")
    }
    goalie = resolve_espn_player_id("Somebody", "BOS", "G", index, team_by_id)
    assert goalie.player_id is None and goalie.method == "goalie"
    unknown = resolve_espn_player_id("Nobody Here", "BOS", "F", index, team_by_id)
    assert unknown.player_id is None and unknown.method == "unresolved"


def test_feed_rows_resolve_to_nhl_ids_and_preserve_espn_id() -> None:
    df = injuries_response_to_rows(
        EspnInjuriesResponse.model_validate(_mapping_feed()), players=_nhl_players()
    )
    carlo = df[df["espn_id"] == 3904175].iloc[0]
    assert carlo["player_id"] == 8478443  # mapped NHL id
    assert carlo["player_name"] == "Brandon Carlo"
    aho = df[df["espn_id"] == 4197149].iloc[0]
    assert aho["player_id"] == 8478427  # CAR forward, disambiguated by team
    # The disjoint ESPN ids no longer leak into the join key.
    assert 3904175 not in set(df["player_id"])
    assert 4197149 not in set(df["player_id"])


def test_injured_flag_join_fires_on_mapped_ids_not_espn_ids() -> None:
    # Failing-then-passing: unmapped ESPN ids never intersect NHL skater ids.
    unmapped = injuries_response_to_rows(EspnInjuriesResponse.model_validate(_mapping_feed()))
    assert _injured_player_ids(unmapped) == {3904175, 4197149}

    mapped = injuries_response_to_rows(
        EspnInjuriesResponse.model_validate(_mapping_feed()), players=_nhl_players()
    )
    injured = _injured_player_ids(mapped)
    # The mapped NHL ids now join; the raw ESPN ids are gone.
    assert 8478443 in injured  # Brandon Carlo (NHL)
    assert 8478427 in injured  # Sebastian Aho, CAR (NHL)
    assert not ({3904175, 4197149} & injured)


def test_unresolved_espn_ids_are_kept_and_reported() -> None:
    feed = {
        "injuries": [
            {
                "displayName": "Boston Bruins",
                "abbreviation": "BOS",
                "injuries": [
                    {
                        "status": "Out",
                        "athlete": {
                            "id": "4999999",
                            "fullName": "Phantom Skater",
                            "position": {"abbreviation": "C"},
                        },
                        "type": {"name": "INJURY_STATUS_OUT"},
                    }
                ],
            }
        ]
    }
    df = injuries_response_to_rows(
        EspnInjuriesResponse.model_validate(feed), players=_nhl_players()
    )
    # Unresolved skater is KEPT (never dropped), keyed on its ESPN id, and reported.
    assert len(df) == 1
    assert df.iloc[0]["player_id"] == 4999999
    assert df.attrs["unresolved_espn_ids"] == [4999999]


def test_override_keys_on_nhl_player_id(tmp_path: Path) -> None:
    df = injuries_response_to_rows(
        EspnInjuriesResponse.model_validate(_mapping_feed()), players=_nhl_players()
    )
    overrides = [InjuryOverride(player_id=8478443, status=STATUS_DAY_TO_DAY)]
    merged = apply_overrides(df, overrides)
    row = merged[merged["player_id"] == 8478443].iloc[0]
    assert row["status"] == STATUS_DAY_TO_DAY
    assert row["source"] == "override"


def test_build_reports_unresolved_and_maps_with_players(tmp_path: Path) -> None:
    out_dir = tmp_path / "normalized"
    out_dir.mkdir()
    _nhl_players().to_parquet(out_dir / "players.parquet", index=False)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_mapping_feed())

    client = EspnInjuriesClient(
        cache_dir=tmp_path / "cache",
        delay=0.0,
        retry_backoff=0.0,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=_noop_sleep,
    )
    result = build_injuries_table(
        client=client, overrides_path=tmp_path / "none.yaml", out_dir=out_dir
    )
    assert result.unresolved_player_ids == []
    saved = pd.read_parquet(out_dir / "injuries.parquet")
    assert 8478443 in set(saved["player_id"])
    assert 3904175 in set(saved["espn_id"])
