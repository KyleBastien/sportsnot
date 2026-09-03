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
from typing import Any

from draft_oracle.optimize.opponents import FittedLeagueOpponents
from draft_oracle.optimize.recommend import (
    PickEvaluation,
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


@dataclass(frozen=True)
class PickOption:
    """One asset surfaced in a turn plan, with its rolled-out value + reasoning."""

    key: str
    name: str
    position: str
    team_abbrev: str
    expected_points: float
    projection: float
    vor: float

    @classmethod
    def from_evaluation(cls, ev: PickEvaluation) -> PickOption:
        """Build from a US-021 :class:`PickEvaluation`."""
        return cls(
            key=ev.asset.key,
            name=ev.asset.name,
            position=ev.asset.position,
            team_abbrev=ev.asset.team_abbrev,
            expected_points=ev.expected_points,
            projection=ev.immediate_value,
            vor=ev.vor,
        )

    def label(self) -> str:
        """Compact ASCII ``Name (POS TEAM)`` label."""
        team = f" {self.team_abbrev}" if self.team_abbrev else ""
        return f"{self.name} ({self.position}{team})"


@dataclass(frozen=True)
class Contingency:
    """A conditional plan for one likely board state at the owner's next turn."""

    probability: float
    condition: str
    recommendation: str


@dataclass(frozen=True)
class TurnPlan:
    """The plan for one of the owner's turns: the pick, alternatives, contingencies."""

    turn_index: int
    round_index: int
    pick_number: int
    recommended: PickOption
    alternatives: list[PickOption]
    contingencies: list[Contingency]


@dataclass(frozen=True)
class SlotPlan:
    """The full strategy plan for a single snake slot."""

    slot: int
    pick_numbers: list[int]
    turns: list[TurnPlan]
    projected_total: float


def slot_pick_numbers(slot: int, managers: int, rounds: int) -> list[int]:
    """1-based overall pick numbers a snake ``slot`` (1-based seat) owns.

    Round ``r`` (0-indexed) uses the seat directly on even rounds and the mirror seat
    ``managers - slot + 1`` on odd rounds; the overall pick number adds the completed
    rounds' picks. Deterministic and independent of the pool -- this is exactly the
    "expected pick numbers in the snake" the acceptance asks for.
    """
    if not 1 <= slot <= managers:
        raise ValueError(f"slot must be in 1..{managers}, got {slot}")
    if rounds < 0:
        raise ValueError(f"rounds must be >= 0, got {rounds}")
    picks: list[int] = []
    for round_index in range(rounds):
        seat = slot if round_index % 2 == 0 else managers - slot + 1
        picks.append(round_index * managers + seat)
    return picks


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
    base: DraftState,
    owner: str,
    opponents: OpponentModel | Mapping[str, OpponentModel],
    target_keys: frozenset[str],
    rng: random.Random,
) -> frozenset[str]:
    """Play opponent picks up to ``owner``'s next turn; return which targets they took.

    Loops on the live ``current_manager`` (never assuming a precomputed order) so the
    placement can never drift out of sync with the manager on the clock.
    """
    sim = base.copy()
    taken: set[str] = set()
    while not sim.is_complete and sim.current_manager != owner:
        manager = sim.current_manager
        model = _resolve_model(opponents, manager)
        asset = model.pick(sim, manager, rng)
        if asset.key in target_keys:
            taken.add(asset.key)
        sim.apply_pick(asset)
    return frozenset(taken)


def _branch_contingencies(
    state: DraftState,
    owner: str,
    recommended: DraftAsset,
    opponents: OpponentModel | Mapping[str, OpponentModel],
    replacement: Mapping[str, float],
    config: SlotStrategyConfig,
    branch_seed: int,
) -> list[Contingency]:
    """Contingency plans for the owner's next turn, from gap-rollout board states.

    The owner tentatively takes ``recommended``; the gap of opponent picks before the
    owner's next turn is rolled out ``contingency_rollouts`` times; the resulting board
    states (which of the owner's top targets survived) are clustered and the most
    likely ones surface, each with the best pick the owner should make in that branch.
    """
    after = state.copy()
    after.apply_pick(recommended)
    roster = after.rosters[owner]
    if roster.count("F") + roster.count("D") + roster.count("G") >= after.capacity.total:
        return []
    gap = after.picks_until_next(owner)
    if not gap:
        return []
    targets = _top_targets(after, owner, replacement, config.contingency_targets)
    if not targets:
        return []
    target_keys = frozenset(t.key for t in targets)

    outcomes: Counter[frozenset[str]] = Counter()
    for j in range(config.contingency_rollouts):
        rng = random.Random(branch_seed + j)
        outcomes[_simulate_gap_taken(after, owner, opponents, target_keys, rng)] += 1
    total = sum(outcomes.values())

    branches: list[Contingency] = []
    for taken, count in outcomes.most_common(config.contingency_branches):
        branch = after.copy()
        for key in taken:
            branch.available.pop(key, None)
        if not branch.legal_assets(owner):
            continue
        best = greedy_vor_pick(branch, owner, replacement)
        gone = [t.name for t in targets if t.key in taken]
        condition = "if " + ", ".join(gone) + " gone" if gone else "if your targets hold"
        team = f" {best.team_abbrev}" if best.team_abbrev else ""
        recommendation = f"take {best.name} ({best.position}{team})"
        branches.append(Contingency(count / total, condition, recommendation))
    return branches


