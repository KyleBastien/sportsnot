"""Multi-step pick recommendation engine (US-021).

Greedy value-over-replacement (US-018) answers *which asset is worth the most in a
vacuum*. It does **not** answer the question a drafter on the clock actually asks:
*which pick, right now, leaves me with the best final roster once the rest of the
draft plays out against these specific opponents?* Those differ whenever a position
is about to run dry, or a target will obviously survive to your next turn, or a
forced slot looms — exactly the situations where greedy leaves points on the board.

This module rolls the whole remaining draft forward with Monte-Carlo simulation:

* the owner tentatively makes each candidate pick,
* the fitted opponent model (US-020, or the greedy fallback, US-019) drafts through
  every one of the owner's remaining turns,
* the owner's *future* slots are filled by a fast value-over-replacement rollout
  policy, and
* the owner's total final-roster projection is averaged across many seeded rollouts.

The recommended pick is the ``argmax`` of that expected final-roster value. Because
the opponents are simulated, the engine automatically prefers a scarce-position asset
that will not survive to the next turn over a safe one that will, times a goalie slot
correctly, and respects forced picks when a manager's roster is nearly full.

Determinism (SPEC section 3): every rollout draws from ``random.Random`` seeded from
``(config.seed, candidate index, rollout index)`` so ``(state, config)`` fully
determines the recommendation.

Speed (acceptance): a full-depth recommendation must finish in <10 s at any state of
a 12-manager 11-pick draft. Three levers keep it there without lowering the rollout
count below the spec floor:

* **candidate pruning** — only the top ``max_candidates`` assets by VOR are rolled out
  (the best current pick is never far down the VOR board),
* **owner-full early stop** — a rollout ends the instant the owner's roster is full,
  since later opponent picks cannot change the owner's score, and
* **depth capping** — ``depth`` bounds how many of the owner's turns are simulated
  against live opponents; beyond it the owner's remaining slots are filled greedily
  from the current pool (``--depth``/``--rollouts`` trade accuracy for speed).
"""

from __future__ import annotations

import json
import math
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import numpy as np

if TYPE_CHECKING:
    import pandas as pd

from draft_oracle.optimize.opponents import (
    FittedLeagueOpponents,
    FittedOpponentModel,
    OpponentFitConfig,
    fit_opponent_models,
)
from draft_oracle.optimize.simulator import (
    DraftAsset,
    DraftState,
    GreedyOpponentModel,
    OpponentModel,
    survival_probability,
)
from draft_oracle.optimize.vor import replacement_level

__all__ = [
    "DEFAULT_MAX_CANDIDATES",
    "DEFAULT_RECOMMEND_ARTIFACT_DIR",
    "DEFAULT_ROLLOUTS",
    "DEFAULT_SURVIVAL_ROLLOUTS",
    "PickEvaluation",
    "RecommendConfig",
    "Recommendation",
    "StrategyComparison",
    "asset_value",
    "build_pool_from_frames",
    "build_pool_from_projection_artifact",
    "build_synthetic_pool",
    "choose_pick",
    "compare_strategies",
    "evaluate_recommendation_strategies_from_normalized",
    "greedy_vor_pick",
    "recommend_pick",
    "replacement_levels",
]

# A rollout averages over at least this many seeded playouts (SPEC/acceptance floor).
DEFAULT_ROLLOUTS = 500
# Survival probability is a cheap by-product estimate; it needs far fewer rollouts.
DEFAULT_SURVIVAL_ROLLOUTS = 200
# Only the top-VOR assets are ever the best current pick; rolling out more wastes time.
DEFAULT_MAX_CANDIDATES = 24

_ROLLOUT_SALT = 1_000_003

# Committed comparison artifact (report + manifest re-included in .gitignore).
DEFAULT_RECOMMEND_ARTIFACT_DIR = Path("artifacts/models/recommend")


def asset_value(asset: DraftAsset) -> float:
    """Projected fantasy points an asset contributes to a roster.

    Prefers the model ``projection`` (expected round points for skaters, expected
    goalie-slot points for a team). Falls back to ``rank_value`` (the public-perception
    signal) when a pool carries no projection, so the engine still ranks sensibly on a
    projection-less pool — documented, never a crash (SPEC section 7).
    """
    if asset.projection is not None:
        return float(asset.projection)
    return float(asset.rank_value)


def replacement_levels(state: DraftState, managers: int) -> dict[str, float]:
    """Per-position replacement level from the *current* available pool (US-018).

    ``managers`` sizes the starter demand; the replacement level of a position is the
    value of the best asset still freely available once every manager has filled that
    slot. Used both to prune candidates and to drive the owner's rollout policy so
    forwards, defensemen, and goalie slots are compared on one axis.
    """
    demand = state.capacity
    forward_vals: list[float] = []
    defense_vals: list[float] = []
    goalie_vals: list[float] = []
    for asset in state.available.values():
        value = asset_value(asset)
        if asset.position == "F":
            forward_vals.append(value)
        elif asset.position == "D":
            defense_vals.append(value)
        else:
            goalie_vals.append(value)
    return {
        "F": replacement_level(forward_vals, demand.forwards * managers),
        "D": replacement_level(defense_vals, demand.defense * managers),
        "G": replacement_level(goalie_vals, demand.goalies * managers),
    }


def greedy_vor_pick(
    state: DraftState, manager: str, replacement: Mapping[str, float]
) -> DraftAsset:
    """Best legal asset for ``manager`` by value over replacement (deterministic).

    The owner's rollout/tail policy and the greedy-VOR comparison baseline both use
    this: score every legal asset ``value - replacement[position]`` and take the max,
    breaking ties by raw value then key so it is fully deterministic.
    """
    legal = state.legal_assets(manager)
    if not legal:
        raise ValueError(f"manager {manager!r} has no legal asset to draft")
    best = legal[0]
    best_vor = asset_value(best) - replacement[best.position]
    best_value = asset_value(best)
    for asset in legal[1:]:
        value = asset_value(asset)
        vor = value - replacement[asset.position]
        if vor > best_vor or (
            vor == best_vor
            and (value > best_value or (value == best_value and asset.key < best.key))
        ):
            best = asset
            best_vor = vor
            best_value = value
    return best


