"""Per-slot draft strategy report (US-023).

Round-1 snake order is randomized and revealed only moments before the draft, so a
drafter has no time to plan once their seat is announced. This module precomputes a
full strategy plan for **every** slot ``1..N`` ahead of time: the instant the order
drops, the owner opens the plan for their seat and drafts.

Each slot's plan is produced by playing the whole draft forward against the fitted
opponent model (US-020, or the greedy fallback when no league history exists). At
every one of the owner's turns the multi-step recommendation engine (US-021) is run
to surface the recommended pick plus its top alternatives; the plan then follows the
recommended line so later turns are conditioned on the picks already made. The owner's
first two turns additionally carry *contingency* guidance: the gap of opponent picks
before the owner's next turn is rolled out many times, the most-likely board states
are clustered from those branches, and each branch gets its own best pick.

Determinism (SPEC section 3): every slot's realized draft line and every contingency
rollout is seeded from ``(config.seed, slot, ...)`` so the whole report is a pure
function of ``(pool, managers, ir, opponents, config)``.

Performance (acceptance): a 12-slot league must finish inside the 15-minute batch
budget. The knobs that keep it there are ``rollouts`` / ``max_candidates`` (per-turn
recommendation cost) and the greedy fast path -- when no fitted opponents are supplied
the vectorized greedy kernel (US-021) evaluates candidates in numpy, so a full 12-slot
sweep runs in seconds rather than minutes.
"""

from __future__ import annotations

import json
import random
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict, Unpack, cast

from draft_oracle.optimize._slot_strategy_types import (
    Contingency,
    PickOption,
    SlotPlan,
    SlotStrategyReport,
    TurnPlan,
    slot_pick_numbers,
)
from draft_oracle.optimize.opponents import FittedLeagueOpponents
from draft_oracle.optimize.recommend import (
    RecommendConfig,
    asset_value,
    greedy_vor_pick,
    recommend_pick,
    replacement_levels,
)
from draft_oracle.optimize.simulator import (
    DraftAsset,
    DraftState,
    GreedyOpponentModel,
    OpponentModel,
    roster_capacity,
)

__all__ = [
    "Contingency",
    "PickOption",
    "SlotPlan",
    "SlotStrategyBuildRequest",
    "SlotStrategyConfig",
    "SlotStrategyReport",
    "TurnPlan",
    "build_slot_strategies",
    "slot_pick_numbers",
    "write_slot_strategies",
]


@dataclass(frozen=True)
class SlotStrategyConfig:
    """Knobs for the per-slot report (deterministic given the seed).

    ``rollouts``/``max_candidates`` size each per-turn multi-step recommendation;
    ``top_alternatives`` is how many runners-up to list per turn. ``contingency_turns``
    owner turns (from the front) get contingency guidance built from
    ``contingency_rollouts`` gap rollouts over the top ``contingency_targets`` targets,
    surfacing the ``contingency_branches`` most-likely board states. ``temperature`` /
    ``need_weight`` configure the greedy fallback opponent.
    """

    rollouts: int = 60
    max_candidates: int = 8
    top_alternatives: int = 3
    contingency_turns: int = 2
    contingency_branches: int = 3
    contingency_targets: int = 4
    contingency_rollouts: int = 120
    depth: int | None = None
    seed: int = 20260827
    temperature: float = 0.3
    need_weight: float = 4.0

    def __post_init__(self) -> None:
        checks: tuple[tuple[int, str, int], ...] = (
            (self.rollouts, "rollouts", 1),
            (self.max_candidates, "max_candidates", 1),
            (self.top_alternatives, "top_alternatives", 0),
            (self.contingency_turns, "contingency_turns", 0),
            (self.contingency_branches, "contingency_branches", 1),
            (self.contingency_targets, "contingency_targets", 1),
            (self.contingency_rollouts, "contingency_rollouts", 1),
        )
        for value, name, minimum in checks:
            if value < minimum:
                raise ValueError(f"{name} must be >= {minimum}, got {value}")
        if self.depth is not None and self.depth < 1:
            raise ValueError(f"depth must be >= 1 or None, got {self.depth}")


def _resolve_model(
    opponents: OpponentModel | Mapping[str, OpponentModel], manager: str
) -> OpponentModel:
    if isinstance(opponents, Mapping):
        try:
            return opponents[manager]
        except KeyError as exc:
            raise ValueError(f"no opponent model for manager {manager!r}") from exc
    return opponents


