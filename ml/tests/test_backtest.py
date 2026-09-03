"""Compatibility collector for split backtest tests."""

from __future__ import annotations

from tests._backtest_market_leakage import (
    test_leakage_guard_catches_skater_team_date_desync,
    test_leakage_guard_passes_on_correct_cutoff,
    test_leakage_guard_raises_when_round_games_leak,
    test_market_series_prob_none_when_uncovered,
    test_market_series_prob_reads_game_one_when_top_seed_is_away,
    test_market_series_prob_uses_only_game_one_line,
)
from tests._backtest_rounds import (
    test_backtest_is_deterministic,
    test_baseline_strategies_run_in_every_slot,
    test_build_projection_artifact_combined_event_folds_r3_and_r4,
    test_combined_r3_r4_roster_scoring_uses_both_rounds,
    test_draft_events_collapse_r3_and_r4_into_one_combined_draft,
    test_from_normalized_and_cli,
    test_from_normalized_never_injects_live_injuries,
    test_infeasible_round_is_skipped_not_crashed,
    test_leakage_guard_spans_the_combined_r3_r4_game_union,
    test_replay_round_two_scores_only_round_two,
    test_run_backtest_replays_round_and_scores,
    test_run_backtest_replays_rounds_2_and_combined_r3_r4,
    test_write_backtest_persists_manifest_and_rounds,
)
from tests._backtest_scoring import (
    test_combined_league_comparison_scores_rounds_three_and_four,
    test_real_2024_levi_r3_4_roster_scores_corrected_64_points,
    test_real_2026_league_comparisons_never_pool_leagues,
    test_score_league_roster_honors_retroactive_ir_swap,
    test_score_league_roster_no_swap_counts_starter_benches_ir,
    test_skater_actual_points_use_player_points,
    test_team_actual_goalie_points_match_rules,
)
from tests._backtest_shared import SERIES_PAIRS, TEAMS, _config, _tables

__all__ = [
    'SERIES_PAIRS',
    'TEAMS',
    '_config',
    '_tables',
    'test_backtest_is_deterministic',
    'test_baseline_strategies_run_in_every_slot',
    'test_build_projection_artifact_combined_event_folds_r3_and_r4',
    'test_combined_league_comparison_scores_rounds_three_and_four',
    'test_combined_r3_r4_roster_scoring_uses_both_rounds',
    'test_draft_events_collapse_r3_and_r4_into_one_combined_draft',
    'test_from_normalized_and_cli',
    'test_from_normalized_never_injects_live_injuries',
    'test_infeasible_round_is_skipped_not_crashed',
    'test_leakage_guard_catches_skater_team_date_desync',
    'test_leakage_guard_passes_on_correct_cutoff',
    'test_leakage_guard_raises_when_round_games_leak',
    'test_leakage_guard_spans_the_combined_r3_r4_game_union',
    'test_market_series_prob_none_when_uncovered',
    'test_market_series_prob_reads_game_one_when_top_seed_is_away',
    'test_market_series_prob_uses_only_game_one_line',
    'test_real_2024_levi_r3_4_roster_scores_corrected_64_points',
    'test_real_2026_league_comparisons_never_pool_leagues',
    'test_replay_round_two_scores_only_round_two',
    'test_run_backtest_replays_round_and_scores',
    'test_run_backtest_replays_rounds_2_and_combined_r3_r4',
    'test_score_league_roster_honors_retroactive_ir_swap',
    'test_score_league_roster_no_swap_counts_starter_benches_ir',
    'test_skater_actual_points_use_player_points',
    'test_team_actual_goalie_points_match_rules',
    'test_write_backtest_persists_manifest_and_rounds',
]