@dataclass(frozen=True)
class RecommendConfig:
    """Knobs for :func:`recommend_pick` (all deterministic given the state).

    ``rollouts`` is the Monte-Carlo count per candidate (>=500 per the acceptance
    floor). ``depth`` bounds the owner turns simulated against live opponents
    (``None`` = the full remaining draft); ``max_candidates`` prunes the candidate set
    to the top assets by VOR. ``survival_rollouts`` sizes the cheaper survival
    estimate. ``top_n`` is how many explained recommendations to surface.
    """

    rollouts: int = DEFAULT_ROLLOUTS
    depth: int | None = None
    max_candidates: int = DEFAULT_MAX_CANDIDATES
    survival_rollouts: int = DEFAULT_SURVIVAL_ROLLOUTS
    top_n: int = 5
    seed: int = 20260827
    compute_survival: bool = True

    def __post_init__(self) -> None:
        if self.rollouts < 1:
            raise ValueError(f"rollouts must be >= 1, got {self.rollouts}")
        if self.depth is not None and self.depth < 1:
            raise ValueError(f"depth must be >= 1 or None, got {self.depth}")
        if self.max_candidates < 1:
            raise ValueError(f"max_candidates must be >= 1, got {self.max_candidates}")
        if self.survival_rollouts < 1:
            raise ValueError(f"survival_rollouts must be >= 1, got {self.survival_rollouts}")
        if self.top_n < 1:
            raise ValueError(f"top_n must be >= 1, got {self.top_n}")


@dataclass(frozen=True)
class PickEvaluation:
    """One candidate's rolled-out value plus the reasoning behind it."""

    asset: DraftAsset
    expected_points: float
    immediate_value: float
    vor: float
    replacement: float
    survival: float
    open_slots: int
    position_limit: int
    delta_vs_next: float = 0.0

    def explanation(self) -> str:
        """One ASCII line of why this pick ranks where it does (SPEC honesty)."""
        need = f"{self.open_slots}/{self.position_limit} {self.asset.position} slots open"
        return (
            f"E[roster] {self.expected_points:.2f} "
            f"(proj {self.immediate_value:.2f}, VOR {self.vor:+.2f}); "
            f"P(survives to next pick) {self.survival:.2f}; "
            f"{need}; delta vs #2 {self.delta_vs_next:+.2f}"
        )


@dataclass
class Recommendation:
    """Ranked, explained pick recommendations for the owner on the clock."""

    owner: str
    pick_index: int
    rollouts: int
    depth: int | None
    replacement: dict[str, float]
    evaluations: list[PickEvaluation]
    candidates_considered: int
    seed: int = 20260827

    @property
    def best(self) -> PickEvaluation:
        """The single recommended pick (highest expected final-roster value)."""
        if not self.evaluations:
            raise ValueError("no evaluations; the owner has no legal pick")
        return self.evaluations[0]

    def top(self, n: int | None = None) -> list[PickEvaluation]:
        """The top ``n`` explained recommendations (all of them when ``n`` is None)."""
        if n is None:
            return list(self.evaluations)
        return self.evaluations[:n]

    def report_lines(self) -> list[str]:
        """Human-readable ranked board (Markdown, ASCII only)."""
        lines = [
            "# Draft Oracle pick recommendation",
            "",
            f"- On the clock: {self.owner} (pick #{self.pick_index + 1})",
            f"- Rollouts per candidate: {self.rollouts}"
            + (f" | depth {self.depth}" if self.depth is not None else " | full depth"),
            f"- Candidates rolled out: {self.candidates_considered}",
            (
                "- Replacement level (points):"
                f" F {self.replacement['F']:.2f}"
                f" / D {self.replacement['D']:.2f}"
                f" / G {self.replacement['G']:.2f}"
            ),
            "",
            "| Rank | Pos | Player | Team | E[roster] | Proj | VOR | P(survive) | Need |",
            "| ---: | :-- | :----- | :--- | --------: | ---: | --: | ---------: | :--- |",
        ]
        for index, ev in enumerate(self.evaluations, start=1):
            need = f"{ev.open_slots}/{ev.position_limit}"
            lines.append(
                f"| {index} | {ev.asset.position} | {ev.asset.name} "
                f"| {ev.asset.team_abbrev} | {ev.expected_points:.2f} "
                f"| {ev.immediate_value:.2f} | {ev.vor:+.2f} | {ev.survival:.2f} "
                f"| {need} |"
            )
        return lines

    def manifest(self) -> dict[str, Any]:
        """JSON-serialisable summary of the recommendation run."""
        return {
            "owner": self.owner,
            "pick_index": self.pick_index,
            "rollouts": self.rollouts,
            "depth": self.depth,
            "seed": self.seed,
            "candidates_considered": self.candidates_considered,
            "replacement_level": dict(self.replacement),
            "recommendations": [
                {
                    "rank": index,
                    "asset": ev.asset.key,
                    "name": ev.asset.name,
                    "position": ev.asset.position,
                    "expected_points": round(ev.expected_points, 6),
                    "immediate_value": round(ev.immediate_value, 6),
                    "vor": round(ev.vor, 6),
                    "survival": round(ev.survival, 6),
                    "open_slots": ev.open_slots,
                    "position_limit": ev.position_limit,
                    "delta_vs_next": round(ev.delta_vs_next, 6),
                }
                for index, ev in enumerate(self.evaluations, start=1)
            ],
        }


def _owner_roster_value(state: DraftState, owner: str) -> float:
    return sum(asset_value(asset) for asset in state.rosters[owner].all_assets())


def _fill_owner_greedily(sim: DraftState, owner: str, replacement: Mapping[str, float]) -> None:
    """Fill the owner's remaining slots greedily, ignoring further opponent picks.

    The fast tail used past ``depth``: it assumes the current pool for the owner's
    leftover slots, trading the accuracy of continued opponent depletion for speed.
    """
    roster = sim.rosters[owner]
    while roster.count("F") + roster.count("D") + roster.count("G") < sim.capacity.total:
        legal = sim.legal_assets(owner)
        if not legal:
            break
        pick = greedy_vor_pick(sim, owner, replacement)
        sim.place(owner, pick)


def _rollout_owner_value(
    state: DraftState,
    owner: str,
    candidate: DraftAsset,
    opponent_model: OpponentModel | Mapping[str, OpponentModel],
    replacement: Mapping[str, float],
    depth: int | None,
    rng: random.Random,
) -> float:
    """One playout's final owner-roster value after taking ``candidate`` now.

    The owner takes ``candidate`` immediately, then the draft plays forward: opponents
    draft via ``opponent_model`` and the owner fills future slots with the greedy-VOR
    rollout policy. Simulation stops the moment the owner's roster is full (later picks
    cannot change the owner's score). Once the owner has made ``depth`` picks the tail
    is filled greedily from the current pool without simulating more opponents.
    """
    sim = state.copy()
    sim.apply_pick(candidate)
    owner_picks = 1
    total = sim.capacity.total
    roster = sim.rosters[owner]

    def owner_full() -> bool:
        return roster.count("F") + roster.count("D") + roster.count("G") >= total

    while not owner_full() and not sim.is_complete:
        manager = sim.current_manager
        if manager == owner:
            if depth is not None and owner_picks >= depth:
                _fill_owner_greedily(sim, owner, replacement)
                break
            pick = greedy_vor_pick(sim, owner, replacement)
            sim.apply_pick(pick)
            owner_picks += 1
        else:
            model = _resolve_model(opponent_model, manager)
            asset = model.pick(sim, manager, rng)
            sim.apply_pick(asset)
    return _owner_roster_value(sim, owner)


