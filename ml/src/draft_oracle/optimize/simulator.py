"""Rules-enforcing snake-draft simulator + fallback opponent model (US-019).

The optimizer needs an engine it can *roll out on*: a faithful reproduction of a
SportsNot re-draft that any lookahead can push picks through and read state back
from. This module provides that engine plus a baseline opponent model and a
Monte-Carlo survival estimator.

Everything is scored and validated through :mod:`draft_oracle.rules` (SPEC section 1),
so the simulator can never produce a state the real app would reject:

* **Snake order** — the pick sequence comes from :func:`draft_oracle.rules.snake_order`.
* **Per-position roster limits** — 5 F / 3 D / 1 G active, ``+1 IR_F`` / ``+1 IR_D``
  only when the league enables IR. A manager who already holds their limit at a
  position simply cannot pick another asset there (a manager with 5 F must take D
  or G). IR slots are pickable *only* when IR is enabled.
* **No duplicates** — an asset leaves the pool the instant it is drafted.
* **Eliminated teams** — a team (and every skater on it) whose ``team_id`` is in
  ``eliminated_team_ids`` is removed from the pool up front and can never be
  drafted. There is **no** mid-round substitution of eliminated players (the 2024
  Trouba->Kulikov sheet swap was a one-time favor, not a rule — SPEC section 1).

The fallback :class:`GreedyOpponentModel` drafts greedily by public perception
(regular-season points, ``rank_value``) with softmax noise (a configurable
``temperature``) and positional-need awareness (positions a manager still needs a
lot of get a bump as they empty out). It sits behind the pluggable
:class:`OpponentModel` interface so fitted models (US-020) can drop in.

:func:`survival_probability` runs Monte-Carlo rollouts of the opponents' picks
between now and a manager's next turn and returns ``P(candidate still available)``.
Every stochastic path takes an explicit seed, so ``(state, seed)`` fully determines
the result (SPEC section 3).
"""

from __future__ import annotations

import math
import random
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

from draft_oracle.rules import (
    RosterSlot,
    RosterValidation,
    snake_order,
    validate_roster,
)

__all__ = [
    "DEFAULT_NEED_WEIGHT",
    "DEFAULT_ROLLOUTS",
    "DEFAULT_TEMPERATURE",
    "DraftAsset",
    "DraftState",
    "GreedyOpponentModel",
    "ManagerRoster",
    "OpponentModel",
    "RosterCapacity",
    "roster_capacity",
    "run_draft",
    "survival_probability",
    "validate_draft",
]

BasePosition = Literal["F", "D", "G"]

# Active-roster slots per manager (SPEC section 1); IR adds one F and one D.
_BASE_FORWARDS = 5
_BASE_DEFENSE = 3
_BASE_GOALIES = 1
_IR_EXTRA_FORWARD = 1
_IR_EXTRA_DEFENSE = 1

# Fallback-opponent defaults.
DEFAULT_TEMPERATURE = 0.0  # 0 == deterministic greedy (pure best-available)
DEFAULT_NEED_WEIGHT = 4.0  # points-scale bump for positions a manager still needs
DEFAULT_ROLLOUTS = 1000


@dataclass(frozen=True)
class DraftAsset:
    """A single draftable asset: a skater (F/D) or a team's goaltending (G).

    ``key`` is the unique pool identity used for de-duplication. ``rank_value`` is
    the public-perception score the fallback opponent drafts by (regular-season
    points, SPEC section 8). Skater assets carry a ``player_id``; the goalie slot
    is an entire NHL team, so team/goalie assets carry a ``team_id``.
    """

    key: str
    name: str
    position: BasePosition
    rank_value: float
    player_id: int | None = None
    team_id: int | None = None
    team_abbrev: str = ""
    projection: float | None = None


@dataclass(frozen=True)
class RosterCapacity:
    """Per-manager slot capacity per base position (SPEC section 1)."""

    forwards: int
    defense: int
    goalies: int

    @property
    def total(self) -> int:
        """Total picks a manager makes to fill every slot."""
        return self.forwards + self.defense + self.goalies

    def limit(self, position: BasePosition) -> int:
        """Slot limit for ``position``."""
        if position == "F":
            return self.forwards
        if position == "D":
            return self.defense
        return self.goalies


def roster_capacity(allow_ir: bool) -> RosterCapacity:
    """Slot capacity for the standard (``5F/3D/1G``) or IR-enabled roster.

    IR adds one forward slot (``IR_F``) and one defense slot (``IR_D``) — never a
    goalie slot — for 11 picks total instead of 9.
    """
    return RosterCapacity(
        forwards=_BASE_FORWARDS + (_IR_EXTRA_FORWARD if allow_ir else 0),
        defense=_BASE_DEFENSE + (_IR_EXTRA_DEFENSE if allow_ir else 0),
        goalies=_BASE_GOALIES,
    )


