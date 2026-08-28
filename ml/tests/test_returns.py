"""Tests for draft_oracle.models.returns (US-015).

All fixtures are in-memory synthetic games -- no network, no committed-archive
dependency (SPEC section 7). Covers absence-spell derivation (bookending +
healthy-scratch filters), the return-time survival curve (monotonicity in game k and
severity ordering across statuses), override precedence (a pinned return game beats the
model), the availability haircut, and an end-to-end honest calibration run.
"""

from __future__ import annotations

from itertools import pairwise

import numpy as np
import pandas as pd
import pytest
from hypothesis import given
from hypothesis import strategies as st

from draft_oracle.ingest.injuries import (
    STATUS_DAY_TO_DAY,
    STATUS_HEALTHY,
    STATUS_IR,
    STATUS_OUT,
    InjuryOverride,
)
from draft_oracle.models import (
    AbsenceSpellConfig,
    ReturnTimeConfig,
    ReturnTimeModel,
    availability_from_return_game,
    derive_absence_spells,
    fit_return_time_model,
    project_availability,
    spells_from_sequence,
    train_return_time_model,
)

HORIZON = 7


def _is_non_decreasing(values: list[float]) -> bool:
    return all(b >= a - 1e-12 for a, b in pairwise(values))


# ── spells_from_sequence ───────────────────────────────────────────────────


def test_spells_from_sequence_bookended_run() -> None:
    # play, miss, miss, play -> one 2-game spell (bookended by appearances).
    present = [True, False, False, True]
    assert spells_from_sequence(present, min_spell=1) == [2]


def test_spells_from_sequence_excludes_leading_and_trailing() -> None:
    # Leading gap (pre-debut) and trailing gap (season end) are NOT spells.
    present = [False, False, True, False, True, False, False]
    assert spells_from_sequence(present, min_spell=1) == [1]


def test_spells_from_sequence_min_spell_filter() -> None:
    # A single missed game is dropped when min_spell=2 (healthy-scratch guard).
    present = [True, False, True, False, False, True]
    assert spells_from_sequence(present, min_spell=2) == [2]
    assert spells_from_sequence(present, min_spell=1) == [1, 2]


def test_spells_from_sequence_needs_two_appearances() -> None:
    assert spells_from_sequence([False, False], min_spell=1) == []
    assert spells_from_sequence([True], min_spell=1) == []


# ── derive_absence_spells ──────────────────────────────────────────────────


def _team_games(season: int, team: str, n: int) -> pd.DataFrame:
    dates = pd.date_range("2021-10-01", periods=n, freq="D").strftime("%Y-%m-%d")
    return pd.DataFrame(
        [
            {
                "season_id": season,
                "game_type_id": 2,
                "game_id": f"{team}{i:03d}",
                "game_date": dates[i],
                "team_abbrev": team,
            }
            for i in range(n)
        ]
    )


def _skater_games(
    season: int, team: str, player_id: int, played_idx: list[int], toi: float
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "season_id": season,
                "game_type_id": 2,
                "game_id": f"{team}{i:03d}",
                "player_id": player_id,
                "team_abbrev": team,
                "toi_seconds": toi,
            }
            for i in played_idx
        ]
    )


def test_derive_absence_spells_finds_injury_gap() -> None:
    season, team, n = 20202021, "AAA", 50
    tg = _team_games(season, team, n)
    # Plays every game except a bookended 4-game absence (games 20-23).
    played = [i for i in range(n) if i not in (20, 21, 22, 23)]
    sg = _skater_games(season, team, 7, played, toi=1000.0)
    config = AbsenceSpellConfig(min_spell=2, min_appearances=20, min_median_toi=600.0)
    spells = derive_absence_spells(sg, tg, config=config)
    assert list(spells["spell_length"]) == [4]
    assert spells.iloc[0]["player_id"] == 7