def _resolve_model(
    opponent_model: OpponentModel | Mapping[str, OpponentModel],
    manager: str,
) -> OpponentModel:
    if isinstance(opponent_model, Mapping):
        try:
            return opponent_model[manager]
        except KeyError as exc:
            raise ValueError(f"no opponent model for manager {manager!r}") from exc
    return opponent_model


@dataclass(frozen=True)
class _Candidate:
    asset: DraftAsset
    vor: float
    replacement: float


def _prune_candidates(
    state: DraftState,
    owner: str,
    replacement: Mapping[str, float],
    max_candidates: int,
) -> list[_Candidate]:
    legal = state.legal_assets(owner)
    scored = [
        _Candidate(
            asset,
            asset_value(asset) - replacement[asset.position],
            replacement[asset.position],
        )
        for asset in legal
    ]
    scored.sort(key=lambda c: (-c.vor, -asset_value(c.asset), c.asset.key))
    return scored[:max_candidates]


def _expected_value(
    state: DraftState,
    owner: str,
    asset: DraftAsset,
    opponent_model: OpponentModel | Mapping[str, OpponentModel],
    replacement: Mapping[str, float],
    cfg: RecommendConfig,
) -> float:
    """Mean final owner-roster value if ``asset`` is taken now (seeded rollouts).

    Rollout ``j`` is seeded from ``j`` alone (not the candidate), so every candidate
    faces the *same* opponent draws per rollout — common random numbers, which pairs
    the candidate comparison and slashes the variance of their differences so a modest
    rollout count still ranks picks correctly.
    """
    total = 0.0
    for rollout in range(cfg.rollouts):
        rng = random.Random(cfg.seed * _ROLLOUT_SALT + rollout)
        total += _rollout_owner_value(
            state, owner, asset, opponent_model, replacement, cfg.depth, rng
        )
    return total / cfg.rollouts


_POS_INDEX: dict[str, int] = {"F": 0, "D": 1, "G": 2}


def _require_legal_rows(legal: np.ndarray, manager: str) -> None:
    """Raise if any rollout row has no legal asset for ``manager``.

    The object-model rollout raises ``ValueError`` from ``greedy_vor_pick`` /
    ``OpponentModel.pick`` when a manager has nothing legal to draft. The vectorized
    kernel must fail the same way: an ``argmax`` over an all -inf row silently returns
    index 0 and drafts whatever asset happens to sit there, corrupting the rollout.
    """
    if not bool(legal.any(axis=1).all()):
        raise ValueError(f"manager {manager!r} has no legal asset to draft")


def _vec_fill_owner(
    alive: np.ndarray,
    counts: np.ndarray,
    owner_idx: int,
    val: np.ndarray,
    vor_owner: np.ndarray,
    posc: np.ndarray,
    limits: np.ndarray,
    owner_total: np.ndarray,
    remaining: int,
) -> None:
    """Vectorized greedy-VOR fill of the owner's remaining slots (opponents ignored)."""
    rows = np.arange(alive.shape[0])
    neg_inf = float("-inf")
    for _ in range(remaining):
        cap_ok = counts[:, owner_idx, :] < limits
        legal = alive & cap_ok[:, posc]
        has_legal = legal.any(axis=1)
        if not has_legal.any():
            break
        scores = np.where(legal, vor_owner[None, :], neg_inf)
        choice = np.argmax(scores, axis=1)
        # Match the object path's ``_fill_owner_greedily``: a row with no legal asset
        # simply stops filling (the owner gets fewer picks) rather than the argmax
        # over all -inf silently drafting pool index 0.
        active = rows[has_legal]
        chosen = choice[has_legal]
        owner_total[active] += val[chosen]
        alive[active, chosen] = False
        counts[active, owner_idx, posc[chosen]] += 1


