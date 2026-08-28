"""Tests for draft_oracle.ingest.normalize (US-004).

All fixtures are built in-memory / on tmp_path — no network, no committed
archive dependency (SPEC §7).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from draft_oracle.ingest import PlayoffBracket
from draft_oracle.ingest.normalize import (
    MANIFEST_NAME,
    TABLE_NAMES,
    bracket_year_from_label,
    build_team_abbrev_map,
    create_snapshot,
    discover_season_labels,
    list_snapshots,
    map_position,
    normalize_archive,
    normalize_players,
    normalize_series,
    normalize_skater_games,
    normalize_team_games,
    normalize_teams,
    season_id_from_label,
    season_id_from_year,
)

# ── Position mapping (SPEC §1) ───────────────────────────────────────────


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("C", "F"),
        ("L", "F"),
        ("R", "F"),
        ("D", "D"),
        ("G", None),
        ("g", None),
        ("d", "D"),
        (" C ", "F"),
        (None, None),
        ("X", None),
    ],
)
def test_map_position(code: str | None, expected: str | None) -> None:
    assert map_position(code) == expected


# ── Season-label helpers ─────────────────────────────────────────────────


def test_season_id_from_label() -> None:
    assert season_id_from_label("2015-16") == 20152016
    assert season_id_from_label("2025-26") == 20252026


def test_bracket_year_from_label() -> None:
    assert bracket_year_from_label("2015-16") == 2016
    assert bracket_year_from_label("2025-26") == 2026


def test_season_id_from_year() -> None:
    assert season_id_from_year(2026) == 20252026


def test_season_id_from_label_rejects_garbage() -> None:
    with pytest.raises(ValueError, match="Unrecognized season label"):
        season_id_from_label("nope")


# ── Fixtures ─────────────────────────────────────────────────────────────


def _raw_skaters() -> pd.DataFrame:
    return pd.DataFrame(
        [
            # centre, wing, defenceman → F, F, D
            _skater_row(2025020001, 100, "Centre Guy", "C", "NYR", "BOS", 1, 1),
            _skater_row(2025020001, 101, "Wing Guy", "L", "NYR", "BOS", 0, 2),
            _skater_row(2025020001, 200, "D Guy", "D", "BOS", "NYR", 0, 0),
            # a goalie row that must be dropped
            _skater_row(2025020001, 300, "Goalie Guy", "G", "BOS", "NYR", 0, 0),
        ]
    )


def _skater_row(
    game_id: int,
    player_id: int,
    name: str,
    pos: str,
    team: str,
    opp: str,
    goals: int,
    assists: int,
) -> dict[str, object]:
    return {
        "seasonId": 20252026,
        "gameTypeId": 3,
        "gameId": game_id,
        "gameDate": "2026-04-20",
        "playerId": player_id,
        "skaterFullName": name,
        "positionCode": pos,
        "shootsCatches": "L",
        "teamAbbrev": team,
        "opponentTeamAbbrev": opp,
        "homeRoad": "H",
        "goals": goals,
        "assists": assists,
        "points": goals + assists,
        "shots": 3,
        "timeOnIcePerGame": 1200.0,
        "ppGoals": 0,
        "ppPoints": 0,
        "shGoals": 0,
        "shPoints": 0,
        "evGoals": goals,
        "evPoints": goals + assists,
        "plusMinus": 1,
        "penaltyMinutes": 0,
        "gameWinningGoals": 0,
        "otGoals": 0,
        "shootingPct": 0.33,
        "faceoffWinPct": None,
    }


def _raw_teams() -> pd.DataFrame:
    return pd.DataFrame(
        [
            _team_row(2025020001, 3, "New York Rangers", "BOS", 1, 0, 0),
            _team_row(2025020001, 6, "Boston Bruins", "NYR", 0, 0, 3),
        ]
    )


def _team_row(
    game_id: int,
    team_id: int,
    full_name: str,
    opp_abbrev: str,
    win: int,
    goals_against: int,
    goals_for: int,
) -> dict[str, object]:
    return {
        "seasonId": 20252026,
        "gameTypeId": 3,
        "gameId": game_id,
        "gameDate": "2026-04-20",
        "teamId": team_id,
        "teamFullName": full_name,
        "opponentTeamAbbrev": opp_abbrev,
        "homeRoad": "H",
        "goalsFor": goals_for,
        "goalsAgainst": goals_against,
        "wins": win,
        "losses": 1 - win,
        "otLosses": 0,
        "ties": None,
        "regulationAndOtWins": win,
        "winsInRegulation": win,
        "winsInShootout": 0,
        "points": 2 * win,
        "pointPct": float(win),
        "teamShutouts": 1 if (win == 1 and goals_against == 0) else 0,
    }


def _raw_bios() -> pd.DataFrame:
    return pd.DataFrame(
        [
            _bios_row(20242025, 100, "Centre Guy", "C", "NYR"),
            _bios_row(20252026, 100, "Centre Guy", "C", "NYR"),  # newer wins
            _bios_row(20252026, 200, "D Guy", "D", "BOS"),
            _bios_row(20252026, 300, "Goalie Guy", "G", "BOS"),  # dropped
        ]
    )


def _bios_row(season_id: int, player_id: int, name: str, pos: str, team: str) -> dict[str, object]:
    return {
        "seasonId": season_id,
        "playerId": player_id,
        "skaterFullName": name,
        "lastName": name.split()[-1],
        "birthDate": "1999-01-01",
        "positionCode": pos,
        "shootsCatches": "L",
        "height": 72,
        "weight": 190,
        "birthCity": "Somewhere",
        "birthStateProvinceCode": "ON",
        "birthCountryCode": "CAN",
        "nationalityCode": "CAN",
        "draftYear": 2017,
        "draftRound": 1,
        "draftOverall": 5,
        "firstSeasonForGameType": 20182019,
        "currentTeamAbbrev": team,
    }


def _bracket() -> PlayoffBracket:
    return PlayoffBracket.model_validate(
        {
            "series": [
                {
                    "seriesLetter": "A",
                    "seriesAbbrev": "R1",
                    "playoffRound": 1,
                    "topSeedWins": 4,
                    "bottomSeedWins": 2,
                    "winningTeamId": 3,
                    "losingTeamId": 6,
                    "topSeedTeam": {"id": 3, "abbrev": "NYR"},
                    "bottomSeedTeam": {"id": 6, "abbrev": "BOS"},
                }
            ]
        }
    )


# ── Per-table normalizers ────────────────────────────────────────────────


def test_normalize_skater_games_drops_goalies_and_maps_positions() -> None:
    df = normalize_skater_games(_raw_skaters())
    assert 300 not in set(df["player_id"])  # goalie dropped
    assert len(df) == 3
    positions = dict(zip(df["player_id"], df["position"], strict=False))
    assert positions == {100: "F", 101: "F", 200: "D"}
    assert "toi_seconds" in df.columns
    assert df.loc[df["player_id"] == 100, "toi_seconds"].iloc[0] == 1200.0


def test_normalize_skater_games_dedups_on_rerun() -> None:
    doubled = pd.concat([_raw_skaters(), _raw_skaters()], ignore_index=True)
    df = normalize_skater_games(doubled)
    assert len(df) == 3
    assert df.duplicated(subset=["game_id", "player_id"]).sum() == 0


def test_build_team_abbrev_map() -> None:
    mapping = build_team_abbrev_map(_raw_teams())
    assert mapping == {3: "NYR", 6: "BOS"}


def test_normalize_team_games_flags_and_abbrev() -> None:
    df = normalize_team_games(_raw_teams())
    assert set(df["team_abbrev"]) == {"NYR", "BOS"}
    nyr = df[df["team_id"] == 3].iloc[0]
    assert bool(nyr["win"]) is True
    assert bool(nyr["shutout_win"]) is True  # 3-0 win
    bos = df[df["team_id"] == 6].iloc[0]
    assert bool(bos["win"]) is False
    assert bool(bos["shutout_win"]) is False


def test_normalize_team_games_dedups_on_rerun() -> None:
    doubled = pd.concat([_raw_teams(), _raw_teams()], ignore_index=True)
    df = normalize_team_games(doubled)
    assert len(df) == 2


def test_normalize_players_drops_goalies_and_keeps_latest_season() -> None:
    df = normalize_players(_raw_bios())
    assert 300 not in set(df["player_id"])  # goalie dropped
    assert len(df) == 2
    centre = df[df["player_id"] == 100].iloc[0]
    assert centre["last_season_id"] == 20252026  # newer bio wins
    assert centre["position"] == "F"


def test_normalize_teams_dimension() -> None:
    team_games = normalize_team_games(_raw_teams())
    teams = normalize_teams(team_games)
    assert len(teams) == 2
    lookup = dict(zip(teams["team_id"], teams["team_abbrev"], strict=False))
    assert lookup == {3: "NYR", 6: "BOS"}
    names = dict(zip(teams["team_id"], teams["team_full_name"], strict=False))
    assert names[6] == "Boston Bruins"


def test_normalize_series_from_bracket() -> None:
    df = normalize_series(_bracket(), 2026)
    assert len(df) == 1
    row = df.iloc[0]
    assert row["series_letter"] == "A"
    assert row["season_id"] == 20252026
    assert row["top_seed_abbrev"] == "NYR"
    assert row["bottom_seed_abbrev"] == "BOS"
    assert row["winning_team_id"] == 3


# ── End-to-end archive normalization on a tmp fixture archive ────────────


def _write_fixture_archive(archive_dir: Path, label: str = "2025-26") -> None:
    archive_dir.mkdir(parents=True, exist_ok=True)
    _raw_skaters().to_csv(
        archive_dir / f"skater-games-{label}.csv.gz", index=False, compression="gzip"
    )
    _raw_teams().to_csv(archive_dir / f"team-games-{label}.csv.gz", index=False, compression="gzip")
    _raw_bios().to_csv(archive_dir / f"skater-bios-{label}.csv.gz", index=False, compression="gzip")
    year = bracket_year_from_label(label)
    (archive_dir / f"bracket-{year}.json").write_text(
        _bracket().model_dump_json(by_alias=True), encoding="utf-8"
    )


def test_discover_season_labels(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    _write_fixture_archive(archive, "2024-25")
    _write_fixture_archive(archive, "2025-26")
    assert discover_season_labels(archive) == ["2024-25", "2025-26"]


def test_normalize_archive_writes_all_tables(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    out = tmp_path / "normalized"
    _write_fixture_archive(archive)

    result = normalize_archive(archive_dir=archive, out_dir=out)
    assert result.skipped is False
    for name in TABLE_NAMES:
        assert (out / f"{name}.parquet").exists()
    assert (out / MANIFEST_NAME).exists()
    assert result.row_counts["skater_games"] == 3
    assert result.row_counts["team_games"] == 2
    assert result.row_counts["series"] == 1
    assert result.row_counts["players"] == 2
    assert result.row_counts["teams"] == 2


def test_normalize_archive_is_idempotent(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    out = tmp_path / "normalized"
    _write_fixture_archive(archive)

    first = normalize_archive(archive_dir=archive, out_dir=out)
    assert first.skipped is False
    second = normalize_archive(archive_dir=archive, out_dir=out)
    assert second.skipped is True  # unchanged sources → no rebuild
    assert second.row_counts == first.row_counts


def test_normalize_archive_force_rebuilds(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    out = tmp_path / "normalized"
    _write_fixture_archive(archive)

    normalize_archive(archive_dir=archive, out_dir=out)
    forced = normalize_archive(archive_dir=archive, out_dir=out, force=True)
    assert forced.skipped is False


def test_normalize_archive_missing_dir(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        normalize_archive(archive_dir=tmp_path / "nope", out_dir=tmp_path / "out")


# ── Snapshots ────────────────────────────────────────────────────────────


def test_create_and_list_snapshot(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    out = tmp_path / "normalized"
    _write_fixture_archive(archive)
    normalize_archive(archive_dir=archive, out_dir=out)

    snap = create_snapshot(out_dir=out, snapshot_id="20260827T000000Z")
    assert snap.snapshot_id == "20260827T000000Z"
    for name in TABLE_NAMES:
        assert (snap.path / f"{name}.parquet").exists()
    assert (snap.path / MANIFEST_NAME).exists()
    assert snap.row_counts["skater_games"] == 3
    assert list_snapshots(out) == ["20260827T000000Z"]

    # Snapshot content matches the live normalized tables (pinnable + reproducible).
    live = pd.read_parquet(out / "series.parquet")
    frozen = pd.read_parquet(snap.path / "series.parquet")
    pd.testing.assert_frame_equal(live, frozen)


def test_snapshot_without_tables_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        create_snapshot(out_dir=tmp_path / "empty")


def test_list_snapshots_empty(tmp_path: Path) -> None:
    assert list_snapshots(tmp_path / "nothing") == []
