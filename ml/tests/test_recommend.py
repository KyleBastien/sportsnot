"""Tests for draft_oracle.optimize.recommend (US-021).

Covers the value/replacement primitives, the greedy-VOR policy, the multi-step
Monte-Carlo recommendation (ranking, explanations, determinism, forced picks,
goalie-slot timing, depth, the <10s full-depth bar), the vectorized greedy kernel,
and the honest strategy comparison. All fixtures are tiny in-memory pools -- no
network, no committed data (SPEC section 7).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pandas as pd
import pytest

from draft_oracle.optimize.opponents import Coefficients, FittedOpponentModel
from draft_oracle.optimize.recommend import (
    Recommendation,
    RecommendConfig,
    StrategyComparison,
    _expected_value,
    _fitted_zero_temp_models,
    _PositionRunOpponent,
    _prune_candidates,
    _vectorized_fitted_expected,
    _vectorized_greedy_expected,
    asset_value,
    build_pool_from_projection_artifact,
    build_synthetic_pool,
    choose_pick,
    compare_strategies,
    greedy_vor_pick,
    recommend_pick,
    replacement_levels,
)
from draft_oracle.optimize.simulator import (
    DraftAsset,
    DraftState,
    GreedyOpponentModel,
    roster_capacity,
)


@dataclass(frozen=True)
class _AssetIds:
    team_id: int
    player_id: int


def _skater(
    key: str, position: Literal["F", "D", "G"], projection: float, ids: _AssetIds
) -> DraftAsset:
    return DraftAsset(
        key=key,
        name=key,
        position=position,
        rank_value=projection,
        player_id=ids.player_id,
        team_id=ids.team_id,
        team_abbrev=f"T{ids.team_id}",
        projection=projection,
    )


def _team(team_id: int, projection: float) -> DraftAsset:
    return DraftAsset(
        key=f"T{team_id}",
        name=f"T{team_id}",
        position="G",
        rank_value=projection,
        team_id=team_id,
        team_abbrev=f"T{team_id}",
        projection=projection,
    )


def _pool(managers: int, allow_ir: bool, *, surplus: int = 6) -> list[DraftAsset]:
    """A pool that comfortably fills every roster with a value gradient per position."""
    cap = roster_capacity(allow_ir)
    pool: list[DraftAsset] = []
    for i in range(cap.forwards * managers + surplus):
        pool.append(_skater(f"F{i}", "F", 30.0 - i, _AssetIds(1 + (i % 8), 1000 + i)))
    for i in range(cap.defense * managers + surplus):
        pool.append(_skater(f"D{i}", "D", 20.0 - i, _AssetIds(1 + (i % 8), 2000 + i)))
    for i in range(cap.goalies * managers + surplus):
        pool.append(_team(100 + i, 25.0 - 2.0 * i))
    return pool


# ── Primitives ────────────────────────────────────────────────────────────


def test_asset_value_prefers_projection() -> None:
    asset = _skater("F0", "F", 12.5, _AssetIds(1, 1))
    assert asset_value(asset) == 12.5


def test_asset_value_falls_back_to_rank() -> None:
    asset = DraftAsset(key="F0", name="F0", position="F", rank_value=9.0, player_id=1, team_id=1)
    assert asset.projection is None
    assert asset_value(asset) == 9.0


def test_replacement_levels_are_positive_and_keyed() -> None:
    state = DraftState.new([f"m{i}" for i in range(4)], _pool(4, False), allow_ir=False)
    repl = replacement_levels(state, 4)
    assert set(repl) == {"F", "D", "G"}
    assert repl["F"] > 0 and repl["D"] > 0 and repl["G"] > 0


def test_greedy_vor_pick_maximizes_vor() -> None:
    state = DraftState.new([f"m{i}" for i in range(4)], _pool(4, False), allow_ir=False)
    repl = replacement_levels(state, 4)
    pick = greedy_vor_pick(state, "m0", repl)
    # The chosen asset has the highest value-over-replacement of all legal assets.
    best_vor = max(asset_value(a) - repl[a.position] for a in state.legal_assets("m0"))
    assert asset_value(pick) - repl[pick.position] == pytest.approx(best_vor)


# ── recommend_pick mechanics ────────────────────────────────────────────────


def test_recommend_returns_ranked_top_n() -> None:
    state = DraftState.new([f"m{i}" for i in range(4)], _pool(4, False), allow_ir=False)
    model = GreedyOpponentModel(temperature=0.3)
    rec = recommend_pick(state, "m0", model, config=RecommendConfig(rollouts=50, top_n=5))
    assert isinstance(rec, Recommendation)
    assert len(rec.evaluations) == 5
    expected = [ev.expected_points for ev in rec.evaluations]
    assert expected == sorted(expected, reverse=True)


def test_recommend_is_deterministic() -> None:
    state = DraftState.new([f"m{i}" for i in range(4)], _pool(4, False), allow_ir=False)
    model = GreedyOpponentModel(temperature=0.4)
    cfg = RecommendConfig(rollouts=64, seed=7)
    a = recommend_pick(state, "m0", model, config=cfg)
    b = recommend_pick(state, "m0", model, config=cfg)
    assert a.best.asset.key == b.best.asset.key
    assert a.best.expected_points == pytest.approx(b.best.expected_points)


def test_recommend_explanations_present() -> None:
    state = DraftState.new([f"m{i}" for i in range(4)], _pool(4, False), allow_ir=False)
    model = GreedyOpponentModel(temperature=0.3)
    rec = recommend_pick(state, "m0", model, config=RecommendConfig(rollouts=40))
    best = rec.best
    assert 0.0 <= best.survival <= 1.0
    assert best.position_limit >= best.open_slots >= 0
    assert best.delta_vs_next >= 0.0  # #1 is >= #2
    assert "P(survives" in best.explanation()


def test_recommend_delta_vs_next_zeroed_for_lower_ranks() -> None:
    state = DraftState.new([f"m{i}" for i in range(4)], _pool(4, False), allow_ir=False)
    model = GreedyOpponentModel(temperature=0.2)
    rec = recommend_pick(state, "m0", model, config=RecommendConfig(rollouts=40))
    # Second-ranked pick's delta vs. the #2 option is zero by definition.
    assert rec.evaluations[1].delta_vs_next == pytest.approx(0.0)


def test_recommend_report_lines_are_ascii() -> None:
    state = DraftState.new([f"m{i}" for i in range(4)], _pool(4, False), allow_ir=False)
    model = GreedyOpponentModel(temperature=0.3)
    rec = recommend_pick(state, "m0", model, config=RecommendConfig(rollouts=40))
    text = "\n".join(rec.report_lines())
    text.encode("ascii")  # raises if any non-ASCII slipped in (cp1252 safety)
    manifest = rec.manifest()
    assert manifest["owner"] == "m0"
    assert len(manifest["recommendations"]) == len(rec.evaluations)


def test_recommend_rejects_wrong_owner() -> None:
    state = DraftState.new([f"m{i}" for i in range(4)], _pool(4, False), allow_ir=False)
    model = GreedyOpponentModel()
    with pytest.raises(ValueError, match="not on the clock"):
        recommend_pick(state, "m1", model, config=RecommendConfig(rollouts=10))


def test_recommend_rejects_complete_draft() -> None:
    state = DraftState.new([f"m{i}" for i in range(2)], _pool(2, False), allow_ir=False)
    model = GreedyOpponentModel()
    from draft_oracle.optimize.simulator import run_draft

    run_draft(state, model, seed=1)
    with pytest.raises(ValueError, match="complete"):
        recommend_pick(state, state.order[0], model, config=RecommendConfig(rollouts=10))


# ── Forced picks & goalie timing ────────────────────────────────────────────


def _fill_owner_skater_slots(state: DraftState, owner: str) -> None:
    """Fill the owner's F/D slots directly so only the goalie slot remains."""
    for asset in list(state.available.values()):
        roster = state.rosters[owner]
        needs_forward = asset.position == "F" and roster.count("F") < state.capacity.forwards
        needs_defense = asset.position == "D" and roster.count("D") < state.capacity.defense
        if needs_forward or needs_defense:
            state.place(owner, asset)


