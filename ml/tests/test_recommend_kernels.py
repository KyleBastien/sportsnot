"""Focused tests for vectorized recommendation kernels."""

from __future__ import annotations

import time

import pytest

from draft_oracle.optimize.opponents import Coefficients, FittedOpponentModel
from draft_oracle.optimize.recommend import (
    RecommendConfig,
    _ChoosePickRequest,
    _expected_value,
    _ExpectedValueRequest,
    _fitted_zero_temp_models,
    _prune_candidates,
    _vectorized_fitted_expected,
    _vectorized_greedy_expected,
    choose_pick,
    recommend_pick,
    replacement_levels,
)
from draft_oracle.optimize.simulator import (
    DraftAsset,
    DraftState,
    GreedyOpponentModel,
    roster_capacity,
)
from tests.test_recommend import _AssetIds, _pool, _skater, _team


def _pool_rank_ne_projection(managers: int) -> list[DraftAsset]:
    """A pool where ``rank_value`` deliberately disagrees with ``projection``."""
    cap = roster_capacity(False)
    pool: list[DraftAsset] = []
    n_f = cap.forwards * managers + 6
    for i in range(n_f):
        pool.append(
            DraftAsset(
                key=f"F{i}",
                name=f"F{i}",
                position="F",
                rank_value=float(i + 1),
                player_id=1000 + i,
                team_id=1 + (i % 8),
                team_abbrev=f"T{1 + (i % 8)}",
                projection=30.0 - i,
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
    """Deterministically advance draft by ``picks`` first-legal choices."""
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
    for key in ("F1", "F2", "F3", "F4", "D0", "D1", "D2"):
        state.place("m2", state.available[key])
    return state, state.available["D3"]


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
    pick = choose_pick(
        _ChoosePickRequest(state, "m0", model, config=RecommendConfig(rollouts=32))
    )
    assert pick.key in state.available


def test_fast_paths_match_object_rank_then_key_tie_break() -> None:
    state, candidate = _tied_opponent_state()
    replacement = replacement_levels(state, 3)
    config = RecommendConfig(rollouts=2, depth=1, seed=1)
    greedy = GreedyOpponentModel(temperature=0.0, need_weight=4.0)
    greedy_mapping = dict.fromkeys(state.rosters, greedy)
    greedy_fast = _vectorized_greedy_expected(
        state, "m1", [candidate], greedy, replacement, config
    )
    greedy_object = [
        _expected_value(
            _ExpectedValueRequest(
                state,
                "m1",
                candidate,
                greedy_mapping,
                replacement,
                config,
            )
        )
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
        _expected_value(
            _ExpectedValueRequest(
                state,
                "m1",
                candidate,
                fitted_mapping,
                replacement,
                config,
            )
        )
    ]

    assert greedy_object == pytest.approx([205.0])
    assert greedy_fast == pytest.approx(greedy_object, abs=1e-9)
    assert fitted_object == pytest.approx([205.0])
    assert fitted_fast == pytest.approx(fitted_object, abs=1e-9)


def test_fast_path_scores_opponents_by_rank_value_and_matches_object() -> None:
    state = DraftState.new([f"m{i}" for i in range(4)], _pool_rank_ne_projection(4), allow_ir=False)
    _advance(state, 7)
    assert state.current_manager == "m0"
    assert len(state.rosters["m0"].all_assets()) == 1
    gmodel = GreedyOpponentModel(temperature=0.0)
    mapping = {m: GreedyOpponentModel(temperature=0.0) for m in state.rosters}
    repl = replacement_levels(state, 4)
    candidates = [c.asset for c in _prune_candidates(state, "m0", repl, 6)]
    cfg = RecommendConfig(rollouts=6, seed=7)
    vec = _vectorized_greedy_expected(state, "m0", candidates, gmodel, repl, cfg)
    obj = [
        _expected_value(_ExpectedValueRequest(state, "m0", asset, mapping, repl, cfg))
        for asset in candidates
    ]
    assert vec == pytest.approx(obj, abs=1e-9)


def test_fast_path_raises_on_dry_pool_like_object_path() -> None:
    managers = [f"m{i}" for i in range(3)]
    pool: list[DraftAsset] = []
    for i in range(20):
        pool.append(_skater(f"F{i}", "F", 30.0 - i, _AssetIds(1 + (i % 4), 1000 + i)))
    for i in range(12):
        pool.append(_skater(f"D{i}", "D", 20.0 - i, _AssetIds(1 + (i % 4), 2000 + i)))
    for i in range(2):
        pool.append(_team(100 + i, 25.0 - 2.0 * i))
    state = DraftState.new(managers, pool, allow_ir=False)
    _advance(state, 2)
    gmodel = GreedyOpponentModel(temperature=0.0)
    mapping = {m: GreedyOpponentModel(temperature=0.0) for m in state.rosters}
    repl = replacement_levels(state, 3)
    candidates = [c.asset for c in _prune_candidates(state, "m2", repl, 4)]
    cfg = RecommendConfig(rollouts=4, seed=1)
    with pytest.raises(ValueError, match="no legal asset"):
        _vectorized_greedy_expected(state, "m2", candidates, gmodel, repl, cfg)
    with pytest.raises(ValueError, match="no legal asset"):
        [
            _expected_value(_ExpectedValueRequest(state, "m2", asset, mapping, repl, cfg))
            for asset in candidates
        ]


def test_vectorized_greedy_matches_object_path_when_deterministic() -> None:
    state = DraftState.new([f"m{i}" for i in range(4)], _pool(4, False), allow_ir=False)
    gmodel = GreedyOpponentModel(temperature=0.0)
    mapping = {m: GreedyOpponentModel(temperature=0.0) for m in state.rosters}
    cfg = RecommendConfig(rollouts=8, seed=1)
    vec = recommend_pick(state, "m0", gmodel, config=cfg)
    obj = recommend_pick(state, "m0", mapping, config=cfg)
    assert vec.best.asset.key == obj.best.asset.key


def test_vectorized_fitted_matches_object_path() -> None:
    state = DraftState.new([f"m{i}" for i in range(4)], _pool(4, False), allow_ir=False)
    mapping = _fitted_mapping(state)
    repl = replacement_levels(state, 4)
    candidates = [c.asset for c in _prune_candidates(state, "m0", repl, 6)]
    cfg = RecommendConfig(rollouts=30, depth=2, seed=11)
    models = _fitted_zero_temp_models(mapping, state)
    assert models is not None
    vec = _vectorized_fitted_expected(state, "m0", candidates, models, repl, cfg)
    obj = [
        _expected_value(_ExpectedValueRequest(state, "m0", asset, mapping, repl, cfg))
        for asset in candidates
    ]
    assert vec == pytest.approx(obj, abs=1e-9)


def test_vectorized_fitted_uses_each_managers_need_weight() -> None:
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
    fast = _vectorized_fitted_expected(state, "m0", candidates, mapping, replacement, config)
    object_path = [
        _expected_value(
            _ExpectedValueRequest(
                state,
                "m0",
                asset,
                mapping,
                replacement,
                config,
            )
        )
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
    assert _fitted_zero_temp_models(_fitted_mapping(state), state) is not None
    assert _fitted_zero_temp_models(_fitted_mapping(state, temperature=0.5), state) is None
    greedy = {m: GreedyOpponentModel(temperature=0.0) for m in state.rosters}
    assert _fitted_zero_temp_models(greedy, state) is None
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
    assert result.evaluations
    assert elapsed < 60.0, f"full-depth recommendation took {elapsed:.2f}s"
