"""Draft playout helpers for backtest replay."""

from __future__ import annotations

import random
from dataclasses import dataclass, replace

from draft_oracle.backtest._replay_types import BacktestConfig, Strategy
from draft_oracle.optimize.recommend import (
    _ChoosePickRequest,
    choose_pick,
    greedy_vor_pick,
    replacement_levels,
)
from draft_oracle.optimize.simulator import DraftAsset, DraftState, OpponentModel, _resolve_model


@dataclass(frozen=True)
class _OraclePickRequest:
    strategy: Strategy
    state: DraftState
    oracle: str
    opponent_model: OpponentModel | dict[str, OpponentModel]
    config: BacktestConfig


@dataclass(frozen=True)
class _OracleDraftRequest:
    base_state: DraftState
    oracle: str
    strategy: Strategy
    opponent_model: OpponentModel | dict[str, OpponentModel]
    config: BacktestConfig
    seed: int


def _oracle_pick(request: _OraclePickRequest, rng: random.Random) -> DraftAsset:
    """The asset the oracle drafts under ``strategy`` at the current slot."""
    if request.strategy == "random_legal":
        legal = request.state.legal_assets(request.oracle)
        if not legal:
            raise ValueError(f"oracle {request.oracle!r} has no legal pick")
        return legal[rng.randrange(len(legal))]
    if request.strategy == "greedy_vor":
        replacement = replacement_levels(request.state, request.config.managers)
        return greedy_vor_pick(request.state, request.oracle, replacement)
    cfg = request.config.recommend_config()
    if request.strategy == "one_step":
        cfg = replace(cfg, depth=1)
    return choose_pick(
        _ChoosePickRequest(
            request.state,
            request.oracle,
            request.opponent_model,
            config=cfg,
        )
    )


def _play_oracle_draft(request: _OracleDraftRequest) -> DraftState:
    """Play a full draft with ``oracle`` seated under ``strategy`` vs. opponents.

    Opponents draw from one seeded ``rng`` so the whole playout is determined by
    ``(base_state, seed)``; the oracle's own policy is deterministic given the state.
    """
    state = request.base_state.copy()
    rng = random.Random(request.seed)
    while not state.is_complete:
        current = state.current_manager
        if current == request.oracle:
            asset = _oracle_pick(
                _OraclePickRequest(
                    request.strategy,
                    state,
                    request.oracle,
                    request.opponent_model,
                    request.config,
                ),
                rng,
            )
        else:
            model = _resolve_model(request.opponent_model, current)
            asset = model.pick(state, current, rng)
        state.apply_pick(asset)
    return state