def _vectorized_greedy_expected(
    state: DraftState,
    owner: str,
    candidate_assets: Sequence[DraftAsset],
    gmodel: GreedyOpponentModel,
    replacement: Mapping[str, float],
    cfg: RecommendConfig,
) -> list[float]:
    """Batched Monte-Carlo expected owner value against a greedy opponent (US-021).

    The pick order is identical across rollouts, so the whole 500-rollout batch is
    advanced in lockstep as numpy arrays: only the opponents' softmax draws differ per
    rollout. This is the "vectorized rollouts" the acceptance calls for and keeps a
    full-depth 12-manager recommendation well under the 10-second bar. Semantics match
    the object-model rollout (greedy-VOR owner tail, opponent ``rank_value + need``
    softmax, owner-full early stop, ``depth`` cap).
    """
    pool = sorted(state.available.values(), key=lambda a: (-asset_value(a), a.key))
    n_assets = len(pool)
    key_to_idx = {asset.key: i for i, asset in enumerate(pool)}
    val = np.array([asset_value(a) for a in pool], dtype="float64")
    rank_val = np.array([a.rank_value for a in pool], dtype="float64")
    posc = np.array([_POS_INDEX[a.position] for a in pool], dtype="int64")
    repl_arr = np.array([replacement["F"], replacement["D"], replacement["G"]], dtype="float64")
    vor_owner = val - repl_arr[posc]

    mgr_ids = list(dict.fromkeys(state.order))
    mid_to_idx = {m: i for i, m in enumerate(mgr_ids)}
    n_managers = len(mgr_ids)
    cap = state.capacity
    limits = np.array([cap.forwards, cap.defense, cap.goalies], dtype="int64")
    base_counts = np.zeros((n_managers, 3), dtype="int64")
    for manager, roster in state.rosters.items():
        base_counts[mid_to_idx[manager]] = [
            roster.count("F"),
            roster.count("D"),
            roster.count("G"),
        ]
    owner_idx = mid_to_idx[owner]
    cap_total = cap.total

    rem = state.order[state.pick_index :]
    rem_m = [mid_to_idx[m] for m in rem]
    owner_needed = cap_total - int(base_counts[owner_idx].sum())
    owner_positions = [k for k, mi in enumerate(rem_m) if mi == owner_idx]
    last_owner_k = owner_positions[owner_needed - 1]

    rollouts = cfg.rollouts
    rows = np.arange(rollouts)
    neg_inf = float("-inf")
    base_owner_value = _owner_roster_value(state, owner)
    means: list[float] = []
    for asset in candidate_assets:
        idx_c = key_to_idx[asset.key]
        # Common random numbers: identical opponent draws across candidates (pairs the
        # comparison; the seed does not depend on the candidate).
        rng = np.random.default_rng(cfg.seed * _ROLLOUT_SALT)
        alive = np.ones((rollouts, n_assets), dtype=bool)
        counts = np.broadcast_to(base_counts, (rollouts, n_managers, 3)).copy()
        owner_total = np.zeros(rollouts, dtype="float64")

        alive[:, idx_c] = False
        counts[:, owner_idx, posc[idx_c]] += 1
        owner_total += val[idx_c]
        owner_taken = 1

        for k in range(1, last_owner_k + 1):
            mgr_i = rem_m[k]
            cnt_m = counts[:, mgr_i, :]
            cap_ok = cnt_m < limits
            legal = alive & cap_ok[:, posc]
            if mgr_i == owner_idx:
                if cfg.depth is not None and owner_taken >= cfg.depth:
                    _vec_fill_owner(
                        alive,
                        counts,
                        owner_idx,
                        val,
                        vor_owner,
                        posc,
                        limits,
                        owner_total,
                        cap_total - owner_taken,
                    )
                    owner_taken = cap_total
                    break
                _require_legal_rows(legal, mgr_ids[mgr_i])
                scores = np.where(legal, vor_owner[None, :], neg_inf)
                choice = np.argmax(scores, axis=1)
                owner_total += val[choice]
                owner_taken += 1
            else:
                _require_legal_rows(legal, mgr_ids[mgr_i])
                urgency = (limits - cnt_m) / limits
                bump = gmodel.need_weight * urgency
                # Score opponents by ``rank_value`` (public perception), matching
                # ``GreedyOpponentModel.pick``; ``val`` (projection) would diverge.
                scores = rank_val[None, :] + bump[:, posc]
                if gmodel.temperature <= 0.0:
                    masked = np.where(legal, scores, neg_inf)
                    choice = np.argmax(masked, axis=1)
                else:
                    gumbel = -np.log(-np.log(rng.random((rollouts, n_assets))))
                    noisy = np.where(legal, scores / gmodel.temperature + gumbel, neg_inf)
                    choice = np.argmax(noisy, axis=1)
            alive[rows, choice] = False
            counts[rows, mgr_i, posc[choice]] += 1

        # ``owner_total`` accumulates only picks made during this rollout; add the
        # owner's already-drafted roster so E[roster] matches the object path's
        # ``_owner_roster_value`` (one documented definition).
        means.append(float(owner_total.mean()) + base_owner_value)
    return means


def _fitted_zero_temp_models(
    opponent_model: OpponentModel | Mapping[str, OpponentModel],
    state: DraftState,
) -> dict[str, FittedOpponentModel] | None:
    """The per-manager fitted models iff every opponent seat maps to a temperature-0 one.

    Guards the vectorized fitted fast path: it can only reproduce a deterministic
    (argmax) fitted policy, so a positive-temperature (sampling) model, a mixed set,
    or a missing seat forces the general object-model rollout instead.
    """
    if not isinstance(opponent_model, Mapping):
        return None
    models: dict[str, FittedOpponentModel] = {}
    for manager in dict.fromkeys(state.order):
        model = opponent_model.get(manager)
        if not isinstance(model, FittedOpponentModel) or model.temperature > 0.0:
            return None
        models[manager] = model
    return models


def _vectorized_fitted_expected(
    state: DraftState,
    owner: str,
    candidate_assets: Sequence[DraftAsset],
    models: Mapping[str, FittedOpponentModel],
    replacement: Mapping[str, float],
    cfg: RecommendConfig,
) -> list[float]:
    """Batched expected owner value against deterministic per-manager fitted opponents.

    The fitted analogue of :func:`_vectorized_greedy_expected`: the owner still fills
    via greedy-VOR, but each opponent seat scores legal assets by its own
    ``beta_rank * rank_z + beta_affinity * affinity + need_weight * need`` utility
    (``rank_z`` standardized within the legal set per base position, exactly as
    :meth:`FittedOpponentModel._utilities`), advanced across the whole rollout batch in
    lockstep. This keeps the fitted recommend under the 10s budget at ``rollouts>=500``
    without falling back to the per-pick Python object rollout.
    """
    pool = sorted(state.available.values(), key=lambda a: (-asset_value(a), a.key))
    n_assets = len(pool)
    key_to_idx = {asset.key: i for i, asset in enumerate(pool)}
    val = np.array([asset_value(a) for a in pool], dtype="float64")
    rank_val = np.array([a.rank_value for a in pool], dtype="float64")
    posc = np.array([_POS_INDEX[a.position] for a in pool], dtype="int64")
    repl_arr = np.array([replacement["F"], replacement["D"], replacement["G"]], dtype="float64")
    vor_owner = val - repl_arr[posc]

    mgr_ids = list(dict.fromkeys(state.order))
    mid_to_idx = {m: i for i, m in enumerate(mgr_ids)}
    n_managers = len(mgr_ids)
    cap = state.capacity
    limits = np.array([cap.forwards, cap.defense, cap.goalies], dtype="int64")
    base_counts = np.zeros((n_managers, 3), dtype="int64")
    for manager, roster in state.rosters.items():
        base_counts[mid_to_idx[manager]] = [
            roster.count("F"),
            roster.count("D"),
            roster.count("G"),
        ]
    owner_idx = mid_to_idx[owner]
    cap_total = cap.total

    # Per-manager fitted parameters, indexed by manager row.
    coef_rank = np.zeros(n_managers, dtype="float64")
    coef_aff = np.zeros(n_managers, dtype="float64")
    aff_matrix = np.zeros((n_managers, n_assets), dtype="float64")
    need_weight = 1.0
    for manager, model in models.items():
        idx = mid_to_idx[manager]
        coef_rank[idx] = model.coefficients.rank
        coef_aff[idx] = model.coefficients.affinity
        need_weight = model.need_weight
        aff_matrix[idx] = [
            float(model.affinity.get(int(a.team_id), 0.0)) if a.team_id is not None else 0.0
            for a in pool
        ]

    pos_masks = [posc == p for p in range(3)]

    rem = state.order[state.pick_index :]
    rem_m = [mid_to_idx[m] for m in rem]
    owner_needed = cap_total - int(base_counts[owner_idx].sum())
    owner_positions = [k for k, mi in enumerate(rem_m) if mi == owner_idx]
    last_owner_k = owner_positions[owner_needed - 1]

    rollouts = cfg.rollouts
    rows = np.arange(rollouts)
    neg_inf = float("-inf")
    base_owner_value = _owner_roster_value(state, owner)
    means: list[float] = []
    for asset in candidate_assets:
        idx_c = key_to_idx[asset.key]
        alive = np.ones((rollouts, n_assets), dtype=bool)
        counts = np.broadcast_to(base_counts, (rollouts, n_managers, 3)).copy()
        owner_total = np.zeros(rollouts, dtype="float64")

        alive[:, idx_c] = False
        counts[:, owner_idx, posc[idx_c]] += 1
        owner_total += val[idx_c]
        owner_taken = 1

        for k in range(1, last_owner_k + 1):
            mgr_i = rem_m[k]
            cnt_m = counts[:, mgr_i, :]
            cap_ok = cnt_m < limits
            legal = alive & cap_ok[:, posc]
            if mgr_i == owner_idx:
                if cfg.depth is not None and owner_taken >= cfg.depth:
                    _vec_fill_owner(
                        alive,
                        counts,
                        owner_idx,
                        val,
                        vor_owner,
                        posc,
                        limits,
                        owner_total,
                        cap_total - owner_taken,
                    )
                    owner_taken = cap_total
                    break
                _require_legal_rows(legal, mgr_ids[mgr_i])
                scores = np.where(legal, vor_owner[None, :], neg_inf)
                choice = np.argmax(scores, axis=1)
                owner_total += val[choice]
                owner_taken += 1
            else:
                _require_legal_rows(legal, mgr_ids[mgr_i])
                urgency = (limits - cnt_m) / limits
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
                utility = (
                    coef_rank[mgr_i] * rank_z
                    + coef_aff[mgr_i] * aff_matrix[mgr_i][None, :]
                    + need_weight * urgency[:, posc]
                )
                masked = np.where(legal, utility, neg_inf)
                choice = np.argmax(masked, axis=1)
            alive[rows, choice] = False
            counts[rows, mgr_i, posc[choice]] += 1

        # Same E[roster] definition as the greedy and object paths: include the
        # owner's already-drafted roster value.
        means.append(float(owner_total.mean()) + base_owner_value)
    return means


