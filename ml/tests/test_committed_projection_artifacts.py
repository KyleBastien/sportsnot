"""Structural regression checks for owner-approved 2026 projection artifacts."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

ML_ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS_ROOT = ML_ROOT / "artifacts"
EXPECTED_TEAMS = {
    1: {
        "ANA",
        "BOS",
        "BUF",
        "CAR",
        "COL",
        "DAL",
        "EDM",
        "LAK",
        "MIN",
        "MTL",
        "OTT",
        "PHI",
        "PIT",
        "TBL",
        "UTA",
        "VGK",
    },
    2: {"ANA", "BUF", "CAR", "COL", "MIN", "MTL", "PHI", "VGK"},
    3: {"CAR", "COL", "MTL", "VGK"},
    4: {"CAR", "VGK"},
}
CSV_FLOAT_RTOL = 1e-12
CSV_FLOAT_ATOL = 1e-12


def _artifact(round_number: int) -> tuple[Path, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    artifact_dir = ARTIFACTS_ROOT / f"2026-r{round_number}"
    skaters = pd.read_parquet(artifact_dir / "skaters.parquet")
    teams = pd.read_parquet(artifact_dir / "teams.parquet")
    manifest = json.loads((artifact_dir / "run_manifest.json").read_text(encoding="utf-8"))
    return artifact_dir, skaters, teams, manifest


def _goalie_team_abbrevs(cheatsheet: str) -> set[str]:
    goalie_rows = re.findall(
        r"^\|\s*\d+\s*\|\s*G\s*\|\s*([A-Z0-9]+)\s*\|\s*([A-Z0-9]+)\s*\|",
        cheatsheet,
        flags=re.MULTILINE,
    )
    assert all(player == team for player, team in goalie_rows)
    return {team for _, team in goalie_rows}


@pytest.mark.parametrize("round_number", [1, 2, 3, 4])
@pytest.mark.parametrize("table_name", ["skaters", "teams"])
def test_committed_2026_projection_csv_matches_parquet(
    round_number: int,
    table_name: str,
) -> None:
    """CSV twins preserve parquet rows within CSV round-trip precision."""
    artifact_dir = ARTIFACTS_ROOT / f"2026-r{round_number}"
    csv_frame = pd.read_csv(artifact_dir / f"{table_name}.csv").replace("", np.nan)
    parquet_frame = pd.read_parquet(
        artifact_dir / f"{table_name}.parquet"
    ).replace("", np.nan)

    pd.testing.assert_frame_equal(
        csv_frame,
        parquet_frame,
        check_dtype=False,
        check_exact=False,
        rtol=CSV_FLOAT_RTOL,
        atol=CSV_FLOAT_ATOL,
    )


@pytest.mark.parametrize("round_number", [1, 2, 3, 4])
def test_committed_2026_projection_artifact_structure(round_number: int) -> None:
    artifact_dir, skaters, teams, manifest = _artifact(round_number)
    expected_teams = EXPECTED_TEAMS[round_number]

    assert manifest["season"] == 2026
    assert manifest["playoff_round"] == round_number
    assert manifest["git_dirty"] is False
    assert re.fullmatch(r"[0-9a-f]{40}", manifest["git_sha"])
    assert set(manifest["eligible_team_abbrevs"]) == expected_teams
    assert set(teams["team_abbrev"]) == expected_teams
    assert set(skaters["team_abbrev"]) == expected_teams
    assert manifest["counts"]["eligible_teams"] == len(teams)
    assert manifest["counts"]["eligible_series"] == len(teams) // 2
    assert manifest["counts"]["skaters_projected"] == len(skaters)

    assert skaters["player_id"].is_unique
    assert set(skaters["position"]) <= {"F", "D"}
    assert (skaters["p10"] <= skaters["p50"]).all()
    assert (skaters["p50"] <= skaters["p90"]).all()
    assert np.allclose(
        skaters["expected_points"],
        skaters["pts_per_game"] * skaters["expected_games"],
        rtol=0.1,
        atol=0.05,
    )

    assert teams["team_id"].is_unique
    assert teams["team_abbrev"].is_unique
    by_abbrev = teams.set_index("team_abbrev")
    for team in teams.to_dict("records"):
        opponent = by_abbrev.loc[str(team["opponent_abbrev"])]
        assert opponent["opponent_abbrev"] == team["team_abbrev"]
        assert float(team["p_series_win"]) + opponent["p_series_win"] == pytest.approx(1.0)

    cheatsheet = (artifact_dir / "cheatsheet.md").read_text(encoding="utf-8")
    assert _goalie_team_abbrevs(cheatsheet) == expected_teams


def test_committed_2026_r3_combined_event_decomposition() -> None:
    _, _, _, manifest = _artifact(3)
    combined = manifest["combined_event"]

    assert combined["draft_event"] == "R3_4"
    assert combined["draft_round"] == 3
    assert combined["scored_rounds"] == [3, 4]
    assert {team["team_abbrev"] for team in combined["teams"]} == EXPECTED_TEAMS[3]
    for team in combined["teams"]:
        expected = team["e_goalie_points_r3"] + (
            team["p_advance"] * team["e_goalie_points_r4"]
        )
        assert team["e_goalie_points_combined"] == pytest.approx(expected, abs=2e-6)


@pytest.mark.parametrize("round_number", [1, 2, 3])
def test_committed_slot_strategies_use_honestly_labeled_deduped_fit(
    round_number: int,
) -> None:
    artifact_dir, _, _, manifest = _artifact(round_number)
    slots = manifest["slot_strategies"]

    assert slots["opponent_label"] == (
        "league-average fitted coefficients (per-seat, affinity zeroed)"
    )
    assert slots["fitted_opponents"] is False
    report = (artifact_dir / "slot_strategies.md").read_text(encoding="utf-8")
    assert slots["opponent_label"] in report
    assert "fitted league model" not in report