def test_derive_absence_spells_filters_low_toi_and_low_appearances() -> None:
    season, team, n = 20202021, "AAA", 50
    tg = _team_games(season, team, n)
    played = [i for i in range(n) if i not in (20, 21, 22, 23)]
    # Low median TOI -> excluded as a fringe scratch even with a real gap.
    sg_low_toi = _skater_games(season, team, 1, played, toi=100.0)
    config = AbsenceSpellConfig(min_median_toi=600.0)
    assert derive_absence_spells(sg_low_toi, tg, config=config).empty

    # Too few appearances -> excluded (not an established regular).
    sg_few = _skater_games(season, team, 2, played[:10], toi=1000.0)
    assert derive_absence_spells(sg_few, tg, config=config).empty


# ── ReturnTimeModel curve ──────────────────────────────────────────────────


def _model(lengths: list[int]) -> ReturnTimeModel:
    return fit_return_time_model(pd.DataFrame({"spell_length": lengths}), horizon=HORIZON)


def test_availability_curve_healthy_is_all_available() -> None:
    model = _model([1, 2, 3, 4, 5])
    assert model.availability_curve(STATUS_HEALTHY) == [1.0] * HORIZON


def test_availability_curve_is_monotone_non_decreasing() -> None:
    model = _model([1, 2, 3, 4, 5, 6, 7, 8])
    for status in (STATUS_DAY_TO_DAY, STATUS_OUT, STATUS_IR):
        assert _is_non_decreasing(model.availability_curve(status))