def _expected_values(
    state: DraftState,
    owner: str,
    candidate_assets: Sequence[DraftAsset],
    opponent_model: OpponentModel | Mapping[str, OpponentModel],
    replacement: Mapping[str, float],
    cfg: RecommendConfig,
) -> list[float]:
    """Expected final owner value per candidate, vectorized where possible.

    Uses the batched numpy kernel when the opponents are a single greedy model or a
    per-manager set of deterministic fitted models (the <10s fast paths); otherwise
    falls back to the general object-model rollout.
    """
    if isinstance(opponent_model, GreedyOpponentModel):
        return _vectorized_greedy_expected(
            state, owner, candidate_assets, opponent_model, replacement, cfg
        )
    fitted_models = _fitted_zero_temp_models(opponent_model, state)
    if fitted_models is not None:
        return _vectorized_fitted_expected(
            state, owner, candidate_assets, fitted_models, replacement, cfg
        )
    return [
        _expected_value(state, owner, asset, opponent_model, replacement, cfg)
        for asset in candidate_assets
    ]


def choose_pick(
    state: DraftState,
    owner: str,
    opponent_model: OpponentModel | Mapping[str, OpponentModel],
    *,
    config: RecommendConfig | None = None,
    managers: int | None = None,
) -> DraftAsset:
    """Lean argmax pick: rollout-expected best asset, skipping explanations/survival.

    The policy used by the strategy comparison and any caller that only needs the
    chosen asset. Same rollout as :func:`recommend_pick` but without the survival
    estimate or the explained board, so it is cheap enough to call at every pick of a
    full simulated draft.
    """
    cfg = config or RecommendConfig()
    n_managers = managers if managers is not None else len(state.rosters)
    replacement = replacement_levels(state, n_managers)
    candidates = _prune_candidates(state, owner, replacement, cfg.max_candidates)
    if not candidates:
        raise ValueError(f"owner {owner!r} has no legal pick")
    expecteds = _expected_values(
        state, owner, [c.asset for c in candidates], opponent_model, replacement, cfg
    )
    best_asset = candidates[0].asset
    best_expected = float("-inf")
    best_vor = float("-inf")
    for candidate, expected in zip(candidates, expecteds, strict=True):
        if expected > best_expected or (
            expected == best_expected
            and (
                candidate.vor > best_vor
                or (candidate.vor == best_vor and candidate.asset.key < best_asset.key)
            )
        ):
            best_asset = candidate.asset
            best_expected = expected
            best_vor = candidate.vor
    return best_asset


def recommend_pick(
    state: DraftState,
    owner: str,
    opponent_model: OpponentModel | Mapping[str, OpponentModel],
    *,
    config: RecommendConfig | None = None,
    managers: int | None = None,
) -> Recommendation:
    """Recommend the owner's best pick by multi-step Monte-Carlo rollout.

    ``owner`` must be on the clock. Every legal candidate (pruned to the top
    ``config.max_candidates`` by VOR) is rolled out to the end of the draft against
    ``opponent_model``; the pick maximising expected final-roster projection wins.
    Each returned :class:`PickEvaluation` carries the reasoning the acceptance asks for
    (VOR, ``P(survives to next pick)``, expected delta vs. the #2 option, positional
    need). Deterministic given ``(state, config)``.
    """
    cfg = config or RecommendConfig()
    if state.is_complete:
        raise ValueError("draft is complete; nothing to recommend")
    if state.current_manager != owner:
        raise ValueError(
            f"owner {owner!r} is not on the clock (current: {state.current_manager!r})"
        )
    n_managers = managers if managers is not None else len(state.rosters)
    replacement = replacement_levels(state, n_managers)
    candidates = _prune_candidates(state, owner, replacement, cfg.max_candidates)
    if not candidates:
        raise ValueError(f"owner {owner!r} has no legal pick")

    roster = state.rosters[owner]
    expecteds = _expected_values(
        state, owner, [c.asset for c in candidates], opponent_model, replacement, cfg
    )
    ranked = sorted(
        zip(candidates, expecteds, strict=True),
        key=lambda pair: (-pair[1], -pair[0].vor, pair[0].asset.key),
    )
    second_best = ranked[1][1] if len(ranked) > 1 else ranked[0][1]

    evaluations: list[PickEvaluation] = []
    # Survival is a display-only explanation, so estimate it just for the surfaced
    # top-N rather than every rolled-out candidate (keeps the <10s budget).
    for candidate, expected in ranked[: cfg.top_n]:
        asset = candidate.asset
        survival = (
            survival_probability(
                state,
                asset,
                owner,
                opponent_model,
                rollouts=cfg.survival_rollouts,
                seed=cfg.seed,
            )
            if cfg.compute_survival
            else 0.0
        )
        limit = state.capacity.limit(asset.position)
        open_slots = limit - roster.count(asset.position)
        evaluations.append(
            PickEvaluation(
                asset=asset,
                expected_points=expected,
                immediate_value=asset_value(asset),
                vor=candidate.vor,
                replacement=candidate.replacement,
                survival=survival,
                open_slots=open_slots,
                position_limit=limit,
                delta_vs_next=expected - second_best,
            )
        )

    return Recommendation(
        owner=owner,
        pick_index=state.pick_index,
        rollouts=cfg.rollouts,
        depth=cfg.depth,
        replacement=replacement,
        evaluations=evaluations,
        candidates_considered=len(candidates),
        seed=cfg.seed,
    )