def _plan_slot(
    slot: int,
    manager_ids: Sequence[str],
    pool: Sequence[DraftAsset],
    *,
    allow_ir: bool,
    opponents: OpponentModel | Mapping[str, OpponentModel],
    eliminated_team_ids: frozenset[int],
    config: SlotStrategyConfig,
) -> SlotPlan:
    """Play one full draft from ``slot``'s seat, recording the owner's turn plans."""
    managers = len(manager_ids)
    owner = manager_ids[slot - 1]
    state = DraftState.new(
        manager_ids, pool, allow_ir=allow_ir, eliminated_team_ids=eliminated_team_ids
    )
    rec_config = RecommendConfig(
        rollouts=config.rollouts,
        depth=config.depth,
        max_candidates=config.max_candidates,
        top_n=config.top_alternatives + 1,
        seed=config.seed + slot,
        compute_survival=False,
    )
    line_rng = random.Random(config.seed * 7919 + slot)

    turns: list[TurnPlan] = []
    turn_index = 0
    total = state.capacity.total
    while not state.is_complete:
        roster = state.rosters[owner]
        if roster.count("F") + roster.count("D") + roster.count("G") >= total:
            break
        manager = state.current_manager
        if manager != owner:
            model = _resolve_model(opponents, manager)
            state.apply_pick(model.pick(state, manager, line_rng))
            continue

        rec = recommend_pick(state, owner, opponents, config=rec_config, managers=managers)
        recommended_eval = rec.best
        alternatives = [
            PickOption.from_evaluation(ev) for ev in rec.top()[1 : config.top_alternatives + 1]
        ]
        contingencies: list[Contingency] = []
        if turn_index < config.contingency_turns:
            replacement = replacement_levels(state, managers)
            contingencies = _branch_contingencies(
                state,
                owner,
                recommended_eval.asset,
                opponents,
                replacement,
                config,
                branch_seed=config.seed * 104729 + slot * 1009 + turn_index,
            )
        pick_number = state.pick_index + 1
        turns.append(
            TurnPlan(
                turn_index=turn_index,
                round_index=state.pick_index // managers,
                pick_number=pick_number,
                recommended=PickOption.from_evaluation(recommended_eval),
                alternatives=alternatives,
                contingencies=contingencies,
            )
        )
        state.apply_pick(recommended_eval.asset)
        turn_index += 1

    return SlotPlan(
        slot=slot,
        pick_numbers=slot_pick_numbers(slot, managers, total),
        turns=turns,
        projected_total=_owner_roster_value(state, owner),
    )


