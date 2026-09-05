"""ESPN athlete to NHL player-id injury mapping tests."""

from __future__ import annotations

from pathlib import Path

import httpx
import pandas as pd

from draft_oracle.ingest.entity_match import build_player_index
from draft_oracle.ingest.injuries import (
    STATUS_DAY_TO_DAY,
    EspnInjuriesClient,
    EspnInjuriesClientRuntime,
    EspnInjuriesResponse,
    EspnPlayerIdRequest,
    InjuryOverride,
    apply_overrides,
    build_injuries_table,
    injuries_response_to_rows,
    resolve_espn_player_id,
)
from tests.test_injuries import _noop_sleep

_INJURED_STATUSES = frozenset({"out", "ir", "day_to_day"})


def _injured_player_ids(injuries: pd.DataFrame | None) -> set[int]:
    if injuries is None or injuries.empty:
        return set()
    hurt = injuries.loc[
        injuries["status"].isin(_INJURED_STATUSES) & (injuries["position"] != "G")
    ]
    return {int(pid) for pid in hurt["player_id"].tolist()}

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
    carlo = resolve_espn_player_id(
        EspnPlayerIdRequest("Brandon Carlo", "BOS", "D"),
        index,
        team_by_id,
    )
    assert carlo.player_id == 8478443
    # Same-name collision disambiguated by team -> the CAR forward, not NYI D.
    aho = resolve_espn_player_id(
        EspnPlayerIdRequest("Sebastian Aho", "CAR", "C"),
        index,
        team_by_id,
    )
    assert aho.player_id == 8478427
    assert aho.method == "team"


def test_resolve_espn_player_id_goalie_and_unresolved_are_not_guessed() -> None:
    players = _nhl_players()
    index = build_player_index(players[players["position"].isin(("F", "D"))])
    team_by_id = {
        int(rec["player_id"]): rec["current_team_abbrev"]
        for rec in players.to_dict("records")
    }
    goalie = resolve_espn_player_id(
        EspnPlayerIdRequest("Somebody", "BOS", "G"),
        index,
        team_by_id,
    )
    assert goalie.player_id is None and goalie.method == "goalie"
    unknown = resolve_espn_player_id(
        EspnPlayerIdRequest("Nobody Here", "BOS", "F"),
        index,
        team_by_id,
    )
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
        runtime=EspnInjuriesClientRuntime(
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            sleep=_noop_sleep,
        ),
    )
    result = build_injuries_table(
        client=client, overrides_path=tmp_path / "none.yaml", out_dir=out_dir
    )
    assert result.unresolved_player_ids == []
    saved = pd.read_parquet(out_dir / "injuries.parquet")
    assert 8478443 in set(saved["player_id"])
    assert 3904175 in set(saved["espn_id"])