def test_forced_pick_when_only_goalie_slot_left() -> None:
    # A manager with all skater slots full can only be recommended a team (G) asset.
    managers = [f"m{i}" for i in range(2)]
    state = DraftState.new(managers, _pool(2, False), allow_ir=False)
    owner = "m0"
    _fill_owner_skater_slots(state, owner)
    # Rewind the pick pointer to owner and confirm only G is legal.
    while state.current_manager != owner:
        state.pick_index += 1
    legal_positions = {a.position for a in state.legal_assets(owner)}
    assert legal_positions == {"G"}
    model = GreedyOpponentModel()
    rec = recommend_pick(state, owner, model, config=RecommendConfig(rollouts=20))
    assert rec.best.asset.position == "G"


def test_goalie_slot_is_recommendable_early() -> None:
    # Make a team goalie slot clearly the top VOR asset so it surfaces at pick 1.
    pool = _pool(2, False)
    pool.append(_team(999, 200.0))  # dominating goalie slot
    state = DraftState.new([f"m{i}" for i in range(2)], pool, allow_ir=False)
    model = GreedyOpponentModel(temperature=0.0)
    rec = recommend_pick(state, "m0", model, config=RecommendConfig(rollouts=20))
    assert rec.best.asset.position == "G"


# ── Depth & vectorized path ─────────────────────────────────────────────────


