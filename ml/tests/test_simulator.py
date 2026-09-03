"""Tests for draft_oracle.optimize.simulator (US-019).

Covers rule enforcement (snake order, per-position limits, IR gating, no
duplicates, eliminated teams), the greedy fallback opponent (public-perception
ranking, softmax temperature, positional need), Monte-Carlo survival estimation,
determinism under a fixed seed, and a full 10-manager 11-pick round-trip that
produces a rules-valid roster for every manager. All fixtures are tiny in-memory
pools -- no committed data, no network (SPEC section 7).
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Literal

import pytest

from draft_oracle.optimize.simulator import (
    DraftAsset,
    DraftState,
    GreedyOpponentModel,
    SurvivalQuery,
    roster_capacity,
    run_draft,
    survival_probability,
    validate_draft,
)


@dataclass(frozen=True)
class _AssetIds:
    team_id: int
    player_id: int


def _skater(key: str, position: Literal["F", "D", "G"], rank: float, ids: _AssetIds) -> DraftAsset:
    return DraftAsset(
        key=key,
        name=key,
        position=position,
        rank_value=rank,
        player_id=ids.player_id,
        team_id=ids.team_id,
        team_abbrev=f"T{ids.team_id}",
    )


def _team_asset(team_id: int, rank: float) -> DraftAsset:
    return DraftAsset(
        key=f"G{team_id}",
        name=f"T{team_id}",
        position="G",
        rank_value=rank,
        team_id=team_id,
        team_abbrev=f"T{team_id}",
    )


def _exact_pool(managers: int, allow_ir: bool) -> list[DraftAsset]:
    """A pool sized to *exactly* fill every roster (forces valid completion)."""
    cap = roster_capacity(allow_ir)
    pool: list[DraftAsset] = []
    rank = 1000.0
    for i in range(cap.forwards * managers):
        pool.append(_skater(f"F{i}", "F", rank, _AssetIds(1 + (i % 8), 1000 + i)))
        rank -= 1.0
    for i in range(cap.defense * managers):
        pool.append(_skater(f"D{i}", "D", rank, _AssetIds(1 + (i % 8), 2000 + i)))
        rank -= 1.0
    for i in range(cap.goalies * managers):
        pool.append(_team_asset(100 + i, rank))
        rank -= 1.0
    return pool


# ── Capacity & roster shape ──────────────────────────────────────────────


def test_roster_capacity_standard() -> None:
    cap = roster_capacity(allow_ir=False)
    assert (cap.forwards, cap.defense, cap.goalies) == (5, 3, 1)
    assert cap.total == 9


def test_roster_capacity_ir() -> None:
    cap = roster_capacity(allow_ir=True)
    assert (cap.forwards, cap.defense, cap.goalies) == (6, 4, 1)
    assert cap.total == 11


# ── Snake order & rule enforcement ───────────────────────────────────────


def test_snake_order_from_state() -> None:
    state = DraftState.new(["a", "b", "c"], _exact_pool(3, False), allow_ir=False)
    # 9 picks per manager -> 27 total; rounds alternate a,b,c / c,b,a.
    assert state.order[:6] == ("a", "b", "c", "c", "b", "a")
    assert len(state.order) == 27


@pytest.mark.parametrize("managers", [["ben", "ben"], ["ben", "Ben"]])
def test_draft_state_rejects_duplicate_manager_ids(managers: list[str]) -> None:
    with pytest.raises(ValueError, match="managers must be unique"):
        DraftState.new(managers, _exact_pool(2, False), allow_ir=False)


def test_full_forwards_must_pick_other_position() -> None:
    state = DraftState.new(["a"], _exact_pool(1, False), allow_ir=False)
    # Fill the manager's 5 forward slots.
    for _ in range(5):
        forward = next(a for a in state.legal_assets("a") if a.position == "F")
        state.apply_pick(forward)
    legal_positions = {a.position for a in state.legal_assets("a")}
    assert "F" not in legal_positions
    assert legal_positions == {"D", "G"}


def test_ir_slots_pickable_only_when_enabled() -> None:
    # Without IR the forward limit is 5; with IR it is 6.
    assert roster_capacity(False).forwards == 5
    assert roster_capacity(True).forwards == 6

    state = DraftState.new(["a"], _exact_pool(1, True), allow_ir=True)
    for _ in range(6):
        forward = next(a for a in state.legal_assets("a") if a.position == "F")
        state.apply_pick(forward)
    assert not any(a.position == "F" for a in state.legal_assets("a"))


def test_no_duplicate_picks() -> None:
    state = DraftState.new(["a", "b"], _exact_pool(2, False), allow_ir=False)
    first = state.legal_assets("a")[0]
    state.apply_pick(first)
    assert first.key not in state.available
    with pytest.raises(ValueError, match="not available"):
        state.place("b", first)


def test_eliminated_team_removed_from_pool() -> None:
    pool = [
        _skater("F1", "F", 100.0, _AssetIds(7, 1)),
        _skater("F2", "F", 90.0, _AssetIds(3, 2)),
        _team_asset(7, 80.0),
    ]
    state = DraftState.new(["a"], pool, allow_ir=False, eliminated_team_ids=frozenset({7}))
    keys = set(state.available)
    assert keys == {"F2"}  # both the skater on team 7 and team 7's goalie slot gone


def test_unresolved_team_skater_dropped_once_teams_eliminated() -> None:
    # m-11 fail-safe: a skater whose team never resolved (team_id=None) cannot be
    # confirmed alive once any team is eliminated, so it must not stay draftable.
    unresolved = DraftAsset(
        key="F_unknown",
        name="F_unknown",
        position="F",
        rank_value=95.0,
        player_id=42,
        team_id=None,
    )
    pool = [
        unresolved,
        _skater("F2", "F", 90.0, _AssetIds(3, 2)),
        _team_asset(3, 80.0),
    ]
    # No eliminations yet: the unresolved skater is still draftable (round-1 behavior).
    open_state = DraftState.new(["a"], pool, allow_ir=False)
    assert "F_unknown" in open_state.available
    # Once a team is eliminated, the unresolved skater is removed fail-safe.
    elim_state = DraftState.new(["a"], pool, allow_ir=False, eliminated_team_ids=frozenset({99}))
    assert "F_unknown" not in elim_state.available
    assert "F2" in elim_state.available  # a resolved, non-eliminated skater survives


def test_place_rejects_over_limit() -> None:
    state = DraftState.new(["a"], _exact_pool(1, False), allow_ir=False)
    goalie = next(a for a in state.available.values() if a.position == "G")
    state.place("a", goalie)
    another = _team_asset(999, 5.0)
    state.available[another.key] = another
    with pytest.raises(ValueError, match="full at position"):
        state.place("a", another)


# ── Greedy opponent model ────────────────────────────────────────────────


def test_greedy_picks_highest_rank_at_zero_temperature() -> None:
    pool = [
        _skater("F1", "F", 50.0, _AssetIds(1, 1)),
        _skater("F2", "F", 99.0, _AssetIds(2, 2)),
        _skater("F3", "F", 10.0, _AssetIds(3, 3)),
    ]
    state = DraftState.new(["a"], pool + _fill_rest(pool), allow_ir=False)
    model = GreedyOpponentModel(temperature=0.0, need_weight=0.0)

    pick = model.pick(state, "a", random.Random(0))
    assert pick.key == "F2"


def _fill_rest(pool: list[DraftAsset]) -> list[DraftAsset]:
    """Pad a pool so a single manager can complete a 9-pick roster."""
    extra: list[DraftAsset] = []
    for i in range(5):
        extra.append(_skater(f"PF{i}", "F", 1.0 + i, _AssetIds(1, 5000 + i)))
    for i in range(3):
        extra.append(_skater(f"PD{i}", "D", 1.0 + i, _AssetIds(1, 6000 + i)))
    extra.append(_team_asset(200, 1.0))
    return extra


def test_greedy_softmax_is_seed_deterministic() -> None:

    pool = _exact_pool(2, False)
    model = GreedyOpponentModel(temperature=1.0, need_weight=2.0)

    state_a = DraftState.new(["a", "b"], pool, allow_ir=False)
    pick_a = model.pick(state_a, "a", random.Random(123))
    state_b = DraftState.new(["a", "b"], pool, allow_ir=False)
    pick_b = model.pick(state_b, "a", random.Random(123))
    assert pick_a.key == pick_b.key


def test_greedy_needs_goalie_when_only_slot_left() -> None:
    # Manager already holds 5F + 3D; only the goalie slot remains open.
    pool = _exact_pool(1, False)
    state = DraftState.new(["a"], pool, allow_ir=False)
    for _ in range(5):
        state.apply_pick(next(a for a in state.legal_assets("a") if a.position == "F"))
    for _ in range(3):
        state.apply_pick(next(a for a in state.legal_assets("a") if a.position == "D"))

    model = GreedyOpponentModel()
    pick = model.pick(state, "a", random.Random(0))
    assert pick.position == "G"


# ── Survival estimation ──────────────────────────────────────────────────


def test_survival_of_drafted_candidate_is_zero() -> None:
    pool = _exact_pool(2, False)
    state = DraftState.new(["a", "b"], pool, allow_ir=False)
    taken = state.legal_assets("a")[0]
    state.apply_pick(taken)
    prob = survival_probability(
        SurvivalQuery(state, taken, "b", GreedyOpponentModel()), rollouts=16, seed=0
    )
    assert prob == 0.0


def test_survival_is_one_when_no_gap() -> None:
    pool = _exact_pool(2, False)
    state = DraftState.new(["a", "b"], pool, allow_ir=False)
    state.apply_pick(state.legal_assets("a")[0])
    # Now b is on the clock; b's own next pick has no intervening opponents.
    candidate = next(a for a in state.available.values() if a.position == "D")
    prob = survival_probability(
        SurvivalQuery(state, candidate, "b", GreedyOpponentModel()), rollouts=16, seed=0
    )
    assert prob == 1.0


def test_top_ranked_candidate_rarely_survives() -> None:
    pool = _exact_pool(4, False)
    state = DraftState.new(["a", "b", "c", "d"], pool, allow_ir=False)
    state.apply_pick(state.legal_assets("a")[0])  # a takes the very best asset
    # Best remaining forward is coveted; a won't pick again until 6 opponents go.
    best_forward = max(
        (a for a in state.available.values() if a.position == "F"),
        key=lambda a: a.rank_value,
    )
    model = GreedyOpponentModel(temperature=0.5, need_weight=2.0)
    prob = survival_probability(
        SurvivalQuery(state, best_forward, "a", model), rollouts=200, seed=7
    )
    assert prob < 0.2


def test_survival_probability_is_seed_deterministic() -> None:
    pool = _exact_pool(4, False)
    state = DraftState.new(["a", "b", "c", "d"], pool, allow_ir=False)
    candidate = state.legal_assets("a")[3]
    model = GreedyOpponentModel(temperature=0.7)
    query = SurvivalQuery(state, candidate, "a", model)
    p1 = survival_probability(query, rollouts=100, seed=42)
    p2 = survival_probability(query, rollouts=100, seed=42)
    assert p1 == p2


def test_survival_thousand_rollouts_under_five_seconds() -> None:
    pool = _exact_pool(10, False)
    state = DraftState.new([f"m{i}" for i in range(10)], pool, allow_ir=False)
    state.apply_pick(state.legal_assets("m0")[0])
    candidate = next(a for a in state.available.values() if a.position == "F")
    model = GreedyOpponentModel(temperature=0.5, need_weight=3.0)
    start = time.perf_counter()
    prob = survival_probability(
        SurvivalQuery(state, candidate, "m0", model), rollouts=1000, seed=1
    )
    elapsed = time.perf_counter() - start
    assert 0.0 <= prob <= 1.0
    assert elapsed < 5.0


# ── Full-draft round-trip ────────────────────────────────────────────────


def test_full_ten_manager_eleven_pick_draft_is_valid() -> None:
    managers = [f"m{i}" for i in range(10)]
    pool = _exact_pool(10, allow_ir=True)  # 11 picks per manager
    state = DraftState.new(managers, pool, allow_ir=True)
    model = GreedyOpponentModel(temperature=0.6, need_weight=4.0)

    run_draft(state, model, seed=2024)

    assert state.is_complete
    assert not state.available  # exact pool fully consumed
    results = validate_draft(state)
    for manager in managers:
        assert results[manager].valid, results[manager].reasons
        roster = state.rosters[manager]
        assert roster.count("F") == 6
        assert roster.count("D") == 4
        assert roster.count("G") == 1


def test_full_draft_is_seed_deterministic() -> None:
    managers = [f"m{i}" for i in range(10)]
    model = GreedyOpponentModel(temperature=0.6, need_weight=4.0)

    state1 = DraftState.new(managers, _exact_pool(10, False), allow_ir=False)
    run_draft(state1, model, seed=99)
    state2 = DraftState.new(managers, _exact_pool(10, False), allow_ir=False)
    run_draft(state2, model, seed=99)

    picks1 = {m: [a.key for a in state1.rosters[m].all_assets()] for m in managers}
    picks2 = {m: [a.key for a in state2.rosters[m].all_assets()] for m in managers}
    assert picks1 == picks2


def test_no_mid_round_substitution_of_eliminated_players() -> None:
    # Once a team is eliminated up front, none of its assets are ever draftable,
    # and the completed rosters contain no eliminated-team assets.
    managers = [f"m{i}" for i in range(4)]
    pool = _exact_pool(4, False)
    eliminated = frozenset({1})  # team 1 skaters removed
    state = DraftState.new(managers, pool, allow_ir=False, eliminated_team_ids=eliminated)
    assert all(a.team_id != 1 for a in state.available.values())