def _owner_roster_value(state: DraftState, owner: str) -> float:
    return sum(asset_value(asset) for asset in state.rosters[owner].all_assets())


def _top_targets(
    state: DraftState, owner: str, replacement: Mapping[str, float], k: int
) -> list[DraftAsset]:
    """The owner's ``k`` most valuable still-legal targets by value over replacement."""
    legal = state.legal_assets(owner)
    legal.sort(key=lambda a: (-(asset_value(a) - replacement[a.position]), a.key))
    return legal[:k]


def _simulate_gap_taken(
    ctx: _SlotCtx,
    base: DraftState,
    target_keys: frozenset[str],
    rng: random.Random,
) -> frozenset[str]:
    """Play opponent picks up to ``owner``'s next turn; return which targets they took.

    Loops on the live ``current_manager`` (never assuming a precomputed order) so the
    placement can never drift out of sync with the manager on the clock.
    """
    sim = base.copy()
    taken: set[str] = set()
    while not sim.is_complete and sim.current_manager != ctx.owner:
        manager = sim.current_manager
        model = _resolve_model(ctx.opponents, manager)
        asset = model.pick(sim, manager, rng)
        if asset.key in target_keys:
            taken.add(asset.key)
        sim.apply_pick(asset)
    return frozenset(taken)


@dataclass(frozen=True)
class _SlotCtx:
    """Fixed inputs for one owner's contingency planning at a slot."""

    owner: str
    opponents: OpponentModel | Mapping[str, OpponentModel]
    replacement: Mapping[str, float]
    config: SlotStrategyConfig


@dataclass(frozen=True)
class _PlanSlotRequest:
    slot: int
    manager_ids: Sequence[str]
    pool: Sequence[DraftAsset]
    allow_ir: bool
    opponents: OpponentModel | Mapping[str, OpponentModel]
    eliminated_team_ids: frozenset[int]
    config: SlotStrategyConfig


def _slot_ctx(
    state: DraftState,
    owner: str,
    opponents: OpponentModel | Mapping[str, OpponentModel],
    config: SlotStrategyConfig,
) -> _SlotCtx:
    return _SlotCtx(owner, opponents, replacement_levels(state, len(state.rosters)), config)


def _gap_outcomes(
    ctx: _SlotCtx, after: DraftState, target_keys: frozenset[str], branch_seed: int
) -> Counter[frozenset[str]]:
    """Cluster ``contingency_rollouts`` gap playouts by which targets opponents took."""
    outcomes: Counter[frozenset[str]] = Counter()
    for j in range(ctx.config.contingency_rollouts):
        rng = random.Random(branch_seed + j)
        outcomes[_simulate_gap_taken(ctx, after, target_keys, rng)] += 1
    return outcomes


def _branch_condition(gone: list[str]) -> str:
    """Human-readable branch label for the surviving/lost targets."""
    if not gone:
        return "if your targets hold"
    return "if " + ", ".join(gone) + " gone"


def _build_branches(
    ctx: _SlotCtx,
    after: DraftState,
    targets: list[DraftAsset],
    outcomes: Counter[frozenset[str]],
) -> list[Contingency]:
    """Surface the most-likely board states, each with the owner's best pick there."""
    total = sum(outcomes.values())
    branches: list[Contingency] = []
    for taken, count in outcomes.most_common(ctx.config.contingency_branches):
        branch = after.copy()
        for key in taken:
            branch.available.pop(key, None)
        if not branch.legal_assets(ctx.owner):
            continue
        best = greedy_vor_pick(branch, ctx.owner, ctx.replacement)
        gone = [t.name for t in targets if t.key in taken]
        team = f" {best.team_abbrev}" if best.team_abbrev else ""
        recommendation = f"take {best.name} ({best.position}{team})"
        branches.append(Contingency(count / total, _branch_condition(gone), recommendation))
    return branches


def _branch_contingencies(
    ctx: _SlotCtx, state: DraftState, recommended: DraftAsset, branch_seed: int
) -> list[Contingency]:
    """Contingency plans for the owner's next turn, from gap-rollout board states.

    The owner tentatively takes ``recommended``; the gap of opponent picks before the
    owner's next turn is rolled out ``contingency_rollouts`` times; the resulting board
    states (which of the owner's top targets survived) are clustered and the most
    likely ones surface, each with the best pick the owner should make in that branch.
    """
    after = state.copy()
    after.apply_pick(recommended)
    roster = after.rosters[ctx.owner]
    if roster.count("F") + roster.count("D") + roster.count("G") >= after.capacity.total:
        return []
    gap = after.picks_until_next(ctx.owner)
    if not gap:
        return []
    targets = _top_targets(after, ctx.owner, ctx.replacement, ctx.config.contingency_targets)
    if not targets:
        return []
    target_keys = frozenset(t.key for t in targets)
    outcomes = _gap_outcomes(ctx, after, target_keys, branch_seed)
    return _build_branches(ctx, after, targets, outcomes)


