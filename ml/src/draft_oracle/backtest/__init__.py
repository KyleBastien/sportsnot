"""Backtest replay engine and reporting with leakage guard (US-025/026)."""

from draft_oracle.backtest.replay import (
    DEFAULT_BACKTEST_ROOT,
    STRATEGIES,
    BacktestConfig,
    BacktestResult,
    RoundResult,
    SlotResult,
    Strategy,
    assert_round_inputs_leakfree,
    round_game_ids,
    run_backtest,
    run_backtest_from_normalized,
    skater_actual_points,
    team_actual_goalie_points,
    write_backtest,
)

__all__ = [
    "DEFAULT_BACKTEST_ROOT",
    "STRATEGIES",
    "BacktestConfig",
    "BacktestResult",
    "RoundResult",
    "SlotResult",
    "Strategy",
    "assert_round_inputs_leakfree",
    "round_game_ids",
    "run_backtest",
    "run_backtest_from_normalized",
    "skater_actual_points",
    "team_actual_goalie_points",
    "write_backtest",
]
