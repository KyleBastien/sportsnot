"""Draft playout helpers for backtest replay."""

from __future__ import annotations

import random
from dataclasses import replace

from draft_oracle.backtest._replay_types import BacktestConfig, Strategy
from draft_oracle.optimize.recommend import choose_pick, greedy_vor_pick, replacement_levels
from draft_oracle.optimize.simulator import DraftAsset, DraftState, OpponentModel, _resolve_model


def _oracle_pick(
    strategy: Strategy,
    state: DraftState,
    oracle: str,
    opponent_model: OpponentModel | dict[str, OpponentModel],
    config: BacktestConfig,
    rng: random.Random,
) -> DraftAsset:
    """The asset the oracle drafts under ``strategy`` at the current slot."""
    if strategy == "random_legal":
        legal = state.legal_assets(oracle)
        if not legal:
            raise ValueError(f"oracle {oracle!r} has no legal pick")
        return legal[rng.randrange(len(legal))]
    if strategy == "greedy_vor":
        replacement = replacement_levels(state, config.managers)
        return greedy_vor_pick(state, oracle, replacement)
    cfg = config.recommend_config()
    if strategy == "one_step":
        cfg = replace(cfg, depth=1)
    return choose_pick(state, oracle, opponent_model, config=cfg, managers=config.managers)


def _play_oracle_draft(
    base_state: DraftState,
    oracle: str,
    strategy: Strategy,
    opponent_model: OpponentModel | dict[str, OpponentModel],
    config: BacktestConfig,
    seed: int,
) -> DraftState:
    """Play a full draft with ``oracle`` seated under ``strategy`` vs. opponents.

    Opponents draw from one seeded ``rng`` so the whole playout is determined by
    ``(base_state, seed)``; the oracle's own policy is deterministic given the state.
    """
    state = base_state.copy()
    rng = random.Random(seed)
    while not state.is_complete:
        current = state.current_manager
        if current == oracle:
            asset = _oracle_pick(strategy, state, oracle, opponent_model, config, rng)
        else:
            model = _resolve_model(opponent_model, current)
            asset = model.pick(state, current, rng)
        state.apply_pick(asset)
    return state