def _slot_state(
    request: _PlanSlotRequest,
) -> tuple[str, DraftState, RecommendConfig, random.Random, int]:
    owner = request.manager_ids[request.slot - 1]
    state = DraftState.new(
        request.manager_ids,
        request.pool,
        allow_ir=request.allow_ir,
        eliminated_team_ids=request.eliminated_team_ids,
    )
    rec_config = RecommendConfig(
        rollouts=request.config.rollouts,
        depth=request.config.depth,
        max_candidates=request.config.max_candidates,
        top_n=request.config.top_alternatives + 1,
        seed=request.config.seed + request.slot,
        compute_survival=False,
    )
    line_rng = random.Random(request.config.seed * 7919 + request.slot)
    return owner, state, rec_config, line_rng, state.capacity.total


def _owner_done(state: DraftState, owner: str, total: int) -> bool:
    roster = state.rosters[owner]
    return roster.count("F") + roster.count("D") + roster.count("G") >= total


def _owner_contingencies(
    ctx: _SlotCtx,
    state: DraftState,
    recommended: DraftAsset,
    turn_index: int,
    slot: int,
) -> list[Contingency]:
    if turn_index >= ctx.config.contingency_turns:
        return []
    return _branch_contingencies(
        ctx,
        state,
        recommended,
        ctx.config.seed * 104729 + slot * 1009 + turn_index,
    )


def _owner_turn_plan(
    request: _PlanSlotRequest,
    state: DraftState,
    owner: str,
    managers: int,
    rec_config: RecommendConfig,
    turn_index: int,
) -> TurnPlan:
    ctx = _slot_ctx(state, owner, request.opponents, request.config)
    rec = recommend_pick(state, owner, request.opponents, config=rec_config)
    recommended_eval = rec.best
    return TurnPlan(
        turn_index=turn_index,
        round_index=state.pick_index // managers,
        pick_number=state.pick_index + 1,
        recommended=PickOption.from_evaluation(recommended_eval),
        alternatives=[
            PickOption.from_evaluation(ev)
            for ev in rec.top()[1 : request.config.top_alternatives + 1]
        ],
        contingencies=_owner_contingencies(
            ctx,
            state,
            recommended_eval.asset,
            turn_index,
            request.slot,
        ),
    )


def _plan_slot(request: _PlanSlotRequest) -> SlotPlan:
    """Play one full draft from ``slot``'s seat, recording the owner's turn plans."""
    managers = len(request.manager_ids)
    owner, state, rec_config, line_rng, total = _slot_state(request)
    turns: list[TurnPlan] = []
    turn_index = 0
    while not state.is_complete:
        if _owner_done(state, owner, total):
            break
        manager = state.current_manager
        if manager != owner:
            model = _resolve_model(request.opponents, manager)
            state.apply_pick(model.pick(state, manager, line_rng))
            continue
        turn_plan = _owner_turn_plan(request, state, owner, managers, rec_config, turn_index)
        turns.append(turn_plan)
        state.apply_pick(state.available[turn_plan.recommended.key])
        turn_index += 1

    return SlotPlan(
        slot=request.slot,
        pick_numbers=slot_pick_numbers(request.slot, managers, total),
        turns=turns,
        projected_total=_owner_roster_value(state, owner),
    )


def _resolve_opponent_setup(
    opponents: FittedLeagueOpponents | None,
    manager_ids: Sequence[str],
    cfg: SlotStrategyConfig,
) -> tuple[OpponentModel | Mapping[str, OpponentModel], bool, str]:
    """Pick the opponent policy + honest label for the report (fitted vs greedy)."""
    if opponents is None:
        greedy = GreedyOpponentModel(temperature=cfg.temperature, need_weight=cfg.need_weight)
        return greedy, False, "greedy fallback"
    opponent_model: OpponentModel | Mapping[str, OpponentModel] = opponents.as_mapping(
        list(manager_ids)
    )
    # The seat ids (``seat1..seatN``) never match the fitted per-manager keys
    # (ben/judah/kyle/levi) or their affinity tables, so ``as_mapping`` yields the
    # league-average coefficients with the affinity feature zeroed for every seat.
    # Label the report by the model actually simulated, not by "fitted supplied".
    genuinely_fitted = any(
        (mid in opponents.per_manager) or bool(opponents.affinity.get(mid))
        for mid in manager_ids
    )
    opponent_label = (
        "fitted per-manager league model"
        if genuinely_fitted
        else "league-average fitted coefficients (per-seat, affinity zeroed)"
    )
    return opponent_model, genuinely_fitted, opponent_label


