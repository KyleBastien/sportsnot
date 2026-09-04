"""Utility helpers for vectorized recommendation kernels."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class _GreedyChoiceInputs:
    rank_val: np.ndarray
    limits: np.ndarray
    posc: np.ndarray
    key_order: np.ndarray
    need_weight: float
    temperature: float
    cnt_m: np.ndarray
    legal: np.ndarray
    rng: np.random.Generator


def _rank_key_argmax(
    scores: np.ndarray,
    legal: np.ndarray,
    rank_value: np.ndarray,
    key_order: np.ndarray,
) -> np.ndarray:
    """Row-wise score argmax with object-model ``rank_value``/key tie-breaks."""
    neg_inf = float("-inf")
    masked = np.where(legal, scores, neg_inf)
    best_score = masked.max(axis=1)
    tied = legal & (scores == best_score[:, None])
    tied_rank = np.where(tied, rank_value[None, :], neg_inf)
    best_rank = tied_rank.max(axis=1)
    tied &= rank_value[None, :] == best_rank[:, None]
    return np.argmin(np.where(tied, key_order[None, :], len(key_order)), axis=1)


def _fitted_rank_z(
    legal: np.ndarray,
    rank_val: np.ndarray,
    pos_masks: Sequence[np.ndarray],
) -> np.ndarray:
    """Per-position standardized ``rank_value`` over legal set (fitted utility term)."""
    rollouts, n_assets = legal.shape
    rank_z = np.zeros((rollouts, n_assets), dtype="float64")
    for pos_mask in pos_masks:
        legal_p = legal & pos_mask[None, :]
        cnt = legal_p.sum(axis=1)
        safe = np.maximum(cnt, 1)
        mean = np.where(cnt > 0, (rank_val[None, :] * legal_p).sum(axis=1) / safe, 0.0)
        sum_sq = ((rank_val[None, :] ** 2) * legal_p).sum(axis=1)
        var = np.where(cnt > 0, sum_sq / safe - mean**2, 0.0)
        std = np.sqrt(np.maximum(var, 0.0))
        std_safe = np.where(std > 0.0, std, 1.0)
        z_p = np.where(
            std[:, None] > 0.0,
            (rank_val[None, :] - mean[:, None]) / std_safe[:, None],
            0.0,
        )
        rank_z[:, pos_mask] = z_p[:, pos_mask]
    return rank_z


def _greedy_opponent_choice(
    request: _GreedyChoiceInputs,
) -> np.ndarray:
    """Greedy opponent's per-rollout pick: ``rank_value + need`` softmax (or argmax)."""
    urgency = (request.limits - request.cnt_m) / request.limits
    scores = request.rank_val[None, :] + (request.need_weight * urgency)[:, request.posc]
    if request.temperature <= 0.0:
        return _rank_key_argmax(scores, request.legal, request.rank_val, request.key_order)
    rollouts, n_assets = request.legal.shape
    gumbel = -np.log(-np.log(request.rng.random((rollouts, n_assets))))
    noisy = np.where(request.legal, scores / request.temperature + gumbel, float("-inf"))
    return np.argmax(noisy, axis=1)


def _fitted_opponent_choice(
    rank_val: np.ndarray,
    limits: np.ndarray,
    posc: np.ndarray,
    key_order: np.ndarray,
    coef_rank: np.ndarray,
    coef_aff: np.ndarray,
    aff_matrix: np.ndarray,
    need_weight: np.ndarray,
    cnt_m: np.ndarray,
    legal: np.ndarray,
    mgr_i: int,
) -> np.ndarray:
    """Fitted opponent's deterministic per-rollout pick from utility model."""
    pos_masks = [posc == position_index for position_index in range(3)]
    urgency = (limits - cnt_m) / limits
    rank_z = _fitted_rank_z(legal, rank_val, pos_masks)
    utility = (
        coef_rank[mgr_i] * rank_z
        + coef_aff[mgr_i] * aff_matrix[mgr_i][None, :]
        + need_weight[mgr_i] * urgency[:, posc]
    )
    return _rank_key_argmax(utility, legal, rank_val, key_order)


def _affinity_row(pool: Sequence[Any], affinity: Mapping[int, float]) -> list[float]:
    return [
        float(affinity.get(int(asset.team_id), 0.0)) if asset.team_id is not None else 0.0
        for asset in pool
    ]
