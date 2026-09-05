"""Tests for draft_oracle.optimize.slot_strategies (US-023).

Covers the snake pick-number math, the config validation, the per-slot planner
(turns, alternatives, contingencies, projected totals), the fitted-opponent path,
IR vs. no-IR coverage, determinism, ASCII-only rendering, and the batch-run time
budget. All fixtures are tiny in-memory pools -- no network, no committed data
(SPEC section 7).
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from draft_oracle.optimize.opponents import Coefficients, FittedLeagueOpponents, OpponentFitConfig
from draft_oracle.optimize.recommend import build_synthetic_pool
from draft_oracle.optimize.simulator import roster_capacity
from draft_oracle.optimize.slot_strategies import (
    Contingency,
    PickOption,
    SlotStrategyConfig,
    build_slot_strategies,
    slot_pick_numbers,
    write_slot_strategies,
)


def _fast_config(**overrides: object) -> SlotStrategyConfig:
    """A cheap-but-valid config so the tests stay quick."""
    params: dict[str, object] = {
        "rollouts": 12,
        "max_candidates": 5,
        "contingency_rollouts": 20,
    }
    params.update(overrides)
    return SlotStrategyConfig(**params)  # type: ignore[arg-type]


def _league_fitted() -> FittedLeagueOpponents:
    """A minimal fitted league model (no per-manager overrides) for the OO path."""
    return FittedLeagueOpponents(
        league=Coefficients(rank=1.0, affinity=0.0),
        per_manager={},
        affinity={},
        manager_pick_counts={},
        total_picks=0,
        config=OpponentFitConfig(),
    )


# ── Snake pick numbers ──────────────────────────────────────────────────────


def test_slot_pick_numbers_first_slot() -> None:
    # Slot 1 in a 4-manager, 9-round snake owns pick 1, then the snake turn 8, etc.
    assert slot_pick_numbers(1, 4, 9) == [1, 8, 9, 16, 17, 24, 25, 32, 33]


def test_slot_pick_numbers_last_slot() -> None:
    assert slot_pick_numbers(4, 4, 9) == [4, 5, 12, 13, 20, 21, 28, 29, 36]


def test_slot_pick_numbers_cover_every_pick_exactly_once() -> None:
    managers, rounds = 6, 5
    seen: list[int] = []
    for slot in range(1, managers + 1):
        seen.extend(slot_pick_numbers(slot, managers, rounds))
    assert sorted(seen) == list(range(1, managers * rounds + 1))


def test_slot_pick_numbers_rejects_out_of_range() -> None:
    with pytest.raises(ValueError):
        slot_pick_numbers(0, 4, 9)
    with pytest.raises(ValueError):
        slot_pick_numbers(5, 4, 9)


# ── Config validation ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "overrides",
    [
        {"rollouts": 0},
        {"max_candidates": 0},
        {"top_alternatives": -1},
        {"contingency_turns": -1},
        {"contingency_branches": 0},
        {"contingency_targets": 0},
        {"contingency_rollouts": 0},
        {"depth": 0},
    ],
)
def test_config_rejects_bad_values(overrides: dict[str, int]) -> None:
    with pytest.raises(ValueError):
        SlotStrategyConfig(**overrides)


# ── PickOption ─────────────────────────────────────────────────────────────


def test_pick_option_label_is_ascii() -> None:
    option = PickOption("P1", "McDavid", "F", "EDM", 12.0, 10.0, 3.5)
    label = option.label()
    assert label == "McDavid (F EDM)"
    assert label.isascii()


# ── Per-slot report (greedy) ─────────────────────────────────────────────────


def test_report_has_one_plan_per_slot_with_expected_picks() -> None:
    managers = 4
    pool = build_synthetic_pool(managers, allow_ir=False)
    report = build_slot_strategies(pool, managers=managers, allow_ir=False, config=_fast_config())
    assert [plan.slot for plan in sorted(report.slots, key=lambda p: p.slot)] == [1, 2, 3, 4]
    rounds = roster_capacity(False).total
    for plan in report.slots:
        assert plan.pick_numbers == slot_pick_numbers(plan.slot, managers, rounds)
        # The owner fills a full roster, so there is one turn per round.
        assert len(plan.turns) == rounds
        assert plan.projected_total > 0.0
        assert not report.fitted_opponents


def test_turns_carry_recommended_and_alternatives() -> None:
    pool = build_synthetic_pool(4, allow_ir=False)
    report = build_slot_strategies(
        pool, managers=4, allow_ir=False, config=_fast_config(top_alternatives=3)
    )
    first_turn = report.slots[0].turns[0]
    assert first_turn.recommended.name
    assert 1 <= len(first_turn.alternatives) <= 3
    # The recommended pick is never duplicated in its own alternative list.
    assert first_turn.recommended.key not in {alt.key for alt in first_turn.alternatives}


def test_contingencies_only_on_the_first_two_turns() -> None:
    pool = build_synthetic_pool(4, allow_ir=False)
    report = build_slot_strategies(
        pool, managers=4, allow_ir=False, config=_fast_config(contingency_turns=2)
    )
    plan = report.slots[0]
    assert plan.turns[0].contingencies
    assert plan.turns[1].contingencies
    for turn in plan.turns[2:]:
        assert turn.contingencies == []
    probs = [c.probability for c in plan.turns[0].contingencies]
    assert all(0.0 <= p <= 1.0 for p in probs)
    assert isinstance(plan.turns[0].contingencies[0], Contingency)


def test_no_contingencies_when_disabled() -> None:
    pool = build_synthetic_pool(4, allow_ir=False)
    report = build_slot_strategies(
        pool, managers=4, allow_ir=False, config=_fast_config(contingency_turns=0)
    )
    for plan in report.slots:
        assert all(turn.contingencies == [] for turn in plan.turns)


def test_report_is_deterministic() -> None:
    pool = build_synthetic_pool(4, allow_ir=False)
    config = _fast_config()
    a = build_slot_strategies(pool, managers=4, allow_ir=False, config=config)
    b = build_slot_strategies(pool, managers=4, allow_ir=False, config=config)
    assert a.report_lines() == b.report_lines()
    assert a.summary() == b.summary()


# ── IR coverage ─────────────────────────────────────────────────────────────


def test_ir_configuration_uses_the_ir_roster_shape() -> None:
    pool = build_synthetic_pool(3, allow_ir=True)
    report = build_slot_strategies(pool, managers=3, allow_ir=True, config=_fast_config())
    assert report.ir is True
    ir_rounds = roster_capacity(True).total
    assert report.rounds == ir_rounds
    for plan in report.slots:
        assert len(plan.turns) == ir_rounds


# ── Fitted-opponent path ─────────────────────────────────────────────────────


def test_fitted_opponent_path_runs_and_flags() -> None:
    pool = build_synthetic_pool(3, allow_ir=False)
    report = build_slot_strategies(
        pool,
        managers=3,
        allow_ir=False,
        opponents=_league_fitted(),
        config=_fast_config(),
    )
    # The league model carries no per-seat coefficients and no affinity, so the
    # seat-keyed simulation runs the league-average coefficients with affinity
    # zeroed -- it must NOT be advertised as a genuinely fitted per-manager model
    # (CODE_REVIEW m-10).
    assert report.fitted_opponents is False
    text = "\n".join(report.report_lines())
    assert "league-average" in text
    assert "fitted league model" not in text
    for plan in report.slots:
        assert plan.projected_total > 0.0


def test_seat_keyed_fitted_model_is_labeled_fitted() -> None:
    # A model whose per-manager keys DO match the seat ids the planner uses is a
    # genuine per-seat fit and is labeled as such.
    fitted = FittedLeagueOpponents(
        league=Coefficients(rank=1.0, affinity=0.0),
        per_manager={"seat1": Coefficients(rank=1.2, affinity=0.5)},
        affinity={"seat1": {8471234: 0.4}},
        manager_pick_counts={"seat1": 9},
        total_picks=9,
        config=OpponentFitConfig(),
    )
    report = build_slot_strategies(
        pool=build_synthetic_pool(3, allow_ir=False),
        managers=3,
        allow_ir=False,
        opponents=fitted,
        config=_fast_config(),
    )
    assert report.fitted_opponents is True
    assert "fitted per-manager league model" in "\n".join(report.report_lines())
    assert report.summary()["opponent_label"] == "fitted per-manager league model"


# ── Rendering + summary ─────────────────────────────────────────────────────


def test_report_lines_are_ascii_and_include_summary_table() -> None:
    pool = build_synthetic_pool(4, allow_ir=False)
    report = build_slot_strategies(pool, managers=4, allow_ir=False, config=_fast_config())
    text = "\n".join(report.report_lines())
    assert text.isascii()
    assert "Projected final-roster points by slot" in text
    assert "| Slot | Pick numbers | Projected total |" in text
    # Every slot appears in the summary table.
    for plan in report.slots:
        assert f"| {plan.slot} |" in text


def test_best_slot_matches_max_projection() -> None:
    pool = build_synthetic_pool(4, allow_ir=False)
    report = build_slot_strategies(pool, managers=4, allow_ir=False, config=_fast_config())
    best = report.best_slot()
    assert best.projected_total == max(p.projected_total for p in report.slots)


def test_summary_has_one_entry_per_slot() -> None:
    pool = build_synthetic_pool(4, allow_ir=False)
    report = build_slot_strategies(pool, managers=4, allow_ir=False, config=_fast_config())
    summary = report.summary()
    assert summary["managers"] == 4
    assert summary["rounds"] == roster_capacity(False).total
    assert len(summary["slots"]) == 4
    assert summary["best_slot"] == report.best_slot().slot
    for entry in summary["slots"]:
        assert entry["first_pick"]
        assert entry["projected_total"] > 0.0


def test_write_slot_strategies_writes_markdown(tmp_path: Path) -> None:
    pool = build_synthetic_pool(4, allow_ir=False)
    report = build_slot_strategies(pool, managers=4, allow_ir=False, config=_fast_config())
    out = write_slot_strategies(report, tmp_path / "slot_strategies.md")
    assert out.exists()
    body = out.read_text(encoding="utf-8")
    assert body.startswith("# Draft Oracle per-slot strategy report")
    assert body.endswith("\n")


# ── Guards ─────────────────────────────────────────────────────────────────


def test_rejects_tiny_league() -> None:
    pool = build_synthetic_pool(2, allow_ir=False)
    with pytest.raises(ValueError):
        build_slot_strategies(pool, managers=1, allow_ir=False, config=_fast_config())


def test_full_greedy_12_slot_run_is_under_budget() -> None:
    # The acceptance bar is 15 minutes for a 12-slot league; the greedy fast path is
    # far under that. Keep a generous ceiling so the assertion is not flaky on CI.
    pool = build_synthetic_pool(12, allow_ir=False)
    started = time.time()
    report = build_slot_strategies(
        pool, managers=12, allow_ir=False, config=SlotStrategyConfig(rollouts=40)
    )
    elapsed = time.time() - started
    assert len(report.slots) == 12
    assert elapsed < 300.0