# ── Strategy comparison (multi-step vs. greedy-VOR vs. one-step) ───────────

_Strategy = Literal["greedy_vor", "one_step", "multi_step"]

# Real NHL team ids the synthetic pool spreads assets across so the fitted opponent
# model's team-affinity signal has something to bite on.
_SYNTHETIC_TEAM_IDS: tuple[int, ...] = tuple(range(1, 33))


@dataclass(frozen=True)
class _PositionRunOpponent(OpponentModel):
    """Opponent that over-drafts one position, creating a run greedy-VOR can't see.

    Balanced fitted/greedy opponents deplete positions evenly, so a static VOR board
    is already optimal against them. Real drafts have runs — a stretch where everyone
    hammers one position — which push that position *below* its pool-wide replacement
    level before a greedy drafter reacts. This model reproduces that: it adds a large
    ``bonus`` to the favoured position, so a multi-step lookout (which simulates it)
    correctly grabs that position early while greedy-VOR waits and gets stuck with
    scraps. Used only in the comparison's stress scenario.
    """

    favored: str
    bonus: float = 12.0
    need_weight: float = 4.0
    temperature: float = 0.4

    def pick(self, state: DraftState, manager: str, rng: random.Random) -> DraftAsset:
        legal = state.legal_assets(manager)
        if not legal:
            raise ValueError(f"manager {manager!r} has no legal asset to draft")
        roster = state.rosters[manager]
        scores: list[float] = []
        for asset in legal:
            limit = state.capacity.limit(asset.position)
            urgency = (limit - roster.count(asset.position)) / limit if limit else 0.0
            bonus = self.bonus if asset.position == self.favored else 0.0
            scores.append(asset.rank_value + self.need_weight * urgency + bonus)
        if self.temperature <= 0.0:
            best = max(range(len(legal)), key=lambda i: (scores[i], legal[i].key))
            return legal[best]
        highest = max(scores)
        weights = [math.exp((s - highest) / self.temperature) for s in scores]
        threshold = rng.random() * sum(weights)
        cumulative = 0.0
        for index, weight in enumerate(weights):
            cumulative += weight
            if threshold <= cumulative:
                return legal[index]
        return legal[-1]


def build_synthetic_pool(
    managers: int,
    *,
    allow_ir: bool,
    seed: int = 20260827,
    contention: float = 1.15,
) -> list[DraftAsset]:
    """A deterministic, self-contained draft pool sized to contest a league.

    The pool holds ``contention`` times each position's league-wide demand so a
    position can plausibly run dry before a manager's next turn — the regime where a
    multi-step lookahead earns its keep. Projections decay linearly with rank plus a
    seeded jitter, and assets are spread across real NHL team ids so the fitted
    opponent model's affinity term is meaningful. ``rank_value`` tracks projection
    (public perception), so no strategy gets a hidden information edge.
    """
    rng = random.Random(seed)
    forwards_per = 6 if allow_ir else 5
    defense_per = 4 if allow_ir else 3
    demand = {
        "F": forwards_per * managers,
        "D": defense_per * managers,
        "G": managers,
    }
    base = {"F": 22.0, "D": 16.0, "G": 30.0}
    pool: list[DraftAsset] = []
    player_id = 1000
    for position in ("F", "D"):
        buffer = max(2, round(demand[position] * (contention - 1.0)))
        count = demand[position] + buffer
        for i in range(count):
            projection = base[position] - 0.15 * i + rng.uniform(-1.0, 1.0)
            projection = max(0.5, projection)
            team_id = _SYNTHETIC_TEAM_IDS[player_id % len(_SYNTHETIC_TEAM_IDS)]
            pool.append(
                DraftAsset(
                    key=f"P{player_id}",
                    name=f"{position}{i}",
                    position=position,
                    rank_value=projection,
                    player_id=player_id,
                    team_id=team_id,
                    team_abbrev=f"T{team_id}",
                    projection=projection,
                )
            )
            player_id += 1
    team_count = demand["G"] + max(2, round(demand["G"] * (contention - 1.0)))
    for i in range(team_count):
        projection = base["G"] - 0.9 * i + rng.uniform(-1.0, 1.0)
        projection = max(0.5, projection)
        team_id = _SYNTHETIC_TEAM_IDS[i % len(_SYNTHETIC_TEAM_IDS)]
        pool.append(
            DraftAsset(
                key=f"T{team_id}",
                name=f"G{team_id}",
                position="G",
                rank_value=projection,
                team_id=team_id,
                team_abbrev=f"T{team_id}",
                projection=projection,
            )
        )
    return pool


def _decision_pick(
    state: DraftState,
    owner: str,
    opponent_model: OpponentModel | Mapping[str, OpponentModel],
    strategy: _Strategy,
    replacement: Mapping[str, float],
    cfg: RecommendConfig,
    managers: int,
) -> DraftAsset:
    """The single pick ``strategy`` makes for the owner at the current slot."""
    if strategy == "greedy_vor":
        return greedy_vor_pick(state, owner, replacement)
    depth = 1 if strategy == "one_step" else None
    return choose_pick(
        state,
        owner,
        opponent_model,
        config=replace(cfg, depth=depth),
        managers=managers,
    )


def _continue_to_end(
    state: DraftState,
    owner: str,
    opponent_model: OpponentModel | Mapping[str, OpponentModel],
    replacement: Mapping[str, float],
    seed: int,
) -> float:
    """Finish the draft with a fixed greedy-VOR owner tail + opponents; owner value.

    The common continuation shared by all three strategies once they diverge at the
    decision slot, seeded identically so the tail is paired across strategies. Isolates
    the quality of the single decision under test.
    """
    rng = random.Random(seed)
    while not state.is_complete:
        current = state.current_manager
        if current == owner:
            state.apply_pick(greedy_vor_pick(state, owner, replacement))
        else:
            model = _resolve_model(opponent_model, current)
            state.apply_pick(model.pick(state, current, rng))
    return _owner_roster_value(state, owner)


