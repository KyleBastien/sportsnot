"""Public report types for per-slot draft strategy plans."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class _PickEvaluationLike(Protocol):
    @property
    def asset(self) -> Any: ...

    @property
    def expected_points(self) -> float: ...

    @property
    def immediate_value(self) -> float: ...

    @property
    def vor(self) -> float: ...


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
    def from_evaluation(cls, ev: _PickEvaluationLike) -> PickOption:
        """Build from a US-021 pick evaluation."""
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
    """1-based overall pick numbers a snake ``slot`` owns."""
    if not 1 <= slot <= managers:
        raise ValueError(f"slot must be in 1..{managers}, got {slot}")
    if rounds < 0:
        raise ValueError(f"rounds must be >= 0, got {rounds}")
    picks: list[int] = []
    for round_index in range(rounds):
        seat = slot if round_index % 2 == 0 else managers - slot + 1
        picks.append(round_index * managers + seat)
    return picks


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
        """The slot with highest projected final-roster total (tie: lowest slot)."""
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
        for plan in sorted(self.slots, key=lambda slot_plan: slot_plan.slot):
            picks = ", ".join(str(number) for number in plan.pick_numbers)
            lines.append(f"| {plan.slot} | {picks} | {plan.projected_total:.2f} |")
        best = self.best_slot()
        lines.extend(
            [
                "",
                f"Best-projected slot: **{best.slot}** ({best.projected_total:.2f} pts).",
                "",
            ]
        )
        for plan in sorted(self.slots, key=lambda slot_plan: slot_plan.slot):
            lines.extend(self._slot_lines(plan))
        return lines

    def _slot_lines(self, plan: SlotPlan) -> list[str]:
        lines = [
            f"## Slot {plan.slot}",
            "",
            f"- Expected picks: {', '.join(str(number) for number in plan.pick_numbers)}",
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
            for contingency in turn.contingencies:
                lines.append(
                    f"- Contingency (P={contingency.probability:.2f}) {contingency.condition}: "
                    f"{contingency.recommendation}"
                )
            lines.append("")
        return lines

    def summary(self) -> dict[str, Any]:
        """JSON-serialisable summary for run manifest."""
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
                for plan in sorted(self.slots, key=lambda slot_plan: slot_plan.slot)
            ],
        }