@dataclass
class ManagerRoster:
    """A single manager's drafted assets, bucketed by base position."""

    manager_id: str
    forwards: list[DraftAsset] = field(default_factory=list)
    defense: list[DraftAsset] = field(default_factory=list)
    goalies: list[DraftAsset] = field(default_factory=list)

    def bucket(self, position: BasePosition) -> list[DraftAsset]:
        """The asset list backing ``position``."""
        if position == "F":
            return self.forwards
        if position == "D":
            return self.defense
        return self.goalies

    def count(self, position: BasePosition) -> int:
        """Number of assets held at ``position``."""
        return len(self.bucket(position))

    def add(self, asset: DraftAsset) -> None:
        """Append ``asset`` to its position bucket."""
        self.bucket(asset.position).append(asset)

    def all_assets(self) -> list[DraftAsset]:
        """Every drafted asset, forwards then defense then goalies."""
        return [*self.forwards, *self.defense, *self.goalies]

    def copy(self) -> ManagerRoster:
        """A shallow copy safe to mutate during a rollout (assets are frozen)."""
        return ManagerRoster(
            manager_id=self.manager_id,
            forwards=list(self.forwards),
            defense=list(self.defense),
            goalies=list(self.goalies),
        )


@dataclass
class DraftState:
    """A snapshot of a snake draft: order, capacity, live pool, and rosters.

    ``available`` is keyed by :attr:`DraftAsset.key`; an asset is removed the
    moment it is drafted. ``pick_index`` points at the next pick in ``order``.
    """

    order: tuple[str, ...]
    capacity: RosterCapacity
    allow_ir: bool
    available: dict[str, DraftAsset]
    rosters: dict[str, ManagerRoster]
    pick_index: int = 0

    @classmethod
    def new(
        cls,
        managers: Sequence[str],
        pool: Sequence[DraftAsset],
        *,
        allow_ir: bool,
        eliminated_team_ids: frozenset[int] = frozenset(),
    ) -> DraftState:
        """Build a fresh draft state.

        ``managers`` is the round-1 order; the full snake sequence is derived from
        it. Assets on an eliminated team are dropped from the pool up front and can
        never be drafted (SPEC section 1: no mid-round substitution).
        """
        if not managers:
            raise ValueError("managers must be non-empty")
        normalized_managers = [manager.casefold() for manager in managers]
        if len(set(normalized_managers)) != len(normalized_managers):
            raise ValueError("managers must be unique (case-insensitive)")
        capacity = roster_capacity(allow_ir)
        order = tuple(snake_order(managers, capacity.total))
        available: dict[str, DraftAsset] = {}
        for asset in pool:
            if asset.team_id is not None and asset.team_id in eliminated_team_ids:
                continue
            # Fail-safe: once any team is eliminated, a skater whose ``team_id`` never
            # resolved cannot be confirmed to survive, so it must not stay draftable
            # (a whole-team goalie asset always carries a ``team_id``).
            if eliminated_team_ids and asset.team_id is None:
                continue
            if asset.key in available:
                raise ValueError(f"duplicate asset key in pool: {asset.key!r}")
            available[asset.key] = asset
        rosters = {manager: ManagerRoster(manager) for manager in managers}
        return cls(
            order=order,
            capacity=capacity,
            allow_ir=allow_ir,
            available=available,
            rosters=rosters,
            pick_index=0,
        )

    @property
    def is_complete(self) -> bool:
        """True once every pick in ``order`` has been made."""
        return self.pick_index >= len(self.order)

    @property
    def current_manager(self) -> str:
        """The manager on the clock for the next pick."""
        if self.is_complete:
            raise ValueError("draft is complete; no manager is on the clock")
        return self.order[self.pick_index]

    def has_capacity(self, manager: str, position: BasePosition) -> bool:
        """Whether ``manager`` may still draft an asset at ``position``."""
        return self.rosters[manager].count(position) < self.capacity.limit(position)

    def legal_assets(self, manager: str) -> list[DraftAsset]:
        """Assets ``manager`` may legally draft right now (respecting slot limits)."""
        return [
            asset for asset in self.available.values() if self.has_capacity(manager, asset.position)
        ]

    def place(self, manager: str, asset: DraftAsset) -> None:
        """Assign ``asset`` to ``manager``, removing it from the pool.

        Rejects assets that are unavailable or would exceed the manager's limit at
        that position — the simulator degrades loudly, never silently (SPEC section 7).
        """
        if asset.key not in self.available:
            raise ValueError(f"asset {asset.key!r} is not available")
        if not self.has_capacity(manager, asset.position):
            raise ValueError(f"manager {manager!r} is full at position {asset.position!r}")
        del self.available[asset.key]
        self.rosters[manager].add(asset)

    def apply_pick(self, asset: DraftAsset) -> None:
        """Make the next ordered pick for :attr:`current_manager` with ``asset``."""
        manager = self.current_manager
        self.place(manager, asset)
        self.pick_index += 1

    def picks_until_next(self, manager: str) -> list[str]:
        """Managers picking between now and ``manager``'s next turn (exclusive).

        If ``manager`` is on the clock now, their current pick is skipped — the gap
        is the stretch of *opponent* picks before they are up again. Every id in the
        returned list is an opponent by construction.
        """
        start = self.pick_index
        if start < len(self.order) and self.order[start] == manager:
            start += 1
        gap: list[str] = []
        index = start
        while index < len(self.order) and self.order[index] != manager:
            gap.append(self.order[index])
            index += 1
        return gap

    def roster_slots(self, manager: str) -> list[RosterSlot]:
        """Canonical :class:`~draft_oracle.rules.RosterSlot` list for ``manager``.

        Extra forwards/defense beyond the active limit fill the ``IR_F`` / ``IR_D``
        slots so the composition lines up with the rules engine.
        """
        roster = self.rosters[manager]
        slots: list[RosterSlot] = []
        slots.extend(_slots_for(roster.forwards, "F", "IR_F", _BASE_FORWARDS))
        slots.extend(_slots_for(roster.defense, "D", "IR_D", _BASE_DEFENSE))
        for asset in roster.goalies:
            slots.append(RosterSlot(position="G", team_id=asset.team_id))
        return slots

    def copy(self) -> DraftState:
        """A deep-enough copy for a rollout: independent pool and rosters."""
        return DraftState(
            order=self.order,
            capacity=self.capacity,
            allow_ir=self.allow_ir,
            available=dict(self.available),
            rosters={mid: roster.copy() for mid, roster in self.rosters.items()},
            pick_index=self.pick_index,
        )


