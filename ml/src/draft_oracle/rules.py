"""SportsNot league ruleset — scoring, draft order, and roster validation.

This module is the Python mirror of the app's rules engine
(``packages/utils/src/lib/utils.ts`` and ``packages/types/src/lib/types.ts``).
Every projection, simulation, and backtest scores through these functions so the
Python pipeline is byte-for-byte identical to the real app (SPEC §1).

Golden vectors are copied from ``packages/utils/src/lib/utils.test.ts`` in the
test suite; keep both in sync when either language changes.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

# ── Scoring constants (mirror SCORING in packages/types) ─────────────────

GOAL_POINTS = 1
ASSIST_POINTS = 1
WIN_POINTS = 2
SHUTOUT_POINTS = 4  # replaces the win's points, never additive

# ── Roster positions (mirror Position in packages/types) ─────────────────

Position = Literal["F", "D", "G", "IR_F", "IR_D"]

FORWARD: Position = "F"
DEFENSE: Position = "D"
GOALIE: Position = "G"
IR_FORWARD: Position = "IR_F"
IR_DEFENSE: Position = "IR_D"

_ALL_POSITIONS: tuple[Position, ...] = (
    FORWARD,
    DEFENSE,
    GOALIE,
    IR_FORWARD,
    IR_DEFENSE,
)


# ── Scoring ──────────────────────────────────────────────────────────────


def player_points(goals: int, assists: int) -> int:
    """Skater points: goals and assists are weighted equally (1 pt each)."""
    return goals * GOAL_POINTS + assists * ASSIST_POINTS


def goalie_series_points(wins: int, shutouts: int) -> int:
    """Goalie (team) points over a series.

    ``(wins - shutouts) * 2 + shutouts * 4``: each shutout upgrades a win from
    2 to 4 points rather than stacking on top of it.
    """
    regular_wins = wins - shutouts
    return regular_wins * WIN_POINTS + shutouts * SHUTOUT_POINTS


def goalie_game_points(team_score: int, opp_score: int) -> int:
    """Goalie (team) points for a single game.

    0 unless the team won. A shutout win (opponent scored 0) is worth 4 and
    *replaces* the win's 2 points — a 1-0 win is 4, never 6.
    """
    if team_score <= opp_score:
        return 0
    return SHUTOUT_POINTS if opp_score == 0 else WIN_POINTS


# ── Draft order ──────────────────────────────────────────────────────────


def snake_order(participants: Sequence[str], total_picks: int) -> list[str]:
    """Snake draft order: order reverses on every odd round (0-indexed).

    Mirrors ``generateSnakeDraftOrder``. Round 0 uses ``participants`` as given;
    round 1 reverses it; round 2 restores it; and so on.
    """
    order: list[str] = []
    base = list(participants)
    for round_index in range(total_picks):
        is_even_round = round_index % 2 == 0
        round_order = base if is_even_round else base[::-1]
        order.extend(round_order)
    return order


def redraft_order(standings: Sequence[tuple[str, float]], total_picks: int) -> list[str]:
    """Re-draft order from standings, worst (fewest points) picks first.

    ``standings`` is a sequence of ``(member_id, points)`` pairs. They are
    sorted by points ascending with a stable sort (ties keep input order), then
    fed into :func:`snake_order`. Mirrors ``generateReDraftOrder``.
    """
    sorted_standings = sorted(standings, key=lambda item: item[1])
    participant_ids = [member_id for member_id, _points in sorted_standings]
    return snake_order(participant_ids, total_picks)


# ── Roster composition & validation ──────────────────────────────────────


def roster_composition(allow_ir_slots: bool) -> dict[Position, int]:
    """Required slot counts per position.

    Always 5 F / 3 D / 1 G. When ``allow_ir_slots`` is true, adds 1 IR_F and
    1 IR_D (11 picks total); otherwise those IR slots are absent (9 picks).
    Mirrors ``getRosterComposition``.
    """
    composition: dict[Position, int] = {
        FORWARD: 5,
        DEFENSE: 3,
        GOALIE: 1,
    }
    if allow_ir_slots:
        composition[IR_FORWARD] = 1
        composition[IR_DEFENSE] = 1
    return composition


@dataclass(frozen=True)
class RosterSlot:
    """A single drafted roster slot.

    Skater/goalie-team slots carry a ``player_id``; the goalie slot (a whole
    NHL team's goaltending) and IR-team slots carry a ``team_id``.
    """

    position: Position
    player_id: int | None = None
    team_id: int | None = None


@dataclass(frozen=True)
class RosterValidation:
    """Result of :func:`validate_roster`. ``reasons`` is empty when valid."""

    valid: bool
    reasons: list[str] = field(default_factory=list)


def validate_roster(
    slots: Sequence[RosterSlot],
    *,
    allow_ir_slots: bool,
    eliminated_team_ids: frozenset[int] = frozenset(),
    player_team_ids: Mapping[int, int] | None = None,
) -> RosterValidation:
    """Validate a roster against league rules, returning reasons on failure.

    Rejects rosters that (a) do not match the required composition, (b) draft
    the same player or team twice, or (c) include a player or team from an
    eliminated NHL team. ``player_team_ids`` maps ``player_id -> team_id`` so
    skaters on eliminated teams can be caught.
    """
    reasons: list[str] = []
    player_team_ids = player_team_ids or {}

    reasons.extend(_composition_reasons(slots, allow_ir_slots))
    reasons.extend(_duplicate_reasons(slots))
    reasons.extend(_eliminated_reasons(slots, eliminated_team_ids, player_team_ids))

    return RosterValidation(valid=not reasons, reasons=reasons)


def _composition_reasons(slots: Sequence[RosterSlot], allow_ir_slots: bool) -> list[str]:
    reasons: list[str] = []
    required = roster_composition(allow_ir_slots)
    counts = Counter(slot.position for slot in slots)

    for position in _ALL_POSITIONS:
        expected = required.get(position, 0)
        actual = counts.get(position, 0)
        if actual != expected:
            reasons.append(f"Position {position} has {actual} slot(s), expected {expected}")
    return reasons


def _duplicate_reasons(slots: Sequence[RosterSlot]) -> list[str]:
    reasons: list[str] = []

    player_counts = Counter(slot.player_id for slot in slots if slot.player_id is not None)
    for player_id, count in player_counts.items():
        if count > 1:
            reasons.append(f"Player {player_id} is drafted {count} times")

    team_counts = Counter(slot.team_id for slot in slots if slot.team_id is not None)
    for team_id, count in team_counts.items():
        if count > 1:
            reasons.append(f"Team {team_id} is drafted {count} times")

    return reasons


def _eliminated_reasons(
    slots: Sequence[RosterSlot],
    eliminated_team_ids: frozenset[int],
    player_team_ids: Mapping[int, int],
) -> list[str]:
    reasons: list[str] = []
    for slot in slots:
        if slot.team_id is not None and slot.team_id in eliminated_team_ids:
            reasons.append(f"Team {slot.team_id} is eliminated")
        if slot.player_id is not None:
            team_id = player_team_ids.get(slot.player_id)
            if team_id is not None and team_id in eliminated_team_ids:
                reasons.append(f"Player {slot.player_id} is on eliminated team {team_id}")
    return reasons