def _play_to_decision(
    base_state: DraftState,
    owner: str,
    opponent_model: OpponentModel | Mapping[str, OpponentModel],
    replacement: Mapping[str, float],
    prefix: int,
    seed: int,
) -> DraftState | None:
    """Advance a fresh draft to the owner's ``prefix``-th pick (greedy tail + opponents).

    Returns the state with the owner on the clock at the decision slot, or ``None`` if
    the draft ends before the owner reaches that many picks (skip such drafts).
    """
    state = base_state.copy()
    rng = random.Random(seed)
    owner_made = 0
    while not state.is_complete:
        current = state.current_manager
        if current == owner:
            if owner_made == prefix:
                return state
            state.apply_pick(greedy_vor_pick(state, owner, replacement))
            owner_made += 1
        else:
            model = _resolve_model(opponent_model, current)
            state.apply_pick(model.pick(state, current, rng))
    return None


@dataclass
class StrategyComparison:
    """Average final owner-roster projection for each drafting strategy."""

    n_drafts: int
    owner: str
    managers: int
    allow_ir: bool
    rollouts: int
    max_candidates: int
    opponent_kind: str
    means: dict[str, float]
    seed: int = 20260827
    scenario: str = "balanced fitted opponents"
    tie_epsilon: float = 0.05

    @property
    def beats_greedy(self) -> bool:
        return self.means["multi_step"] > self.means["greedy_vor"]

    @property
    def beats_one_step(self) -> bool:
        return self.means["multi_step"] > self.means["one_step"]

    @property
    def ties_greedy(self) -> bool:
        return abs(self.means["multi_step"] - self.means["greedy_vor"]) <= self.tie_epsilon

    def report_lines(self) -> list[str]:
        """Honest Markdown comparison (SPEC section 7 — report misses, never hide)."""
        multi = self.means["multi_step"]
        greedy = self.means["greedy_vor"]
        one = self.means["one_step"]
        if self.ties_greedy:
            verdict = "matches greedy-VOR (statistical tie)"
        elif self.beats_greedy and self.beats_one_step:
            verdict = "beats both baselines"
        elif self.beats_greedy:
            verdict = "beats greedy only"
        elif self.beats_one_step:
            verdict = "beats one-step only"
        else:
            verdict = "does not beat the baselines"
        return [
            f"## Scenario: {self.scenario}",
            "",
            f"- Simulated drafts: {self.n_drafts} (seeded, {self.opponent_kind} opponents)",
            f"- League: {self.managers} managers, IR {'on' if self.allow_ir else 'off'}, "
            f"owner seat {self.owner}",
            f"- Rollouts per recommendation: {self.rollouts}, candidates: {self.max_candidates}",
            "",
            "| Strategy | Mean final roster projection | Delta vs. greedy |",
            "| :------- | ---------------------------: | ---------------: |",
            f"| Greedy-VOR (baseline a) | {greedy:.3f} | +0.000 |",
            f"| One-step lookahead (baseline b) | {one:.3f} | {one - greedy:+.3f} |",
            f"| Multi-step rollout | {multi:.3f} | {multi - greedy:+.3f} |",
            "",
            f"Multi-step vs. one-step: {multi - one:+.3f}. Verdict: multi-step {verdict}.",
        ]

    def manifest(self) -> dict[str, Any]:
        return {
            "scenario": self.scenario,
            "n_drafts": self.n_drafts,
            "owner": self.owner,
            "managers": self.managers,
            "allow_ir": self.allow_ir,
            "rollouts": self.rollouts,
            "max_candidates": self.max_candidates,
            "opponent_kind": self.opponent_kind,
            "seed": self.seed,
            "means": {k: round(v, 6) for k, v in self.means.items()},
            "multi_step_beats_greedy": self.beats_greedy,
            "multi_step_beats_one_step": self.beats_one_step,
            "multi_step_ties_greedy": self.ties_greedy,
        }


def compare_strategies(
    pool: Sequence[DraftAsset],
    managers_list: Sequence[str],
    owner: str,
    opponent_model: OpponentModel | Mapping[str, OpponentModel],
    *,
    allow_ir: bool = False,
    config: RecommendConfig | None = None,
    n_drafts: int = 200,
    decision_prefix: int | None = None,
    seed: int = 20260827,
    opponent_kind: str = "greedy",
    scenario: str = "balanced fitted opponents",
) -> StrategyComparison:
    """Compare multi-step vs. greedy-VOR vs. one-step over ``n_drafts`` seeded drafts.

    Single-decision, same-slot framing (acceptance: "from the same slot"): each draft
    is advanced to the owner's ``decision_prefix``-th pick with a greedy tail against
    seeded opponents; from that *shared* state each strategy makes exactly one pick,
    and the draft is then finished with an identical greedy-VOR tail + opponents seeded
    the same way. The mean final owner-roster projection isolates the quality of that
    one decision. Honest by construction: one fixed config, every draft counted, no
    per-seed or per-slot cherry-picking (acceptance / SPEC section 7).
    """
    if n_drafts < 1:
        raise ValueError(f"n_drafts must be >= 1, got {n_drafts}")
    cfg = config or RecommendConfig(compute_survival=False)
    managers = len(managers_list)
    base = DraftState.new(managers_list, pool, allow_ir=allow_ir)
    replacement = replacement_levels(base, managers)
    prefix = decision_prefix if decision_prefix is not None else base.capacity.total // 3
    totals = {"greedy_vor": 0.0, "one_step": 0.0, "multi_step": 0.0}
    strategies: tuple[_Strategy, ...] = ("greedy_vor", "one_step", "multi_step")
    counted = 0
    for draft in range(n_drafts):
        draft_seed = seed + draft
        decision = _play_to_decision(base, owner, opponent_model, replacement, prefix, draft_seed)
        if decision is None:
            continue
        counted += 1
        for strategy in strategies:
            state = decision.copy()
            pick = _decision_pick(
                state, owner, opponent_model, strategy, replacement, cfg, managers
            )
            state.apply_pick(pick)
            totals[strategy] += _continue_to_end(
                state, owner, opponent_model, replacement, draft_seed
            )
    if counted == 0:
        raise ValueError("no draft reached the decision slot; lower decision_prefix")
    means = {k: v / counted for k, v in totals.items()}
    return StrategyComparison(
        n_drafts=counted,
        owner=owner,
        managers=managers,
        allow_ir=allow_ir,
        rollouts=cfg.rollouts,
        max_candidates=cfg.max_candidates,
        opponent_kind=opponent_kind,
        means=means,
        seed=seed,
        scenario=scenario,
    )