def test_availability_curve_severity_ordering() -> None:
    # A more severe status implies a longer absence -> lower availability haircut.
    model = _model([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
    d2d = model.availability_multiplier(STATUS_DAY_TO_DAY)
    out = model.availability_multiplier(STATUS_OUT)
    ir = model.availability_multiplier(STATUS_IR)
    assert d2d > out > ir
    assert 0.0 <= ir <= d2d <= 1.0


def test_expected_games_available_matches_curve_sum() -> None:
    model = _model([2, 3, 4, 5])
    curve = model.availability_curve(STATUS_OUT)
    assert model.expected_games_available(STATUS_OUT) == pytest.approx(sum(curve))
    assert model.availability_multiplier(STATUS_OUT) == pytest.approx(sum(curve) / HORIZON)


def test_games_missed_raises_availability() -> None:
    # Conditioning on games already missed brings the return closer.
    model = _model([3, 4, 5, 6])
    fresh = model.availability_curve(STATUS_OUT, games_missed=0)
    partway = model.availability_curve(STATUS_OUT, games_missed=2)
    assert sum(partway) >= sum(fresh)


@given(
    lengths=st.lists(st.integers(min_value=1, max_value=40), min_size=1, max_size=30),
    games_missed=st.integers(min_value=0, max_value=10),
    status=st.sampled_from([STATUS_DAY_TO_DAY, STATUS_OUT, STATUS_IR]),
)
def test_availability_curve_monotone_property(
    lengths: list[int], games_missed: int, status: str
) -> None:
    model = _model(lengths)
    curve = model.availability_curve(status, games_missed=games_missed)
    assert len(curve) == HORIZON
    assert all(0.0 <= p <= 1.0 for p in curve)
    assert _is_non_decreasing(curve)


# ── availability_from_return_game + override precedence ────────────────────


def test_availability_from_return_game() -> None:
    assert availability_from_return_game(3, HORIZON) == [0, 0, 1, 1, 1, 1, 1]
    assert availability_from_return_game(1, HORIZON) == [1] * HORIZON


def _injuries(rows: list[dict[str, object]]) -> pd.DataFrame:
    columns = ["player_id", "player_name", "status"]
    return pd.DataFrame(rows, columns=columns)


def test_project_availability_override_pins_return_game() -> None:
    model = _model([2, 3, 4, 5, 6])
    injuries = _injuries([{"player_id": 10, "player_name": "Sidney Crosby", "status": STATUS_OUT}])
    override = InjuryOverride(player="Sidney Crosby", status=STATUS_OUT, return_game=4)
    out = project_availability(injuries, model, overrides=[override])
    row = out.iloc[0]
    assert row["source"] == "override"
    assert [row[f"p_available_g{k}"] for k in range(1, HORIZON + 1)] == [
        0,
        0,
        0,
        1,
        1,
        1,
        1,
    ]


def test_project_availability_override_matches_by_espn_id() -> None:
    model = _model([2, 3, 4, 5, 6])
    injuries = _injuries([{"player_id": 99, "player_name": "Name Mismatch", "status": STATUS_OUT}])
    override = InjuryOverride(espn_id=99, return_game=2)
    out = project_availability(injuries, model, overrides=[override])
    assert out.iloc[0]["source"] == "override"
    assert out.iloc[0]["p_available_g1"] == 0.0
    assert out.iloc[0]["p_available_g2"] == 1.0


def test_project_availability_falls_back_to_model() -> None:
    model = _model([2, 3, 4, 5, 6])
    injuries = _injuries([{"player_id": 5, "player_name": "No Override", "status": STATUS_OUT}])
    out = project_availability(injuries, model, overrides=[])
    assert out.iloc[0]["source"] == "model"
    assert 0.0 <= out.iloc[0]["availability_multiplier"] <= 1.0


def test_project_availability_healthy_row_is_fully_available() -> None:
    model = _model([2, 3, 4])
    injuries = _injuries([{"player_id": 1, "player_name": "Healthy Guy", "status": STATUS_HEALTHY}])
    out = project_availability(injuries, model, overrides=[])
    assert out.iloc[0]["source"] == "healthy"
    assert out.iloc[0]["availability_multiplier"] == pytest.approx(1.0)


# ── end-to-end training + honest calibration ───────────────────────────────


def _multi_season_archive() -> tuple[pd.DataFrame, pd.DataFrame]:
    tgs: list[pd.DataFrame] = []
    sgs: list[pd.DataFrame] = []
    rng = np.random.default_rng(7)
    for season in (20192020, 20202021, 20212022):
        for t, team in enumerate(("AAA", "BBB")):
            n = 60
            tg = _team_games(season, team, n)
            tgs.append(tg)
            for p in range(6):
                player_id = season * 100 + t * 10 + p
                miss_start = 15 + int(rng.integers(0, 20))
                miss_len = 2 + int(rng.integers(0, 5))
                missed = set(range(miss_start, miss_start + miss_len))
                played = [i for i in range(n) if i not in missed]
                sgs.append(_skater_games(season, team, player_id, played, toi=900.0))
    return pd.concat(sgs, ignore_index=True), pd.concat(tgs, ignore_index=True)


def test_train_return_time_model_end_to_end() -> None:
    skater_games, team_games = _multi_season_archive()
    config = ReturnTimeConfig(
        n_test_seasons=1,
        spell_config=AbsenceSpellConfig(min_appearances=20, min_median_toi=600.0),
    )
    result = train_return_time_model(skater_games, team_games, config=config)

    assert result.n_spells_total > 0
    assert result.n_spells_train + result.n_spells_test == result.n_spells_total
    assert result.mean_spell >= config.spell_config.min_spell
    assert 0.0 <= result.calibration_mae <= 1.0

    manifest = result.manifest()
    assert manifest["model_version"] == "return-time-v1"
    assert manifest["counts"]["spells_total"] == result.n_spells_total

    report = "\n".join(result.report_lines())
    assert "Injury return-time model" in report
    assert report.isascii()

    # The shipped model produces a valid monotone curve.
    curve = result.model.availability_curve(STATUS_OUT)
    assert _is_non_decreasing(curve)


def test_train_return_time_model_empty_raises() -> None:
    empty = pd.DataFrame(
        columns=["season_id", "game_type_id", "game_id", "player_id", "team_abbrev", "toi_seconds"]
    )
    empty_team = pd.DataFrame(
        columns=["season_id", "game_type_id", "game_id", "game_date", "team_abbrev"]
    )
    with pytest.raises(ValueError, match="no absence spells"):
        train_return_time_model(empty, empty_team)