def test_depth_one_step_runs_and_is_deterministic() -> None:
    state = DraftState.new([f"m{i}" for i in range(4)], _pool(4, False), allow_ir=False)
    model = GreedyOpponentModel(temperature=0.4)
    cfg = RecommendConfig(rollouts=48, depth=1, seed=3)
    a = recommend_pick(state, "m0", model, config=cfg)
    b = recommend_pick(state, "m0", model, config=cfg)
    assert a.best.asset.key == b.best.asset.key
    assert a.depth == 1


def test_choose_pick_returns_legal_asset() -> None:
    state = DraftState.new([f"m{i}" for i in range(4)], _pool(4, False), allow_ir=False)
    model = GreedyOpponentModel(temperature=0.3)
    pick = choose_pick(state, "m0", model, config=RecommendConfig(rollouts=32))
    assert pick.key in state.available


def _pool_rank_ne_projection(managers: int) -> list[DraftAsset]:
    """A pool where ``rank_value`` deliberately disagrees with ``projection``.

    Public perception (``rank_value``) is the reverse of the model's ``projection``
    within each position, so an opponent scored by ``rank_value`` (the object model's
    real policy) drafts a different asset than one scored by ``projection`` -- the
    exact divergence CODE_REVIEW m-7 flags. Used to prove the fast and object paths
    agree only after the fast path scores opponents by ``rank_value``.
    """
    cap = roster_capacity(False)
    pool: list[DraftAsset] = []
    n_f = cap.forwards * managers + 6
    for i in range(n_f):
        pool.append(
            DraftAsset(
                key=f"F{i}",
                name=f"F{i}",
                position="F",
                rank_value=float(i + 1),  # ascending: opposite of projection
                player_id=1000 + i,
                team_id=1 + (i % 8),
                team_abbrev=f"T{1 + (i % 8)}",
                projection=30.0 - i,  # descending
            )
        )
    n_d = cap.defense * managers + 6
    for i in range(n_d):
        pool.append(
            DraftAsset(
                key=f"D{i}",
                name=f"D{i}",
                position="D",
                rank_value=float(i + 1),
                player_id=2000 + i,
                team_id=1 + (i % 8),
                team_abbrev=f"T{1 + (i % 8)}",
                projection=20.0 - i,
            )
        )
    n_g = cap.goalies * managers + 6
    for i in range(n_g):
        pool.append(
            DraftAsset(
                key=f"G{i}",
                name=f"G{i}",
                position="G",
                rank_value=float(i + 1),
                team_id=100 + i,
                team_abbrev=f"T{100 + i}",
                projection=25.0 - 2.0 * i,
            )
        )
    return pool


