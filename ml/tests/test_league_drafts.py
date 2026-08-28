"""Tests for league draft-history parsing (US-006).

Run against the committed snapshots in ``data/raw/league-drafts/``. Expected pick and
flag counts per tab are derived from ``SCHEMA.md`` §8 and ``OPEN_QUESTIONS.md``.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from draft_oracle.ingest.league_drafts import (
    DEFAULT_LEAGUE_DRAFTS_DIR,
    LeagueDraftsResult,
    _read_dict_rows,
    build_champions,
    build_league_drafts,
    canonical_manager,
    detect_draft_order,
    parse_app_draft_order,
    parse_app_picks,
    parse_sheet_tab,
    parse_wins_tab,
    read_csv_rows,
    slot_position,
)

LEAGUE_DIR = DEFAULT_LEAGUE_DRAFTS_DIR


# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def result(tmp_path_factory: pytest.TempPathFactory) -> LeagueDraftsResult:
    out_dir = tmp_path_factory.mktemp("league_out")
    return build_league_drafts(league_dir=LEAGUE_DIR, out_dir=out_dir)


@pytest.fixture(scope="module")
def picks(result: LeagueDraftsResult) -> pd.DataFrame:
    return result.picks


# ── Small units ──────────────────────────────────────────────────────────


def test_canonical_manager_folds_aliases() -> None:
    assert canonical_manager("Evi") == "levi"
    assert canonical_manager("Levi ") == "levi"
    assert canonical_manager("Judah ") == "judah"
    assert canonical_manager("nuttguy") == "kyle"
    assert canonical_manager("bentunigold") == "ben"
    assert canonical_manager("judah18") == "judah"
    assert canonical_manager("gemmell.levi") == "levi"
    # Press-only managers keep their lowercased username.
    assert canonical_manager("paul.markhauser") == "paul.markhauser"


def test_slot_position_mapping() -> None:
    assert slot_position("Forward 1") == "F"
    assert slot_position("Forward 5") == "F"
    assert slot_position("Defense 3") == "D"
    assert slot_position("Goalie 1") == "G"
    assert slot_position("IR - F") == "IR_F"
    assert slot_position("IR - D") == "IR_D"
    assert slot_position("Total") is None
    assert slot_position("Total across Rounds") is None


# ── Per-tab pick and flag counts (SCHEMA §8) ─────────────────────────────

# (file, season, event, expected picks, status flags, excluded, activated)
_TAB_EXPECTATIONS = [
    ("sheet3__round-1.csv", 2024, "R1", 36, 0, 0, 0),
    ("sheet3__round-2.csv", 2024, "R2", 36, 0, 0, 0),
    ("sheet3__round-3-round-4.csv", 2024, "R3_4", 36, 0, 0, 0),
    ("sheet2__round-1.csv", 2025, "R1", 44, 2, 1, 1),
    ("sheet2__round-2.csv", 2025, "R2", 44, 4, 2, 2),
    ("sheet2__round-3-4.csv", 2025, "R3_4", 44, 0, 2, 2),
    ("sheet1__round-1.csv", 2026, "R1", 36, 0, 0, 0),
    ("sheet1__round-2.csv", 2026, "R2", 36, 2, 2, 0),
]


@pytest.mark.parametrize(
    ("file", "season", "event", "n_picks", "n_flags", "n_excluded", "n_activated"),
    _TAB_EXPECTATIONS,
)
def test_tab_counts(
    file: str,
    season: int,
    event: str,
    n_picks: int,
    n_flags: int,
    n_excluded: int,
    n_activated: int,
) -> None:
    rows = read_csv_rows(LEAGUE_DIR / file)
    records = parse_sheet_tab(rows, season, event)
    assert len(records) == n_picks
    assert sum(1 for r in records if r["status"] is not None) == n_flags
    assert sum(1 for r in records if r["points_excluded"]) == n_excluded
    assert sum(1 for r in records if r["ir_activated"]) == n_activated
    # Every block is a legal 9-starter composition (5F + 3D + 1G), IR excluded.
    non_ir = [r for r in records if not str(r["position"]).startswith("IR")]
    assert len(non_ir) == 36  # 4 managers x 9 starters


def test_every_manager_round_has_full_starter_composition(picks: pd.DataFrame) -> None:
    scored = picks[(picks.source == "sheet")]
    grouped = scored[~scored.position.str.startswith("IR")].groupby(
        ["season", "draft_event", "manager"]
    )
    for (_season, _event, _manager), block in grouped:
        counts = block.position.value_counts().to_dict()
        assert counts.get("F") == 5
        assert counts.get("D") == 3
        assert counts.get("G") == 1


# ── Documented corrections ───────────────────────────────────────────────


def test_makar_row_corrected_to_bouchard(picks: pd.DataFrame) -> None:
    row = picks[
        (picks.season == 2024)
        & (picks.draft_event == "R3_4")
        & (picks.manager == "levi")
        & (picks.slot_label == "Defense 1")
    ]
    assert len(row) == 1
    assert row.iloc[0]["player_or_team_name"] == "Makar"  # raw preserved
    assert row.iloc[0]["corrected_name"] == "Evan Bouchard"


def test_trouba_note_parsed_as_recorded(picks: pd.DataFrame) -> None:
    row = picks[
        (picks.season == 2024)
        & (picks.draft_event == "R3_4")
        & (picks.manager == "ben")
        & (picks.slot_label == "Defense 1")
    ]
    assert len(row) == 1
    # Kulikov is the recorded holder; the +3 lives in the note, not a substitution.
    assert row.iloc[0]["player_or_team_name"] == "Dmitry Kulikov"
    assert "Trouba" in str(row.iloc[0]["note"])
    assert row.iloc[0]["points_excluded"] is False or not bool(row.iloc[0]["points_excluded"])


def test_unflagged_2025_swaps_marked(picks: pd.DataFrame) -> None:
    r34 = picks[(picks.season == 2025) & (picks.draft_event == "R3_4")]
    reinhart = r34[r34.player_or_team_name == "Sam Reinhart"].iloc[0]
    verhaeghe = r34[r34.player_or_team_name == "Carter Verhaeghe"].iloc[0]
    assert bool(reinhart["points_excluded"]) is True
    assert reinhart["status"] is None or pd.isna(reinhart["status"])
    assert bool(verhaeghe["ir_activated"]) is True
    assert reinhart["swap_partner"] == "Carter Verhaeghe"
    assert verhaeghe["swap_partner"] == "Sam Reinhart"


def test_flagged_ir_swaps_pair_same_position(picks: pd.DataFrame) -> None:
    # Scored seasons with IR slots always pair an excluded F/D starter with an IR row.
    excluded = picks[(picks.source == "sheet") & picks.is_scored & picks.points_excluded]
    for _, starter in excluded.iterrows():
        if str(starter["position"]) not in ("F", "D"):
            continue
        assert starter["swap_partner"] is not None and not pd.isna(starter["swap_partner"])


def test_hyman_mini_columns_honored(picks: pd.DataFrame) -> None:
    row = picks[
        (picks.season == 2024)
        & (picks.draft_event == "R1")
        & (picks.player_or_team_name == "Zach Hyman")
    ].iloc[0]
    assert row["points_for_round"] == 3
    assert row["points_when_drafted"] == 5
    assert row["current_total_points"] == 8


# ── Draft order (snake_slot) ─────────────────────────────────────────────


def test_detect_draft_order_vertical() -> None:
    rows = read_csv_rows(LEAGUE_DIR / "sheet3__round-1.csv")
    order = detect_draft_order(rows)
    assert order == {"levi": 1, "ben": 2, "kyle": 3, "judah": 4}


def test_detect_draft_order_horizontal() -> None:
    rows = read_csv_rows(LEAGUE_DIR / "sheet2__round-2.csv")
    order = detect_draft_order(rows)
    assert order == {"judah": 1, "ben": 2, "levi": 3, "kyle": 4}


def test_detect_draft_order_absent_returns_none() -> None:
    rows = read_csv_rows(LEAGUE_DIR / "sheet2__round-1.csv")
    assert detect_draft_order(rows) is None


def test_sheet2_round1_snake_slot_null(picks: pd.DataFrame) -> None:
    subset = picks[(picks.season == 2025) & (picks.draft_event == "R1")]
    assert subset.snake_slot.isna().all()


def test_evi_order_folds_to_levi() -> None:
    # sheet1 R1 order list names "Evi" where Levi must sit.
    rows = read_csv_rows(LEAGUE_DIR / "sheet1__round-1.csv")
    order = detect_draft_order(rows)
    assert order == {"kyle": 1, "ben": 2, "levi": 3, "judah": 4}


# ── 2026 (sheet1) unscored rosters ───────────────────────────────────────


def test_2026_rosters_unscored(picks: pd.DataFrame) -> None:
    sheet_2026 = picks[(picks.source == "sheet") & (picks.season == 2026)]
    assert len(sheet_2026) == 72  # R1 36 + R2 36
    assert (~sheet_2026.is_scored).all()
    assert sheet_2026.points_for_round.isna().all()


def test_2026_round34_excluded(picks: pd.DataFrame) -> None:
    # sheet1__round-3-4.csv is a stale 2025 duplicate and must not appear.
    sheet_2026 = picks[(picks.source == "sheet") & (picks.season == 2026)]
    assert set(sheet_2026.draft_event.unique()) == {"R1", "R2"}


# ── Champions ────────────────────────────────────────────────────────────


def test_champions_table(result: LeagueDraftsResult) -> None:
    years = [int(y) for y in result.champions["year"].tolist()]
    champs = dict(zip(years, result.champions["champion"].tolist(), strict=True))
    assert champs == {
        2018: "ben",
        2019: "levi",
        2020: "levi",
        2021: "levi",
        2022: "levi",
        2023: "kyle",
        2024: "levi",
        2025: "levi",
        2026: "ben",
    }


def test_parse_wins_tab_folds_evi() -> None:
    rows = read_csv_rows(LEAGUE_DIR / "sheet2__wins.csv")
    champs = parse_wins_tab(rows)
    assert champs[2019] == "levi"  # raw "Evi"
    assert 2014 not in champs  # NHL-only backfill has no league champion


def test_build_champions_standalone() -> None:
    frame = build_champions(LEAGUE_DIR)
    assert list(frame.year) == [2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]


# ── App export ───────────────────────────────────────────────────────────


def test_app_export_present_and_counted(result: LeagueDraftsResult) -> None:
    assert result.app_present is True
    assert result.app_picks == 240


def test_app_picks_preserve_pick_number(picks: pd.DataFrame) -> None:
    app = picks[picks.source == "app"]
    assert app.league_name.value_counts().to_dict() == {
        "Press Play-offs": 132,
        "The Gemmell Cup": 108,
    }
    gemmell_r1 = app[(app.league_name == "The Gemmell Cup") & (app.draft_event == "R1")]
    # pick_number is contiguous 1..36 for the Gemmell round-1 draft.
    assert sorted(gemmell_r1.pick_number.tolist()) == list(range(1, 37))


def test_app_manager_aliasing(picks: pd.DataFrame) -> None:
    app = picks[picks.source == "app"]
    gemmell = set(app[app.league_name == "The Gemmell Cup"].manager.unique())
    assert gemmell == {"ben", "judah", "kyle", "levi"}


def test_app_snake_slot_from_order() -> None:
    order = parse_app_draft_order(_read_dict_rows(LEAGUE_DIR / "app-export-2026__draft-order.csv"))
    picks = parse_app_picks(_read_dict_rows(LEAGUE_DIR / "app-export-2026__draft-picks.csv"), order)
    slots = [p["snake_slot"] for p in picks if p["snake_slot"] is not None]
    assert slots  # every app pick resolves a seat
    assert all(isinstance(s, int) and 1 <= s <= 4 for s in slots)


def test_missing_app_export_reported(tmp_path: Path) -> None:
    # Copy only the sheet snapshots (no app-export files) into a temp dir.
    src = LEAGUE_DIR
    for name in src.iterdir():
        if name.is_file() and not name.name.startswith("app-export"):
            (tmp_path / name.name).write_bytes(name.read_bytes())
    out_dir = tmp_path / "out"
    res = build_league_drafts(league_dir=tmp_path, out_dir=out_dir)
    assert res.app_present is False
    assert res.app_picks == 0
    assert any("ABSENT" in line for line in res.report_lines())
    # Sheets still parse without the app data.
    assert len(res.picks) == 312


# ── Fail-loud behavior ───────────────────────────────────────────────────


def test_bad_header_raises() -> None:
    rows = [["", "Wrong", "Header"], ["Ben", "Forward 1", "X", "Y", "1"]]
    with pytest.raises(ValueError, match="unexpected header"):
        parse_sheet_tab(rows, 2025, "R1")


def test_unknown_slot_label_raises() -> None:
    rows = [
        ["", "Position ", "Player ", "Team", "Points"],
        ["Ben", "Bench 1", "Nobody", "Team", "0"],
    ]
    with pytest.raises(ValueError):
        parse_sheet_tab(rows, 2025, "R1")


def test_wrong_block_count_raises() -> None:
    rows = [
        ["", "Position ", "Player ", "Team", "Points"],
        ["Ben", "Forward 1", "X", "Y", "1"],
        ["", "Total", "", "", "1"],
    ]
    with pytest.raises(ValueError, match="4 manager blocks"):
        parse_sheet_tab(rows, 2025, "R1")


# ── Parquet output ───────────────────────────────────────────────────────


def test_parquet_written(result: LeagueDraftsResult) -> None:
    assert (result.out_dir / "league_picks.parquet").exists()
    assert (result.out_dir / "league_champions.parquet").exists()
    reloaded = pd.read_parquet(result.out_dir / "league_picks.parquet")
    assert len(reloaded) == 552