@dataclass
class SlotStrategyReport:
    """The per-slot strategy report for a whole league."""

    managers: int
    ir: bool
    rounds: int
    slots: list[SlotPlan]
    seed: int
    rollouts: int
    fitted_opponents: bool
    opponent_label: str = "greedy fallback"

    def best_slot(self) -> SlotPlan:
        """The slot with the highest projected final-roster total (tie: lowest slot)."""
        if not self.slots:
            raise ValueError("report has no slots")
        return max(self.slots, key=lambda plan: (plan.projected_total, -plan.slot))

    def report_lines(self) -> list[str]:
        """Human-readable Markdown report (ASCII only, cp1252-safe)."""
        lines = [
            "# Draft Oracle per-slot strategy report",
            "",
            f"- League size: {self.managers} managers"
            f" ({'IR' if self.ir else 'no-IR'}, {self.rounds} rounds)",
            f"- Opponents: {self.opponent_label}",
            f"- Rollouts per turn: {self.rollouts} | seed {self.seed}",
            "",
            "## Projected final-roster points by slot",
            "",
            "| Slot | Pick numbers | Projected total |",
            "| ---: | :----------- | --------------: |",
        ]
        for plan in sorted(self.slots, key=lambda p: p.slot):
            picks = ", ".join(str(n) for n in plan.pick_numbers)
            lines.append(f"| {plan.slot} | {picks} | {plan.projected_total:.2f} |")
        best = self.best_slot()
        lines.extend(
            [
                "",
                f"Best-projected slot: **{best.slot}** ({best.projected_total:.2f} pts).",
                "",
            ]
        )
        for plan in sorted(self.slots, key=lambda p: p.slot):
            lines.extend(self._slot_lines(plan))
        return lines

    def _slot_lines(self, plan: SlotPlan) -> list[str]:
        lines = [
            f"## Slot {plan.slot}",
            "",
            f"- Expected picks: {', '.join(str(n) for n in plan.pick_numbers)}",
            f"- Projected final-roster total: {plan.projected_total:.2f}",
            "",
        ]
        for turn in plan.turns:
            lines.append(
                f"### Turn {turn.turn_index + 1} "
                f"(round {turn.round_index + 1}, pick #{turn.pick_number})"
            )
            lines.append("")
            rec = turn.recommended
            lines.append(
                f"- Recommended: {rec.label()} -- "
                f"E[roster] {rec.expected_points:.2f}, proj {rec.projection:.2f}, "
                f"VOR {rec.vor:+.2f}"
            )
            if turn.alternatives:
                alts = "; ".join(
                    f"{alt.label()} (E[roster] {alt.expected_points:.2f})"
                    for alt in turn.alternatives
                )
                lines.append(f"- Alternatives: {alts}")
            for cont in turn.contingencies:
                lines.append(
                    f"- Contingency (P={cont.probability:.2f}) {cont.condition}: "
                    f"{cont.recommendation}"
                )
            lines.append("")
        return lines

    def summary(self) -> dict[str, Any]:
        """JSON-serialisable summary for the run manifest."""
        return {
            "managers": self.managers,
            "ir": self.ir,
            "rounds": self.rounds,
            "seed": self.seed,
            "rollouts": self.rollouts,
            "fitted_opponents": self.fitted_opponents,
            "opponent_label": self.opponent_label,
            "best_slot": self.best_slot().slot,
            "slots": [
                {
                    "slot": plan.slot,
                    "pick_numbers": plan.pick_numbers,
                    "projected_total": round(plan.projected_total, 6),
                    "first_pick": (plan.turns[0].recommended.name if plan.turns else None),
                }
                for plan in sorted(self.slots, key=lambda p: p.slot)
            ],
        }


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


def build_slot_strategies(
    pool: Sequence[DraftAsset],
    *,
    managers: int,
    allow_ir: bool,
    opponents: FittedLeagueOpponents | None = None,
    eliminated_team_ids: frozenset[int] = frozenset(),
    config: SlotStrategyConfig | None = None,
) -> SlotStrategyReport:
    """Precompute a strategy plan for every slot ``1..managers``.

    When ``opponents`` is a fitted league model the plans are simulated against it
    (per-manager policies); otherwise the greedy fallback is used (which also unlocks
    the vectorized fast path in the recommendation engine). ``allow_ir`` selects the
    roster shape (adds the ``IR_F`` / ``IR_D`` slots), so the report covers both the
    IR and no-IR configurations when ``--ir`` is set.
    """
    if managers < 2:
        raise ValueError(f"managers must be >= 2, got {managers}")
    cfg = config or SlotStrategyConfig()
    manager_ids = [f"seat{i + 1}" for i in range(managers)]
    opponent_model, genuinely_fitted, opponent_label = _resolve_opponent_setup(
        opponents, manager_ids, cfg
    )

    rounds = roster_capacity(allow_ir).total
    slots = [
        _plan_slot(
            slot,
            manager_ids,
            pool,
            allow_ir=allow_ir,
            opponents=opponent_model,
            eliminated_team_ids=eliminated_team_ids,
            config=cfg,
        )
        for slot in range(1, managers + 1)
    ]
    return SlotStrategyReport(
        managers=managers,
        ir=allow_ir,
        rounds=rounds,
        slots=slots,
        seed=cfg.seed,
        rollouts=cfg.rollouts,
        fitted_opponents=genuinely_fitted,
        opponent_label=opponent_label,
    )


def write_slot_strategies(report: SlotStrategyReport, path: Path) -> Path:
    """Write the Markdown report to ``path`` (parent created if needed)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(report.report_lines()) + "\n", encoding="utf-8")
    return path


def _summary_json(report: SlotStrategyReport) -> str:  # pragma: no cover - convenience
    return json.dumps(report.summary(), indent=2, sort_keys=True)