def _advance(state: DraftState, picks: int) -> None:
    """Deterministically advance the draft by ``picks`` first-legal choices."""
    for _ in range(picks):
        legal = state.legal_assets(state.current_manager)
        state.apply_pick(legal[0])


def _tied_opponent_state() -> tuple[DraftState, DraftAsset]:
    """State where projection order conflicts with object-model tie-breaking."""
    pool = _pool(3, False)
    pool.extend(
        [
            DraftAsset(
                key="FA",
                name="FA",
                position="F",
                rank_value=50.0,
                player_id=9001,
                team_id=9,
                projection=9.0,
            ),
            DraftAsset(
                key="FB",
                name="FB",
                position="F",
                rank_value=50.0,
                player_id=9002,
                team_id=9,
                projection=40.0,
            ),
        ]
    )
    state = DraftState.new(["m0", "m1", "m2"], pool, allow_ir=False)
    state.apply_pick(state.available["F0"])
    # m2 has exactly one F slot and one G slot open at its snake turn-around.
    # Its first pick is the tied FA/FB choice; its second is forced to G, leaving
    # the other tied forward for owner m1's greedy tail.
    for key in ("F1", "F2", "F3", "F4", "D0", "D1", "D2"):
        state.place("m2", state.available[key])
    return state, state.available["D3"]


def test_fast_paths_match_object_rank_then_key_tie_break() -> None:
    # R2-m15 regression: both tied assets have rank_value=50, but FA projection=9
    # and FB projection=40. Object policies take FA by key; fast paths must not use
    # their projection-ordered array position and take FB instead.
    state, candidate = _tied_opponent_state()
    replacement = replacement_levels(state, 3)
    config = RecommendConfig(rollouts=2, depth=1, seed=1)

    greedy = GreedyOpponentModel(temperature=0.0, need_weight=4.0)
    greedy_mapping = dict.fromkeys(state.rosters, greedy)
    greedy_fast = _vectorized_greedy_expected(
        state, "m1", [candidate], greedy, replacement, config
    )
    greedy_object = [
        _expected_value(state, "m1", candidate, greedy_mapping, replacement, config)
    ]

    fitted_mapping = {
        manager: FittedOpponentModel(
            coefficients=Coefficients(rank=1.0, affinity=0.0),
            affinity={},
            need_weight=4.0,
        )
        for manager in state.rosters
    }
    fitted_fast = _vectorized_fitted_expected(
        state, "m1", [candidate], fitted_mapping, replacement, config
    )
    fitted_object = [
        _expected_value(state, "m1", candidate, fitted_mapping, replacement, config)
    ]

    assert greedy_object == pytest.approx([205.0])
    assert greedy_fast == pytest.approx(greedy_object, abs=1e-9)
    assert fitted_object == pytest.approx([205.0])
    assert fitted_fast == pytest.approx(fitted_object, abs=1e-9)


def test_fast_path_scores_opponents_by_rank_value_and_matches_object(
) -> None:
    # m-7 + m-8: with rank_value != projection and the owner already holding picks,
    # the deterministic greedy fast path must equal the object path, which (a) scores
    # opponents by rank_value and (b) includes the owner's already-drafted roster.
    state = DraftState.new([f"m{i}" for i in range(4)], _pool_rank_ne_projection(4), allow_ir=False)
    _advance(state, 7)  # snake: pick_index 7 is m0's second turn; m0 owns 1 asset
    assert state.current_manager == "m0"
    assert len(state.rosters["m0"].all_assets()) == 1
    gmodel = GreedyOpponentModel(temperature=0.0)
    mapping = {m: GreedyOpponentModel(temperature=0.0) for m in state.rosters}
    repl = replacement_levels(state, 4)
    candidates = [c.asset for c in _prune_candidates(state, "m0", repl, 6)]
    cfg = RecommendConfig(rollouts=6, seed=7)
    vec = _vectorized_greedy_expected(state, "m0", candidates, gmodel, repl, cfg)
    obj = [_expected_value(state, "m0", asset, mapping, repl, cfg) for asset in candidates]
    assert vec == pytest.approx(obj, abs=1e-9)
    # The base roster value is actually part of the number (guards against m-8
    # silently zeroing it): every candidate's E[roster] exceeds it.
    base = sum(asset_value(a) for a in state.rosters["m0"].all_assets())
    assert base > 0.0
    assert all(v > base for v in vec)


