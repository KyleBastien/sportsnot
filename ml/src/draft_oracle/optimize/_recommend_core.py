"""Value primitives, config, and the object-model rollout policy for recommend.

The leaf layer of the pick-recommendation engine: everything the vectorized kernels
(:mod:`draft_oracle.optimize._recommend_kernels`) and the public surface
(:mod:`draft_oracle.optimize.recommend`) build on, with no dependency back on either
so the package stays import-cycle free. See :mod:`draft_oracle.optimize.recommend`
for the engine's design rationale.
"""

from __future__ import annotations

import random
from collections.abc import Mapping
from dataclasses import dataclass

from draft_oracle.optimize.simulator import DraftAsset, DraftState, OpponentModel
from draft_oracle.optimize.vor import replacement_level

# A rollout averages over at least this many seeded playouts (SPEC/acceptance floor).
DEFAULT_ROLLOUTS = 500
# Survival probability is a cheap by-product estimate; it needs far fewer rollouts.
DEFAULT_SURVIVAL_ROLLOUTS = 200
# Only the top-VOR assets are ever the best current pick; rolling out more wastes time.
DEFAULT_MAX_CANDIDATES = 24

_ROLLOUT_SALT = 1_000_003

_POS_INDEX: dict[str, int] = {"F": 0, "D": 1, "G": 2}


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
        checks: tuple[tuple[int, str, int], ...] = (
            (self.rollouts, "rollouts", 1),
            (self.max_candidates, "max_candidates", 1),
            (self.survival_rollouts, "survival_rollouts", 1),
            (self.top_n, "top_n", 1),
        )
        for value, name, minimum in checks:
            if value < minimum:
                raise ValueError(f"{name} must be >= {minimum}, got {value}")
        if self.depth is not None and self.depth < 1:
            raise ValueError(f"depth must be >= 1 or None, got {self.depth}")


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