class _BuildSlotStrategyKwargs(TypedDict, total=False):
    managers: int
    allow_ir: bool
    opponents: FittedLeagueOpponents | None
    eliminated_team_ids: frozenset[int]
    config: SlotStrategyConfig | None


@dataclass(frozen=True)
class SlotStrategyBuildRequest:
    pool: Sequence[DraftAsset]
    managers: int
    allow_ir: bool
    opponents: FittedLeagueOpponents | None = None
    eliminated_team_ids: frozenset[int] = frozenset()
    config: SlotStrategyConfig | None = None


def build_slot_strategies(
    pool: SlotStrategyBuildRequest | Sequence[DraftAsset] | None = None,
    **legacy: Unpack[_BuildSlotStrategyKwargs],
) -> SlotStrategyReport:
    """Precompute a strategy plan for every slot ``1..managers``.

    When ``opponents`` is a fitted league model the plans are simulated against it
    (per-manager policies); otherwise the greedy fallback is used (which also unlocks
    the vectorized fast path in the recommendation engine). ``allow_ir`` selects the
    roster shape (adds the ``IR_F`` / ``IR_D`` slots), so the report covers both the
    IR and no-IR configurations when ``--ir`` is set.
    """
    resolved = _resolve_build_request(pool, legacy)
    if resolved.managers < 2:
        raise ValueError(f"managers must be >= 2, got {resolved.managers}")
    cfg = resolved.config or SlotStrategyConfig()
    manager_ids = [f"seat{i + 1}" for i in range(resolved.managers)]
    opponent_model, genuinely_fitted, opponent_label = _resolve_opponent_setup(
        resolved.opponents, manager_ids, cfg
    )

    rounds = roster_capacity(resolved.allow_ir).total
    slots = [
        _plan_slot(
            _PlanSlotRequest(
                slot=slot,
                manager_ids=manager_ids,
                pool=resolved.pool,
                allow_ir=resolved.allow_ir,
                opponents=opponent_model,
                eliminated_team_ids=resolved.eliminated_team_ids,
                config=cfg,
            )
        )
        for slot in range(1, resolved.managers + 1)
    ]
    return SlotStrategyReport(
        managers=resolved.managers,
        ir=resolved.allow_ir,
        rounds=rounds,
        slots=slots,
        seed=cfg.seed,
        rollouts=cfg.rollouts,
        fitted_opponents=genuinely_fitted,
        opponent_label=opponent_label,
    )


def _resolve_build_request(
    pool: SlotStrategyBuildRequest | Sequence[DraftAsset] | None,
    legacy: Mapping[str, object],
) -> SlotStrategyBuildRequest:
    if isinstance(pool, SlotStrategyBuildRequest):
        if legacy:
            raise TypeError("SlotStrategyBuildRequest calls do not accept extra keyword args")
        return pool
    if pool is None:
        raise TypeError("build_slot_strategies requires pool")
    _require_slot_request_field(legacy, "managers")
    _require_slot_request_field(legacy, "allow_ir")
    return SlotStrategyBuildRequest(
        pool=pool,
        managers=cast("int", legacy["managers"]),
        allow_ir=cast("bool", legacy["allow_ir"]),
        opponents=cast("FittedLeagueOpponents | None", legacy.get("opponents")),
        eliminated_team_ids=cast(
            "frozenset[int]",
            legacy.get("eliminated_team_ids", frozenset()),
        ),
        config=cast("SlotStrategyConfig | None", legacy.get("config")),
    )


def _require_slot_request_field(legacy: Mapping[str, object], field_name: str) -> None:
    if field_name not in legacy:
        raise TypeError(f"build_slot_strategies legacy calls require {field_name}")


def write_slot_strategies(report: SlotStrategyReport, path: Path) -> Path:
    """Write the Markdown report to ``path`` (parent created if needed)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(report.report_lines()) + "\n", encoding="utf-8")
    return path


def _summary_json(report: SlotStrategyReport) -> str:  # pragma: no cover - convenience
    return json.dumps(report.summary(), indent=2, sort_keys=True)