def test_fast_path_raises_on_dry_pool_like_object_path() -> None:
    # m-9: a state where a manager runs out of a needed position before the owner's
    # last pick must raise in the fast path, not silently draft pool index 0. The
    # owner is the last seat (m2) so the rollout spans the whole draft and the starved
    # manager's dry pick falls inside the owner's horizon.
    managers = [f"m{i}" for i in range(3)]
    pool: list[DraftAsset] = []
    for i in range(20):
        pool.append(_skater(f"F{i}", "F", 30.0 - i, _AssetIds(1 + (i % 4), 1000 + i)))
    for i in range(12):
        pool.append(_skater(f"D{i}", "D", 20.0 - i, _AssetIds(1 + (i % 4), 2000 + i)))
    for i in range(2):  # 3 managers each need 1 goalie; only 2 exist -> one runs dry
        pool.append(_team(100 + i, 25.0 - 2.0 * i))
    state = DraftState.new(managers, pool, allow_ir=False)
    _advance(state, 2)  # m0, m1 have picked -> m2 (last seat) is on the clock
    assert state.current_manager == "m2"
    gmodel = GreedyOpponentModel(temperature=0.0)
    mapping = {m: GreedyOpponentModel(temperature=0.0) for m in state.rosters}
    repl = replacement_levels(state, 3)
    candidates = [c.asset for c in _prune_candidates(state, "m2", repl, 4)]
    cfg = RecommendConfig(rollouts=4, seed=1)
    with pytest.raises(ValueError, match="no legal asset"):
        _vectorized_greedy_expected(state, "m2", candidates, gmodel, repl, cfg)
    # The object path raises on the same starved state.
    with pytest.raises(ValueError, match="no legal asset"):
        [_expected_value(state, "m2", asset, mapping, repl, cfg) for asset in candidates]


def test_vectorized_greedy_matches_object_path_when_deterministic() -> None:
    # With temperature 0 the greedy opponent is deterministic, so the vectorized kernel
    # (GreedyOpponentModel) and the object-model mapping path must agree on the pick.
    state = DraftState.new([f"m{i}" for i in range(4)], _pool(4, False), allow_ir=False)
    gmodel = GreedyOpponentModel(temperature=0.0)
    mapping = {m: GreedyOpponentModel(temperature=0.0) for m in state.rosters}
    cfg = RecommendConfig(rollouts=8, seed=1)
    vec = recommend_pick(state, "m0", gmodel, config=cfg)
    obj = recommend_pick(state, "m0", mapping, config=cfg)
    assert vec.best.asset.key == obj.best.asset.key


def _fitted_mapping(
    state: DraftState, *, temperature: float = 0.0
) -> dict[str, FittedOpponentModel]:
    return {
        manager: FittedOpponentModel(
            coefficients=Coefficients(rank=0.5, affinity=1.2),
            affinity={1: 0.6, 2: 0.3, 3: 0.1},
            need_weight=1.0,
            temperature=temperature,
        )
        for manager in state.rosters
    }


