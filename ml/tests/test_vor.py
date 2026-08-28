"""Tests for draft_oracle.optimize.vor (US-018).

Covers replacement-level scarcity (2-manager, 12-manager, IR, and the final round
with only two teams alive), VOR pricing for skaters and teams, deterministic
cheat-sheet ordering, and the IR-driven layout change. All fixtures are tiny
in-memory frames -- no committed data, no network (SPEC section 7).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from hypothesis import given
from hypothesis import strategies as st

from draft_oracle.optimize.vor import (
    CHEATSHEET_COLUMNS,
    RosterDemand,
    VorConfig,
    build_cheatsheet,
    render_cheatsheet_markdown,
    replacement_level,
    roster_demand,
    write_cheatsheet,
)


def _skaters(forward_points: list[float], defense_points: list[float]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    pid = 1
    for pts in forward_points:
        rows.append(
            {
                "player_id": pid,
                "player_name": f"F{pid}",
                "team_abbrev": "AAA",
                "position": "F",
                "expected_points": pts,
                "p10": pts - 1,
                "p50": pts,
                "p90": pts + 1,
                "injured": False,
            }
        )
        pid += 1
    for pts in defense_points:
        rows.append(
            {
                "player_id": pid,
                "player_name": f"D{pid}",
                "team_abbrev": "BBB",
                "position": "D",
                "expected_points": pts,
                "p10": pts - 1,
                "p50": pts,
                "p90": pts + 1,
                "injured": False,
            }
        )
        pid += 1
    return pd.DataFrame(rows)


def _teams(points: list[float]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for i, pts in enumerate(points):
        rows.append(
            {
                "team_id": i + 1,
                "team_abbrev": f"T{i + 1}",
                "e_goalie_points": pts,
            }
        )
    return pd.DataFrame(rows)


# -- replacement_level primitive -------------------------------------------------


def test_replacement_level_picks_the_next_asset_past_demand() -> None:
    # 5 values, demand 2 starters -> replacement is the 3rd-best (index 2).
    assert replacement_level([10.0, 8.0, 6.0, 4.0, 2.0], starters=2) == 6.0


def test_replacement_level_is_rank_not_input_order() -> None:
    assert replacement_level([2.0, 10.0, 6.0, 8.0, 4.0], starters=1) == 8.0


def test_replacement_level_zero_when_demand_exceeds_supply() -> None:
    # Final round: only 2 teams alive but 4 managers each want a goalie slot.
    assert replacement_level([5.0, 3.0], starters=4) == 0.0
    assert replacement_level([], starters=1) == 0.0


def test_replacement_level_zero_when_demand_equals_supply() -> None:
    assert replacement_level([5.0, 3.0], starters=2) == 0.0


def test_replacement_level_rejects_negative_starters() -> None:
    with pytest.raises(ValueError, match="starters must be >= 0"):
        replacement_level([1.0], starters=-1)


@given(
    values=st.lists(st.floats(min_value=0, max_value=100), min_size=1, max_size=30),
    starters=st.integers(min_value=0, max_value=30),
)
def test_replacement_level_matches_sorted_index(values: list[float], starters: int) -> None:
    ranked = sorted(values, reverse=True)
    expected = ranked[starters] if starters < len(ranked) else 0.0
    assert replacement_level(values, starters) == expected


# -- roster demand + IR ----------------------------------------------------------


def test_roster_demand_standard_and_ir() -> None:
    assert roster_demand(ir=False) == RosterDemand(5, 3, 1)
    assert roster_demand(ir=True) == RosterDemand(6, 4, 1)


def test_vor_config_rejects_zero_managers() -> None:
    with pytest.raises(ValueError, match="managers must be >= 1"):
        VorConfig(managers=0)


# -- scarcity edge cases (acceptance criteria) -----------------------------------


def test_two_manager_league_replacement_levels() -> None:
    # 2 managers: F replacement = (5*2 + 1)-th = 11th forward, D = 7th, G = 3rd team.
    forwards = [float(30 - i) for i in range(15)]  # 30..16
    defense = [float(20 - i) for i in range(10)]  # 20..11
    teams = _teams([float(12 - i) for i in range(6)])  # 12..7
    sheet = build_cheatsheet(_skaters(forwards, defense), teams, config=VorConfig(managers=2))
    assert sheet.replacement_forward == forwards[10]  # 11th ranked (index 10) = 20
    assert sheet.replacement_defense == defense[6]  # 7th ranked = 14
    assert sheet.replacement_goalie == 10.0  # 3rd team = 12-2


def test_twelve_manager_league_replacement_levels() -> None:
    # 12 managers: F replacement = 61st forward; with a small pool that is 0.0.
    forwards = [float(70 - i) for i in range(65)]  # plenty of forwards
    defense = [float(40 - i) for i in range(30)]  # 30 D < 37 demand -> 0.0
    teams = _teams([float(20 - i) for i in range(8)])  # 8 teams < 13 demand -> 0.0
    sheet = build_cheatsheet(_skaters(forwards, defense), teams, config=VorConfig(managers=12))
    assert sheet.replacement_forward == forwards[60]  # 61st ranked forward
    assert sheet.replacement_defense == 0.0  # demand 36 > 30 supply
    assert sheet.replacement_goalie == 0.0  # demand 12 > 8 supply


def test_final_round_two_teams_alive() -> None:
    # Only 2 teams remain but 4 managers -> no free replacement, VOR = full points.
    teams = _teams([9.0, 4.0])
    sheet = build_cheatsheet(_skaters([], []), teams, config=VorConfig(managers=4))
    assert sheet.replacement_goalie == 0.0
    goalie_rows = sheet.rows[sheet.rows["position"] == "G"].set_index("name")
    assert goalie_rows.loc["T1", "vor"] == 9.0
    assert goalie_rows.loc["T2", "vor"] == 4.0


def test_ir_raises_skater_replacement_demand() -> None:
    forwards = [float(30 - i) for i in range(20)]
    defense = [float(20 - i) for i in range(15)]
    teams = _teams([float(12 - i) for i in range(6)])
    skaters = _skaters(forwards, defense)
    no_ir = build_cheatsheet(skaters, teams, config=VorConfig(managers=2, ir=False))
    with_ir = build_cheatsheet(skaters, teams, config=VorConfig(managers=2, ir=True))
    # IR adds +1 F, +1 D per manager -> higher demand -> deeper (lower) replacement.
    assert no_ir.replacement_forward == forwards[10]  # 11th
    assert with_ir.replacement_forward == forwards[12]  # 13th (6*2+1)
    assert with_ir.replacement_forward < no_ir.replacement_forward
    assert with_ir.replacement_defense == defense[8]  # 9th (4*2+1)
    # Goalie demand is unchanged by IR.
    assert with_ir.replacement_goalie == no_ir.replacement_goalie


# -- VOR + cheat-sheet assembly --------------------------------------------------


def test_vor_equals_projection_minus_replacement() -> None:
    forwards = [20.0, 15.0, 10.0, 5.0]
    sheet = build_cheatsheet(_skaters(forwards, []), _teams([]), config=VorConfig(managers=1))
    # 1 manager, no IR -> F replacement = 6th forward; only 4 exist -> 0.0.
    assert sheet.replacement_forward == 0.0
    rows = sheet.rows.set_index("name")
    assert rows.loc["F1", "vor"] == 20.0


def test_cheatsheet_columns_and_sorted_by_vor() -> None:
    forwards = [float(30 - i) for i in range(12)]
    defense = [float(25 - i) for i in range(8)]
    teams = _teams([15.0, 11.0, 7.0])
    sheet = build_cheatsheet(_skaters(forwards, defense), teams, config=VorConfig(managers=2))
    assert list(sheet.rows.columns) == list(CHEATSHEET_COLUMNS)
    vor = sheet.rows["vor"].tolist()
    assert vor == sorted(vor, reverse=True)
    assert sheet.rows["rank"].tolist() == list(range(1, len(sheet.rows) + 1))


def test_cheatsheet_mixes_skaters_and_teams() -> None:
    sheet = build_cheatsheet(_skaters([30.0], [25.0]), _teams([40.0]), config=VorConfig(managers=1))
    positions = set(sheet.rows["position"])
    assert positions == {"F", "D", "G"}
    # The team with a big goalie projection and no replacement tops the board.
    assert sheet.rows.iloc[0]["position"] == "G"


def test_empty_pools_produce_empty_sheet() -> None:
    sheet = build_cheatsheet(_skaters([], []), _teams([]), config=VorConfig(managers=4))
    assert list(sheet.rows.columns) == list(CHEATSHEET_COLUMNS)
    assert sheet.rows.empty
    assert sheet.replacement_forward == 0.0


def test_injured_flag_carries_to_sheet() -> None:
    skaters = _skaters([30.0, 20.0], [])
    skaters.loc[0, "injured"] = True
    sheet = build_cheatsheet(skaters, _teams([]), config=VorConfig(managers=1))
    flagged = sheet.rows.set_index("name")["injured"]
    assert bool(flagged.loc["F1"]) is True
    assert bool(flagged.loc["F2"]) is False


# -- markdown rendering (IR-driven layout) ---------------------------------------


def test_markdown_is_ascii_and_reports_replacement() -> None:
    sheet = build_cheatsheet(
        _skaters([30.0, 20.0], [15.0]), _teams([12.0]), config=VorConfig(managers=2)
    )
    md = render_cheatsheet_markdown(sheet)
    md.encode("ascii")  # must not raise (Windows cp1252 console safety)
    assert "Replacement level" in md
    assert "5 F / 3 D / 1 G" in md
    assert "IR slots: off" in md


def test_markdown_layout_changes_with_ir() -> None:
    skaters = _skaters([30.0, 20.0], [15.0])
    skaters.loc[0, "injured"] = True
    no_ir = render_cheatsheet_markdown(
        build_cheatsheet(skaters, _teams([12.0]), config=VorConfig(managers=1, ir=False))
    )
    with_ir = render_cheatsheet_markdown(
        build_cheatsheet(skaters, _teams([12.0]), config=VorConfig(managers=1, ir=True))
    )
    assert "IR slots: off" in no_ir
    assert "6 F / 4 D / 1 G" in with_ir
    assert "IR slots: on" in with_ir
    # Injured skaters are tagged differently depending on the IR flag.
    assert "OUT" in no_ir
    assert "IR?" in with_ir


def test_write_cheatsheet_writes_markdown(tmp_path: Path) -> None:
    sheet = build_cheatsheet(_skaters([30.0], []), _teams([12.0]), config=VorConfig(managers=1))
    out = write_cheatsheet(sheet, tmp_path / "cheatsheet.md")
    assert out.exists()
    assert out.read_text(encoding="utf-8").startswith("# Draft Oracle cheat sheet")


def test_summary_is_json_serialisable() -> None:
    import json

    sheet = build_cheatsheet(
        _skaters([30.0], [15.0]), _teams([12.0]), config=VorConfig(managers=4, ir=True)
    )
    payload = json.dumps(sheet.summary())
    restored = json.loads(payload)
    assert restored["managers"] == 4
    assert restored["ir"] is True
    assert restored["roster_demand"]["forwards_per_manager"] == 6
