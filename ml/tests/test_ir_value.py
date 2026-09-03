"""Tests for draft_oracle.optimize.ir_value (US-022).

Covers the retroactive same-position swap math on hand-computed early/no/late-return
scenarios, the Monte-Carlo stash EV composition (US-015 availability + US-016
production), the stash/avoid verdict against the healthy replacement-level
alternative, the cheat-sheet IR section, and the optimizer pool repricing. All
fixtures are tiny and deterministic -- no committed data, no network (SPEC section 7).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np
import pytest

from draft_oracle.optimize.ir_value import (
    StashInput,
    _StashSimulationInput,
    _StashValueRequest,
    build_stash_valuations,
    healthy_alternative_value,
    render_ir_section,
    reprice_pool_for_ir,
    retroactive_swap_points,
    round_points_with_return,
    simulate_stash_samples,
    value_stash,
)
from draft_oracle.optimize.simulator import DraftAsset

# ── Retroactive swap primitive (hand-computed) ───────────────────────────


def test_retroactive_swap_keeps_the_higher_scorer() -> None:
    # Activation replaces the starter for the whole round -> keep whichever scored more.
    assert retroactive_swap_points(6.0, 3.0) == 6.0
    assert retroactive_swap_points(1.0, 3.0) == 3.0
    assert retroactive_swap_points(3.0, 3.0) == 3.0


def test_round_points_early_return_plays_whole_series() -> None:
    # Returns game 1 of a 6-game series, 1 pt/game -> 6 points.
    per_game = [1.0] * 7
    assert round_points_with_return(per_game, series_length=6, return_game=1) == 6.0


def test_round_points_no_return_scores_zero() -> None:
    # Never returns within the series (return game past its length) -> 0 points.
    per_game = [1.0] * 7
    assert round_points_with_return(per_game, series_length=6, return_game=8) == 0.0


def test_round_points_late_return_plays_only_tail() -> None:
    # Returns game 6 of a 6-game series -> only that game's points.
    per_game = [2.0] * 7
    assert round_points_with_return(per_game, series_length=6, return_game=6) == 2.0


def test_hand_computed_swap_early_no_late() -> None:
    per_game = [1.0] * 7
    baseline = 3.0
    early = round_points_with_return(per_game, 6, 1)  # 6
    none = round_points_with_return(per_game, 6, 8)  # 0
    late = round_points_with_return(per_game, 6, 6)  # 1
    # Early return outscores the starter -> activate; no/late return keep the starter.
    assert retroactive_swap_points(early, baseline) == 6.0
    assert retroactive_swap_points(none, baseline) == 3.0
    assert retroactive_swap_points(late, baseline) == 3.0
    # A weaker starter flips the late-return decision to an activation.
    assert retroactive_swap_points(late, 0.5) == 1.0


# ── Monte-Carlo stash EV composition ─────────────────────────────────────

_LENGTH_7 = {7: 1.0}


def test_never_available_stash_ev_equals_baseline() -> None:
    # An all-zero availability curve means the stash never plays -> keep the starter.
    curve = [0.0] * 7
    stash_ev, stash_value, activation = value_stash(
        _StashValueRequest(2.0, _LENGTH_7, curve, 3.0),
        seed=1,
        n_sims=2000,
    )
    assert stash_ev == pytest.approx(3.0)
    assert stash_value == pytest.approx(0.0)
    assert activation == pytest.approx(0.0)


def test_healthy_high_scorer_beats_a_weak_baseline() -> None:
    # Fully available, high per-game rate, weak starter -> big stash value, near-always
    # activated.
    curve = [1.0] * 7
    stash_ev, stash_value, activation = value_stash(
        _StashValueRequest(1.5, _LENGTH_7, curve, 1.0),
        seed=7,
        n_sims=4000,
    )
    assert stash_value > 0.0
    assert stash_ev > 1.0
    assert activation > 0.9


def test_value_stash_is_deterministic_given_seed() -> None:
    first = value_stash(
        _StashValueRequest(1.0, _LENGTH_7, [0.5] * 7, 2.0),
        seed=42,
        n_sims=1500,
    )
    second = value_stash(
        _StashValueRequest(1.0, _LENGTH_7, [0.5] * 7, 2.0),
        seed=42,
        n_sims=1500,
    )
    assert first == second


def test_simulate_stash_samples_shape_and_nonnegative() -> None:
    rng = np.random.default_rng(0)
    samples = simulate_stash_samples(
        rng,
        _StashSimulationInput(1.0, _LENGTH_7, [1.0] * 7),
        n_sims=500,
        horizon=7,
    )
    assert samples.shape == (500,)
    assert float(samples.min()) >= 0.0


def test_earlier_return_is_worth_at_least_as_much() -> None:
    # A curve that is available earlier weakly dominates a later one -> >= stash value.
    early = [1.0] * 7
    late = [0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0]
    _ev_e, value_early, _a = value_stash(
        _StashValueRequest(1.2, _LENGTH_7, early, 2.0),
        seed=3,
        n_sims=6000,
    )
    _ev_l, value_late, _b = value_stash(
        _StashValueRequest(1.2, _LENGTH_7, late, 2.0),
        seed=3,
        n_sims=6000,
    )
    assert value_early >= value_late - 1e-9


# ── Healthy alternative + verdicts ───────────────────────────────────────


def test_healthy_alternative_value_is_small_and_nonnegative() -> None:
    # A replacement-level healthy body only adds upside variance over the same-level
    # starter, so its marginal IR value is small but never negative.
    value = healthy_alternative_value(3.0, _LENGTH_7, seed=5, n_sims=4000)
    assert value >= 0.0
    assert value < 3.0


def _input(
    case: _StashCase,
) -> StashInput:
    return StashInput(
        player_id=case.player_id,
        player_name=case.name,
        position=case.position,
        team_abbrev="AAA",
        status="out",
        pts_per_game=case.pts_per_game,
        length_probs=_LENGTH_7,
        availability_curve=case.curve,
        expected_games_available=float(sum(case.curve)),
    )


@dataclass(frozen=True)
class _StashCase:
    player_id: int
    position: str
    pts_per_game: float
    curve: list[float]
    name: str = "P"


def test_build_valuations_verdicts_and_ordering() -> None:
    star = _input(_StashCase(1, "F", 1.6, [1.0] * 7, name="Star"))
    scrub = _input(
        _StashCase(2, "F", 0.1, [0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0], name="Scrub")
    )
    replacement = {"F": 1.2, "D": 0.8}
    vals = build_stash_valuations([scrub, star], replacement, seed=11, n_sims=6000)

    by_id = {v.player_id: v for v in vals}
    assert by_id[1].verdict == "stash"
    assert by_id[2].verdict == "avoid"
    # Ranked by stash value descending -> the star comes first.
    assert [v.player_id for v in vals] == [1, 2]
    # F swaps the F replacement level (SPEC: same-position swap enforced).
    assert by_id[1].active_baseline == pytest.approx(1.2)


def test_defense_swaps_defense_baseline() -> None:
    d = _input(_StashCase(9, "D", 1.0, [1.0] * 7))
    vals = build_stash_valuations([d], {"F": 5.0, "D": 0.5}, seed=1, n_sims=1000)
    assert vals[0].active_baseline == pytest.approx(0.5)


# ── Cheat-sheet IR section ───────────────────────────────────────────────


def test_render_ir_section_empty_is_blank() -> None:
    assert render_ir_section([]) == []


def test_render_ir_section_is_ascii_with_verdict() -> None:
    star = _input(_StashCase(1, "F", 1.6, [1.0] * 7, name="Star"))
    vals = build_stash_valuations([star], {"F": 1.0, "D": 1.0}, seed=1, n_sims=1000)
    lines = render_ir_section(vals)
    text = "\n".join(lines)
    assert "IR stash candidates" in text
    assert "Verdict" in text
    assert "stash" in text
    # ASCII only (Windows cp1252 console safety, SPEC honesty rules).
    assert text.encode("ascii")


# ── Optimizer pool repricing ─────────────────────────────────────────────


def _asset(player_id: int, position: Literal["F", "D", "G"], projection: float) -> DraftAsset:
    return DraftAsset(
        key=f"P{player_id}",
        name=f"P{player_id}",
        position=position,
        rank_value=projection,
        player_id=player_id,
        team_abbrev="AAA",
        projection=projection,
    )


def test_reprice_pool_for_ir_only_touches_injured() -> None:
    pool = [_asset(1, "F", 10.0), _asset(2, "D", 8.0)]
    repriced = reprice_pool_for_ir(pool, {1: 2.5})
    by_id = {a.player_id: a for a in repriced}
    # The injured star is repriced down to its stash value; the healthy asset is intact.
    assert by_id[1].projection == pytest.approx(2.5)
    assert by_id[1].rank_value == pytest.approx(2.5)
    assert by_id[2].projection == pytest.approx(8.0)


def test_reprice_pool_preserves_length_and_identity() -> None:
    pool = [_asset(1, "F", 10.0), _asset(2, "D", 8.0)]
    repriced = reprice_pool_for_ir(pool, {1: 2.5})
    assert len(repriced) == len(pool)
    assert {a.key for a in repriced} == {a.key for a in pool}


def test_no_return_stash_is_worthless_to_the_optimizer() -> None:
    # A stash that never plays has zero stash value -> the optimizer prices it at ~0.
    hurt = _input(_StashCase(1, "F", 3.0, [0.0] * 7))
    vals = build_stash_valuations([hurt], {"F": 4.0, "D": 4.0}, seed=1, n_sims=1000)
    assert math.isclose(vals[0].stash_value, 0.0, abs_tol=1e-9)
    repriced = reprice_pool_for_ir([_asset(1, "F", 12.0)], {1: vals[0].stash_value})
    assert repriced[0].projection == pytest.approx(0.0)