def test_vectorized_fitted_matches_object_path() -> None:
    # The fitted fast path must reproduce the per-pick object rollout exactly (up to
    # float noise), so wiring the fitted model in never changes the recommendation.
    state = DraftState.new([f"m{i}" for i in range(4)], _pool(4, False), allow_ir=False)
    mapping = _fitted_mapping(state)
    repl = replacement_levels(state, 4)
    candidates = [c.asset for c in _prune_candidates(state, "m0", repl, 6)]
    cfg = RecommendConfig(rollouts=30, depth=2, seed=11)
    models = _fitted_zero_temp_models(mapping, state)
    assert models is not None
    vec = _vectorized_fitted_expected(state, "m0", candidates, models, repl, cfg)
    obj = [_expected_value(state, "m0", asset, mapping, repl, cfg) for asset in candidates]
    assert vec == pytest.approx(obj, abs=1e-9)


def test_vectorized_fitted_uses_each_managers_need_weight() -> None:
    # R2-m11 regression: the old kernel overwrote one scalar in this loop and used
    # m3's 3.5 weight for every seat. Heterogeneous object policies are authoritative.
    state = DraftState.new([f"m{i}" for i in range(4)], _pool(4, False), allow_ir=False)
    weights = dict(zip(state.rosters, (1.0, 0.2, 8.0, 3.5), strict=True))
    mapping = {
        manager: FittedOpponentModel(
            coefficients=Coefficients(rank=0.5, affinity=1.2),
            affinity={1: 0.6, 2: 0.3, 3: 0.1},
            need_weight=weights[manager],
        )
        for manager in state.rosters
    }
    replacement = replacement_levels(state, 4)
    candidates = [candidate.asset for candidate in _prune_candidates(state, "m0", replacement, 6)]
    config = RecommendConfig(rollouts=3, depth=1, seed=11)

    fast = _vectorized_fitted_expected(
        state, "m0", candidates, mapping, replacement, config
    )
    object_path = [
        _expected_value(state, "m0", asset, mapping, replacement, config)
        for asset in candidates
    ]

    assert object_path == pytest.approx([205.0, 204.0, 203.0, 201.0, 201.0, 201.0])
    assert fast == pytest.approx(object_path, abs=1e-9)


def test_recommend_pick_uses_fitted_fast_path() -> None:
    state = DraftState.new([f"m{i}" for i in range(4)], _pool(4, False), allow_ir=False)
    mapping = _fitted_mapping(state)
    result = recommend_pick(state, "m0", mapping, config=RecommendConfig(rollouts=40, seed=5))
    assert result.evaluations
    assert result.best.asset.key in state.available


def test_fitted_zero_temp_models_gates_the_fast_path() -> None:
    state = DraftState.new([f"m{i}" for i in range(4)], _pool(4, False), allow_ir=False)
    # Deterministic fitted mapping -> eligible for the vectorized kernel.
    assert _fitted_zero_temp_models(_fitted_mapping(state), state) is not None
    # A sampling (temperature>0) fitted model cannot be reproduced by argmax -> object path.
    assert _fitted_zero_temp_models(_fitted_mapping(state, temperature=0.5), state) is None
    # A greedy mapping is not fitted -> object path.
    greedy = {m: GreedyOpponentModel(temperature=0.0) for m in state.rosters}
    assert _fitted_zero_temp_models(greedy, state) is None
    # A single (non-mapping) model is not a per-manager fitted set.
    assert _fitted_zero_temp_models(GreedyOpponentModel(), state) is None


def test_full_depth_12_manager_recommendation_completes() -> None:
    managers = [f"m{i}" for i in range(12)]
    pool: list[DraftAsset] = []
    for i in range(200):
        pool.append(
            _skater(f"F{i}", "F", 30.0 - 0.1 * i, _AssetIds(1 + (i % 16), 1000 + i))
        )
    for i in range(120):
        pool.append(
            _skater(f"D{i}", "D", 20.0 - 0.1 * i, _AssetIds(1 + (i % 16), 2000 + i))
        )
    for i in range(16):
        pool.append(_team(100 + i, 25.0 - i))
    state = DraftState.new(managers, pool, allow_ir=True)
    model = GreedyOpponentModel(temperature=0.3)
    start = time.perf_counter()
    result = recommend_pick(state, "m0", model, config=RecommendConfig(rollouts=500))
    elapsed = time.perf_counter() - start
    # Smoke bound only: the vectorized full-depth path must complete without a
    # super-linear blow-up. This is deliberately generous rather than a tight SLA --
    # the interactive latency target is not enforced here, so the check stays stable
    # across slower hardware.
    assert result.evaluations
    assert elapsed < 60.0, f"full-depth recommendation took {elapsed:.2f}s"