def _slots_for(
    assets: Sequence[DraftAsset],
    active: Literal["F", "D", "G"],
    ir: Literal["IR_F", "IR_D"],
    active_limit: int,
) -> list[RosterSlot]:
    slots: list[RosterSlot] = []
    for index, asset in enumerate(assets):
        position = active if index < active_limit else ir
        if asset.player_id is not None:
            slots.append(RosterSlot(position=position, player_id=asset.player_id))
        else:
            slots.append(RosterSlot(position=position, team_id=asset.team_id))
    return slots


# ── Opponent models ──────────────────────────────────────────────────────


class OpponentModel(ABC):
    """Pluggable draft policy: choose a legal asset for a manager on the clock."""

    @abstractmethod
    def pick(self, state: DraftState, manager: str, rng: random.Random) -> DraftAsset:
        """Return the asset ``manager`` drafts from ``state``."""
        raise NotImplementedError


@dataclass(frozen=True)
class GreedyOpponentModel(OpponentModel):
    """Greedy-by-public-perception opponent with softmax noise and need awareness.

    A manager scores every *legal* asset as ``rank_value + need_weight * urgency``,
    where ``urgency`` is the fraction of that position's slots still open
    (``open_slots / position_limit``). Early on every position is wide open so the
    bump is roughly uniform and public perception dominates (best available); as a
    position fills, its urgency falls and the still-needed positions float up.

    Scores are turned into probabilities by a softmax with the given
    ``temperature``: ``0`` picks the argmax (deterministic greedy), larger values
    add more noise. Ties at ``temperature == 0`` break by ``rank_value`` then key
    so the model is fully deterministic given the RNG stream.
    """

    temperature: float = DEFAULT_TEMPERATURE
    need_weight: float = DEFAULT_NEED_WEIGHT

    def pick(self, state: DraftState, manager: str, rng: random.Random) -> DraftAsset:
        legal = state.legal_assets(manager)
        if not legal:
            raise ValueError(f"manager {manager!r} has no legal asset to draft")
        roster = state.rosters[manager]
        scores: list[float] = []
        for asset in legal:
            limit = state.capacity.limit(asset.position)
            open_slots = limit - roster.count(asset.position)
            urgency = open_slots / limit if limit else 0.0
            scores.append(asset.rank_value + self.need_weight * urgency)
        index = _softmax_choice(legal, scores, rng, self.temperature)
        return legal[index]


