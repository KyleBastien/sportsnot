"""Tests for draft_oracle.rules — the SportsNot ruleset mirror (US-002).

Golden vectors are copied verbatim from
``packages/utils/src/lib/utils.test.ts`` so that any drift between the
TypeScript app and this Python mirror is caught. Property-based tests
(hypothesis) cover scoring and snake-order invariants.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from draft_oracle.rules import (
    RosterSlot,
    goalie_game_points,
    goalie_series_points,
    player_points,
    redraft_order,
    roster_composition,
    snake_order,
    validate_roster,
)

# ── Golden vectors: player_points (calculatePlayerPoints) ────────────────


def test_player_points_goals_and_assists() -> None:
    assert player_points(3, 5) == 8  # 3*1 + 5*1


def test_player_points_zero_stats() -> None:
    assert player_points(0, 0) == 0


def test_player_points_high_line() -> None:
    assert player_points(12, 20) == 32


# ── Golden vectors: goalie_series_points (calculateGoaliePoints) ──────────


def test_goalie_series_win_points() -> None:
    assert goalie_series_points(4, 0) == 8  # 4*2


def test_goalie_series_shutout_replaces_win() -> None:
    # 4 wins, 1 shutout -> 3*2 + 1*4 = 10
    assert goalie_series_points(4, 1) == 10


def test_goalie_series_all_shutouts() -> None:
    assert goalie_series_points(4, 4) == 16


def test_goalie_series_no_wins() -> None:
    assert goalie_series_points(0, 0) == 0


# ── Golden vectors: goalie_game_points (calculateGoalieGamePoints) ────────


def test_goalie_game_regular_win() -> None:
    assert goalie_game_points(3, 1) == 2


def test_goalie_game_shutout() -> None:
    assert goalie_game_points(2, 0) == 4


def test_goalie_game_loss() -> None:
    assert goalie_game_points(1, 3) == 0


def test_goalie_game_tie() -> None:
    assert goalie_game_points(2, 2) == 0


def test_goalie_game_shutout_not_additive() -> None:
    # 3-0 win is a shutout worth 4, never 6
    assert goalie_game_points(3, 0) == 4


def test_goalie_game_one_goal_margin() -> None:
    assert goalie_game_points(2, 1) == 2


def test_goalie_game_multiple_games_tally() -> None:
    # 3 regular wins * 2 + 1 shutout * 4 = 10
    games = [(3, 1), (4, 2), (1, 3), (2, 0), (5, 3), (0, 2), (1, 4)]
    total = sum(goalie_game_points(team, opp) for team, opp in games)
    assert total == 10


def test_goalie_game_oilers_scenario() -> None:
    # 4 wins with 0 shutouts = 8 goalie points
    games = [(3, 2), (4, 1), (2, 1), (5, 3)]
    total = sum(goalie_game_points(team, opp) for team, opp in games)
    assert total == 8


# ── Golden vectors: snake_order (generateSnakeDraftOrder) ─────────────────


def test_snake_order_two_players_two_rounds() -> None:
    assert snake_order(["A", "B"], 2) == ["A", "B", "B", "A"]


def test_snake_order_three_players_three_rounds() -> None:
    assert snake_order(["A", "B", "C"], 3) == [
        "A",
        "B",
        "C",
        "C",
        "B",
        "A",
        "A",
        "B",
        "C",
    ]


def test_snake_order_zero_rounds() -> None:
    assert snake_order(["A", "B"], 0) == []


def test_snake_order_single_player() -> None:
    assert snake_order(["A"], 3) == ["A", "A", "A"]


def test_snake_order_does_not_mutate_input() -> None:
    participants = ["A", "B", "C"]
    snake_order(participants, 4)
    assert participants == ["A", "B", "C"]


# ── Golden vectors: redraft_order (generateReDraftOrder) ──────────────────


def test_redraft_order_worst_to_best() -> None:
    standings = [("A", 30.0), ("B", 10.0), ("C", 20.0)]
    assert redraft_order(standings, 1) == ["B", "C", "A"]


def test_redraft_order_snake_pattern() -> None:
    standings = [("A", 20.0), ("B", 10.0)]
    assert redraft_order(standings, 2) == ["B", "A", "A", "B"]


def test_redraft_order_four_members_ascending() -> None:
    standings = [
        ("alpha", 20.0),
        ("beta", 30.0),
        ("gamma", 5.0),
        ("delta", 25.0),
    ]
    assert redraft_order(standings, 1) == ["gamma", "alpha", "delta", "beta"]


def test_redraft_order_tied_points_stable_sort() -> None:
    standings = [("a", 10.0), ("b", 10.0), ("c", 10.0)]
    # All tied -> stable sort keeps input order
    assert redraft_order(standings, 1) == ["a", "b", "c"]


def test_redraft_order_single_member() -> None:
    assert redraft_order([("solo", 42.0)], 3) == ["solo", "solo", "solo"]


def test_redraft_order_worst_team_first_pick() -> None:
    standings = [("best", 100.0), ("mid", 50.0), ("worst", 10.0)]
    order = redraft_order(standings, 1)
    assert order[0] == "worst"
    assert order[2] == "best"


# ── roster_composition ────────────────────────────────────────────────────


def test_roster_composition_with_ir() -> None:
    composition = roster_composition(allow_ir_slots=True)
    assert composition == {"F": 5, "D": 3, "G": 1, "IR_F": 1, "IR_D": 1}
    assert sum(composition.values()) == 11


def test_roster_composition_without_ir() -> None:
    composition = roster_composition(allow_ir_slots=False)
    assert composition == {"F": 5, "D": 3, "G": 1}
    assert sum(composition.values()) == 9


# ── validate_roster ───────────────────────────────────────────────────────


def _valid_roster(*, allow_ir_slots: bool) -> list[RosterSlot]:
    slots = [
        RosterSlot("F", player_id=1),
        RosterSlot("F", player_id=2),
        RosterSlot("F", player_id=3),
        RosterSlot("F", player_id=4),
        RosterSlot("F", player_id=5),
        RosterSlot("D", player_id=6),
        RosterSlot("D", player_id=7),
        RosterSlot("D", player_id=8),
        RosterSlot("G", team_id=100),
    ]
    if allow_ir_slots:
        slots.append(RosterSlot("IR_F", player_id=9))
        slots.append(RosterSlot("IR_D", player_id=10))
    return slots


def test_validate_roster_valid_no_ir() -> None:
    result = validate_roster(_valid_roster(allow_ir_slots=False), allow_ir_slots=False)
    assert result.valid
    assert result.reasons == []


def test_validate_roster_valid_with_ir() -> None:
    result = validate_roster(_valid_roster(allow_ir_slots=True), allow_ir_slots=True)
    assert result.valid


def test_validate_roster_ir_slots_present_but_disabled() -> None:
    result = validate_roster(_valid_roster(allow_ir_slots=True), allow_ir_slots=False)
    assert not result.valid
    assert any("IR_F" in reason for reason in result.reasons)


def test_validate_roster_wrong_composition() -> None:
    slots = _valid_roster(allow_ir_slots=False)[:-1]  # drop the goalie
    result = validate_roster(slots, allow_ir_slots=False)
    assert not result.valid
    assert any("Position G" in reason for reason in result.reasons)


def test_validate_roster_duplicate_player() -> None:
    slots = _valid_roster(allow_ir_slots=False)
    slots[1] = RosterSlot("F", player_id=1)  # duplicate of slots[0]
    result = validate_roster(slots, allow_ir_slots=False)
    assert not result.valid
    assert any("drafted 2 times" in reason for reason in result.reasons)


def test_validate_roster_duplicate_team() -> None:
    slots = _valid_roster(allow_ir_slots=True)
    # Give an IR slot the same team as the goalie slot.
    slots[-1] = RosterSlot("IR_D", team_id=100)
    result = validate_roster(slots, allow_ir_slots=True)
    assert not result.valid
    assert any("Team 100 is drafted" in reason for reason in result.reasons)


def test_validate_roster_eliminated_team_goalie() -> None:
    result = validate_roster(
        _valid_roster(allow_ir_slots=False),
        allow_ir_slots=False,
        eliminated_team_ids=frozenset({100}),
    )
    assert not result.valid
    assert any("Team 100 is eliminated" in reason for reason in result.reasons)


def test_validate_roster_eliminated_team_player() -> None:
    result = validate_roster(
        _valid_roster(allow_ir_slots=False),
        allow_ir_slots=False,
        eliminated_team_ids=frozenset({55}),
        player_team_ids={1: 55},
    )
    assert not result.valid
    assert any("on eliminated team 55" in reason for reason in result.reasons)


# ── Property-based invariants (hypothesis) ────────────────────────────────

_counts = st.integers(min_value=0, max_value=1000)


@given(goals=_counts, assists=_counts)
def test_player_points_is_sum(goals: int, assists: int) -> None:
    assert player_points(goals, assists) == goals + assists


@given(wins=_counts, extra=_counts)
def test_goalie_series_equals_two_times_wins_plus_shutouts(wins: int, extra: int) -> None:
    # Shutouts cannot exceed wins.
    shutouts = extra % (wins + 1)
    assert goalie_series_points(wins, shutouts) == 2 * wins + 2 * shutouts


@given(team=_counts, opp=_counts)
def test_goalie_game_points_domain(team: int, opp: int) -> None:
    points = goalie_game_points(team, opp)
    assert points in {0, 2, 4}
    if team <= opp:
        assert points == 0
    elif opp == 0:
        assert points == 4  # shutout, never 6
    else:
        assert points == 2


@given(
    participants=st.lists(st.text(min_size=1, max_size=3), min_size=1, max_size=8, unique=True),
    total_picks=st.integers(min_value=0, max_value=11),
)
def test_snake_order_invariants(participants: list[str], total_picks: int) -> None:
    order = snake_order(participants, total_picks)
    assert len(order) == len(participants) * total_picks
    for round_index in range(total_picks):
        start = round_index * len(participants)
        chunk = order[start : start + len(participants)]
        expected = participants if round_index % 2 == 0 else participants[::-1]
        assert chunk == expected
    # Every participant picks exactly once per round.
    for member in participants:
        assert order.count(member) == total_picks


@given(
    standings=st.lists(
        st.tuples(
            st.text(min_size=1, max_size=3),
            st.integers(min_value=0, max_value=500),
        ),
        min_size=1,
        max_size=8,
        unique_by=lambda item: item[0],
    ),
    total_picks=st.integers(min_value=1, max_value=6),
)
def test_redraft_first_round_is_points_ascending(
    standings: list[tuple[str, int]], total_picks: int
) -> None:
    order = redraft_order(standings, total_picks)
    first_round = order[: len(standings)]
    points_by_member = dict(standings)
    ordered_points = [points_by_member[member] for member in first_round]
    assert ordered_points == sorted(ordered_points)