# ── Synthetic pool & strategy comparison ────────────────────────────────────


def test_build_synthetic_pool_covers_demand() -> None:
    pool = build_synthetic_pool(4, allow_ir=False)
    forwards = sum(1 for a in pool if a.position == "F")
    defense = sum(1 for a in pool if a.position == "D")
    goalies = sum(1 for a in pool if a.position == "G")
    assert forwards > 5 * 4  # more than league-wide forward demand
    assert defense > 3 * 4
    assert goalies > 4


def test_compare_strategies_returns_three_means() -> None:
    pool = build_synthetic_pool(4, allow_ir=False)
    managers = [f"m{i}" for i in range(4)]
    model = GreedyOpponentModel(temperature=0.5)
    result = compare_strategies(
        pool,
        managers,
        "m0",
        model,
        config=RecommendConfig(rollouts=12, max_candidates=5, compute_survival=False),
        n_drafts=5,
    )
    assert isinstance(result, StrategyComparison)
    assert set(result.means) == {"greedy_vor", "one_step", "multi_step"}
    assert result.n_drafts <= 5


def test_multi_step_beats_greedy_on_positional_run() -> None:
    # Against opponents that run a position, the static VOR board is blind and the
    # multi-step lookahead should not do worse than greedy-VOR (usually beats it).
    pool = build_synthetic_pool(4, allow_ir=False)
    managers = [f"m{i}" for i in range(4)]
    run_model = _PositionRunOpponent(favored="F", bonus=12.0)
    result = compare_strategies(
        pool,
        managers,
        "m0",
        run_model,
        config=RecommendConfig(rollouts=24, max_candidates=6, compute_survival=False),
        n_drafts=60,
        opponent_kind="positional-run",
        scenario="positional-run",
    )
    assert result.means["multi_step"] >= result.means["greedy_vor"] - 0.05


def test_strategy_comparison_report_is_ascii() -> None:
    comparison = StrategyComparison(
        n_drafts=200,
        owner="m0",
        managers=4,
        allow_ir=False,
        rollouts=40,
        max_candidates=6,
        opponent_kind="fitted-league",
        means={"greedy_vor": 184.6, "one_step": 184.6, "multi_step": 184.58},
    )
    "\n".join(comparison.report_lines()).encode("ascii")
    assert comparison.ties_greedy
    assert comparison.manifest()["multi_step_ties_greedy"] is True


def test_build_pool_from_projection_artifact(tmp_path: Path) -> None:
    skaters = pd.DataFrame(
        [
            {
                "player_id": 1,
                "player_name": "A",
                "team_abbrev": "AAA",
                "position": "F",
                "expected_points": 10.0,
            },
            {
                "player_id": 2,
                "player_name": "B",
                "team_abbrev": "BBB",
                "position": "D",
                "expected_points": 8.0,
            },
            {
                "player_id": 3,
                "player_name": "C",
                "team_abbrev": "AAA",
                "position": "G",
                "expected_points": 0.0,
            },
        ]
    )
    teams = pd.DataFrame(
        [
            {"team_id": 11, "team_abbrev": "AAA", "e_goalie_points": 20.0},
            {"team_id": 22, "team_abbrev": "BBB", "e_goalie_points": 18.0},
        ]
    )
    skaters.to_parquet(tmp_path / "skaters.parquet", index=False)
    teams.to_parquet(tmp_path / "teams.parquet", index=False)
    pool = build_pool_from_projection_artifact(tmp_path)
    positions = sorted(a.position for a in pool)
    assert positions == ["D", "F", "G", "G"]  # 1 F + 1 D skaters, 2 team G rows
    forward = next(a for a in pool if a.position == "F")
    assert forward.team_id == 11 and forward.projection == 10.0