def _softmax_choice(
    assets: Sequence[DraftAsset],
    scores: Sequence[float],
    rng: random.Random,
    temperature: float,
) -> int:
    """Index into ``assets`` sampled by a softmax over ``scores``.

    ``temperature <= 0`` returns the argmax, breaking ties by ``rank_value`` then
    ``key`` for determinism. Otherwise a numerically stable softmax is sampled with
    a single ``rng`` draw.
    """
    if temperature <= 0.0:
        best = 0
        for index in range(1, len(scores)):
            if _is_better(assets[index], scores[index], assets[best], scores[best]):
                best = index
        return best

    highest = max(scores)
    weights = [math.exp((score - highest) / temperature) for score in scores]
    total = sum(weights)
    threshold = rng.random() * total
    cumulative = 0.0
    for index, weight in enumerate(weights):
        cumulative += weight
        if threshold <= cumulative:
            return index
    return len(weights) - 1


def _is_better(
    asset: DraftAsset,
    score: float,
    best_asset: DraftAsset,
    best_score: float,
) -> bool:
    if score != best_score:
        return score > best_score
    if asset.rank_value != best_asset.rank_value:
        return asset.rank_value > best_asset.rank_value
    return asset.key < best_asset.key


# ── Draft execution & analysis ───────────────────────────────────────────


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


def run_draft(
    state: DraftState,
    opponent_model: OpponentModel | Mapping[str, OpponentModel],
    *,
    seed: int = 0,
) -> DraftState:
    """Play ``state`` to completion, each manager picking via its opponent model.

    ``opponent_model`` is one policy applied to everyone, or a per-manager mapping.
    A single seeded RNG threads through every pick, so ``(state, seed)`` fully
    determines the resulting draft. Mutates and returns ``state``.
    """
    rng = random.Random(seed)
    while not state.is_complete:
        manager = state.current_manager
        model = _resolve_model(opponent_model, manager)
        asset = model.pick(state, manager, rng)
        state.apply_pick(asset)
    return state


def validate_draft(state: DraftState) -> dict[str, RosterValidation]:
    """Validate every manager's roster through :func:`draft_oracle.rules.validate_roster`.

    Builds a ``player_id -> team_id`` map from the drafted skaters so eliminated-team
    membership is checked, and returns one validation result per manager.
    """
    player_team_ids: dict[int, int] = {}
    for roster in state.rosters.values():
        for asset in roster.all_assets():
            if asset.player_id is not None and asset.team_id is not None:
                player_team_ids[asset.player_id] = asset.team_id
    results: dict[str, RosterValidation] = {}
    for manager in state.rosters:
        results[manager] = validate_roster(
            state.roster_slots(manager),
            allow_ir_slots=state.allow_ir,
            player_team_ids=player_team_ids,
        )
    return results


def survival_probability(
    state: DraftState,
    candidate: DraftAsset,
    manager: str,
    opponent_model: OpponentModel | Mapping[str, OpponentModel],
    *,
    rollouts: int = DEFAULT_ROLLOUTS,
    seed: int = 0,
) -> float:
    """Monte-Carlo estimate of ``P(candidate survives to manager's next pick)``.

    Rolls the opponents' picks between now and ``manager``'s next turn ``rollouts``
    times; the candidate *survives* a rollout if no opponent drafts it. Returns the
    survival fraction. Deterministic given ``(state, seed)``: rollout ``i`` uses an
    RNG seeded deterministically from ``seed`` and ``i``.

    Fast paths: an already-drafted candidate returns ``0.0`` and an empty gap
    (``manager`` picks again immediately, or the draft is over) returns ``1.0``.
    """
    if rollouts <= 0:
        raise ValueError(f"rollouts must be >= 1, got {rollouts}")
    if candidate.key not in state.available:
        return 0.0
    gap = state.picks_until_next(manager)
    if not gap:
        return 1.0

    survived = 0
    for rollout in range(rollouts):
        rng = random.Random(seed * 1_000_003 + rollout)
        if _candidate_survives(state, gap, candidate, opponent_model, rng):
            survived += 1
    return survived / rollouts


def _candidate_survives(
    state: DraftState,
    gap: Sequence[str],
    candidate: DraftAsset,
    opponent_model: OpponentModel | Mapping[str, OpponentModel],
    rng: random.Random,
) -> bool:
    sim = state.copy()
    for manager in gap:
        model = _resolve_model(opponent_model, manager)
        asset = model.pick(sim, manager, rng)
        if asset.key == candidate.key:
            return False
        sim.place(manager, asset)
    return True
