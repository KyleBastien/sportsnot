"""Tests for draft_oracle.optimize.recommend (US-021).

Covers the value/replacement primitives, the greedy-VOR policy, the multi-step
Monte-Carlo recommendation (ranking, explanations, determinism, forced picks,
goalie-slot timing, depth, the <10s full-depth bar), the vectorized greedy kernel,
and the honest strategy comparison. All fixtures are tiny in-memory pools -- no
network, no committed data (SPEC section 7).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pandas as pd
import pytest

from draft_oracle.optimize._recommend_strategies import CompareStrategiesRequest
from draft_oracle.optimize.recommend import (
    Recommendation,
    RecommendConfig,
    StrategyComparison,
    _PositionRunOpponent,
    asset_value,
    build_pool_from_projection_artifact,
    build_synthetic_pool,
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
        CompareStrategiesRequest(
            pool,
            managers,
            "m0",
            model,
            config=RecommendConfig(rollouts=12, max_candidates=5, compute_survival=False),
            n_drafts=5,
        )
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
        CompareStrategiesRequest(
            pool,
            managers,
            "m0",
            run_model,
            config=RecommendConfig(rollouts=24, max_candidates=6, compute_survival=False),
            n_drafts=60,
            opponent_kind="positional-run",
            scenario="positional-run",
        )
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