def _league_managers(fitted: FittedLeagueOpponents, limit: int) -> list[str]:
    ranked = sorted(fitted.manager_pick_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [manager for manager, _ in ranked[:limit]]


def evaluate_recommendation_strategies_from_normalized(
    *,
    normalized_dir: Path,
    artifact_dir: Path = DEFAULT_RECOMMEND_ARTIFACT_DIR,
    managers: int = 4,
    n_drafts: int = 200,
    rollouts: int = 40,
    max_candidates: int = 6,
    allow_ir: bool = False,
    opponent_temperature: float = 0.75,
    run_bonus: float = 12.0,
    seed: int = 20260827,
) -> StrategyComparison:
    """Fit league opponents, run both comparison scenarios, and commit report + manifest.

    Two honest scenarios over the deterministic synthetic pool:

    1. **Balanced fitted opponents** (the acceptance's primary case) — the US-020
       fitted league model (``league_draft_picks.parquet``) with a positive
       ``opponent_temperature`` so the seeded playouts differ. Fitted opponents draft
       positions evenly, so a static VOR board is already optimal and multi-step is
       expected to *tie* it (and edge one-step).
    2. **Positional-run opponents** (:class:`_PositionRunOpponent`) — opponents that
       hammer one position, pushing it below its pool-wide replacement level. This is
       where a static VOR board is blind and the multi-step lookahead, which simulates
       the run, should beat both baselines.

    Writes a combined ``report.md`` + ``manifest.json`` under ``artifact_dir``
    (re-included in .gitignore like the other model reports). Returns the primary
    (fitted-opponent) comparison. Deterministic given the inputs + seed.
    """
    import pandas as pd

    picks = pd.read_parquet(normalized_dir / "league_draft_picks.parquet")
    fitted = fit_opponent_models(picks, OpponentFitConfig(temperature=opponent_temperature))
    managers_list = _league_managers(fitted, managers)
    if len(managers_list) < 2:
        raise ValueError("need at least two league managers to run the comparison")
    owner = managers_list[0]
    pool = build_synthetic_pool(len(managers_list), allow_ir=allow_ir, seed=seed)
    cfg = RecommendConfig(
        rollouts=rollouts,
        max_candidates=max_candidates,
        compute_survival=False,
        seed=seed,
    )

    fitted_comparison = compare_strategies(
        pool,
        managers_list,
        owner,
        fitted.as_mapping(managers_list),
        allow_ir=allow_ir,
        config=cfg,
        n_drafts=n_drafts,
        seed=seed,
        opponent_kind="fitted-league",
        scenario="balanced fitted opponents",
    )
    run_opponent = _PositionRunOpponent(favored="F", bonus=run_bonus)
    run_comparison = compare_strategies(
        pool,
        managers_list,
        owner,
        run_opponent,
        allow_ir=allow_ir,
        config=cfg,
        n_drafts=n_drafts,
        seed=seed,
        opponent_kind="positional-run",
        scenario="positional-run opponents (forward run)",
    )

    lines = ["# Multi-step pick recommendation comparison", ""]
    lines += fitted_comparison.report_lines()
    lines += [""]
    lines += run_comparison.report_lines()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (artifact_dir / "manifest.json").write_text(
        json.dumps(
            {
                "balanced_fitted": fitted_comparison.manifest(),
                "positional_run": run_comparison.manifest(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return fitted_comparison


def build_pool_from_frames(
    skaters: pd.DataFrame, teams: pd.DataFrame, *, ir: bool = False
) -> list[DraftAsset]:
    """Build a draftable pool from the two in-memory projection tables.

    Skater rows become F/D assets priced by ``expected_points``; team rows become the
    whole-team goalie (``G``) asset priced by ``e_goalie_points``. ``rank_value`` (the
    opponents' public-perception signal) tracks the projection. Skater ``team_id`` is
    resolved from the teams table via ``team_abbrev`` so elimination and team affinity
    still work.

    When ``ir`` is set, injured skaters carrying an ``ir_stash_value`` (US-022) are
    repriced to that stash value, so the optimizer values an ``IR_F`` / ``IR_D`` stash
    for the retroactive-swap points it really adds, not for full-health production.
    """
    import pandas as pd

    from draft_oracle.optimize.ir_value import reprice_pool_for_ir

    abbrev_to_id = {
        str(rec["team_abbrev"]): int(rec["team_id"]) for rec in teams.to_dict("records")
    }
    pool: list[DraftAsset] = []
    for rec in skaters.to_dict("records"):
        position = str(rec["position"])
        if position not in ("F", "D"):
            continue
        projection = float(rec["expected_points"])
        pool.append(
            DraftAsset(
                key=f"P{int(rec['player_id'])}",
                name=str(rec["player_name"]),
                position=position,  # type: ignore[arg-type]
                rank_value=projection,
                player_id=int(rec["player_id"]),
                team_id=abbrev_to_id.get(str(rec["team_abbrev"])),
                team_abbrev=str(rec["team_abbrev"]),
                projection=projection,
            )
        )
    for rec in teams.to_dict("records"):
        projection = float(rec["e_goalie_points"])
        pool.append(
            DraftAsset(
                key=f"T{int(rec['team_id'])}",
                name=str(rec["team_abbrev"]),
                position="G",
                rank_value=projection,
                team_id=int(rec["team_id"]),
                team_abbrev=str(rec["team_abbrev"]),
                projection=projection,
            )
        )
    if ir and "ir_stash_value" in skaters.columns:
        stash_value_by_player = {
            int(rec["player_id"]): float(rec["ir_stash_value"])
            for rec in skaters.to_dict("records")
            if pd.notna(rec.get("ir_stash_value"))
        }
        if stash_value_by_player:
            pool = reprice_pool_for_ir(pool, stash_value_by_player)
    return pool


def build_pool_from_projection_artifact(
    artifact_dir: Path, *, ir: bool = False
) -> list[DraftAsset]:
    """Build a draftable pool from a US-017 projection artifact directory.

    Thin disk wrapper over :func:`build_pool_from_frames`: reads ``skaters.parquet`` and
    ``teams.parquet`` from ``artifact_dir`` and delegates the asset construction.
    """
    import pandas as pd

    skaters = pd.read_parquet(artifact_dir / "skaters.parquet")
    teams = pd.read_parquet(artifact_dir / "teams.parquet")
    return build_pool_from_frames(skaters, teams, ir=ir)
