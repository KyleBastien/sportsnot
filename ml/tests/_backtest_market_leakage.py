"""Market benchmark and leakage-guard tests for backtest replay."""

from __future__ import annotations

import pandas as pd
import pytest

from draft_oracle.backtest.replay import (
    RoundLeakageCheck,
    _market_series_prob,
    assert_round_inputs_leakfree,
    round_game_ids,
)
from draft_oracle.features.leakage import LeakageError
from draft_oracle.models.series_sim import simulate_series
from tests._backtest_shared import _series_odds_frame, _tables


def test_market_series_prob_uses_only_game_one_line() -> None:
    top_id, bottom_id, season = 10, 20, 2024
    odds = _series_odds_frame(
        [
            {
                'season_end_year': season,
                'game_date': '2024-04-20',
                'is_playoff': True,
                'home_team_id': top_id,
                'away_team_id': bottom_id,
                'home_implied': 0.55,
                'away_implied': 0.45,
            },
            {
                'season_end_year': season,
                'game_date': '2024-04-22',
                'is_playoff': True,
                'home_team_id': top_id,
                'away_team_id': bottom_id,
                'home_implied': 0.05,
                'away_implied': 0.95,
            },
            {
                'season_end_year': season,
                'game_date': '2024-04-24',
                'is_playoff': True,
                'home_team_id': bottom_id,
                'away_team_id': top_id,
                'home_implied': 0.95,
                'away_implied': 0.05,
            },
        ]
    )
    got = _market_series_prob(odds, top_id, bottom_id, season)
    expected = simulate_series(0.55, 0.55).p_a_win_series
    assert got is not None
    assert got == pytest.approx(expected)
    assert got > 0.5


def test_market_series_prob_reads_game_one_when_top_seed_is_away() -> None:
    top_id, bottom_id, season = 10, 20, 2024
    odds = _series_odds_frame(
        [
            {
                'season_end_year': season,
                'game_date': '2024-05-01',
                'is_playoff': True,
                'home_team_id': bottom_id,
                'away_team_id': top_id,
                'home_implied': 0.40,
                'away_implied': 0.60,
            },
            {
                'season_end_year': season,
                'game_date': '2024-05-03',
                'is_playoff': True,
                'home_team_id': top_id,
                'away_team_id': bottom_id,
                'home_implied': 0.99,
                'away_implied': 0.01,
            },
        ]
    )
    got = _market_series_prob(odds, top_id, bottom_id, season)
    expected = simulate_series(0.60, 0.60).p_a_win_series
    assert got == pytest.approx(expected)


def test_market_series_prob_none_when_uncovered() -> None:
    odds = _series_odds_frame([])
    assert _market_series_prob(odds, 10, 20, 2024) is None
    assert _market_series_prob(None, 10, 20, 2024) is None


def test_leakage_guard_passes_on_correct_cutoff() -> None:
    tables = _tables()
    season_id = 2021 * 10000 + 2022
    ids = round_game_ids(
        tables['team_games'],
        tables['series'],
        season_id=season_id,
        playoff_round=1,
    )
    assert ids
    assert_round_inputs_leakfree(
        RoundLeakageCheck(tables['team_games'], ids, '2022-04-15', label='team')
    )


def test_leakage_guard_raises_when_round_games_leak() -> None:
    tables = _tables()
    season_id = 2021 * 10000 + 2022
    ids = round_game_ids(
        tables['team_games'],
        tables['series'],
        season_id=season_id,
        playoff_round=1,
    )
    with pytest.raises(LeakageError, match='leaked into the as-of'):
        assert_round_inputs_leakfree(
            RoundLeakageCheck(tables['team_games'], ids, '2022-05-01', label='team')
        )


def test_leakage_guard_catches_skater_team_date_desync() -> None:
    cutoff = '2022-05-01'
    team_games = pd.DataFrame([{'game_id': 99, 'game_date': '2022-05-10'}])
    skater_games = pd.DataFrame([{'game_id': 99, 'game_date': '2022-04-20', 'player_id': 1}])
    round_ids: set[int] = set()

    assert_round_inputs_leakfree(
        RoundLeakageCheck(skater_games, round_ids, cutoff, label='skater')
    )

    with pytest.raises(LeakageError, match='desynced past cutoff'):
        assert_round_inputs_leakfree(
            RoundLeakageCheck(
                skater_games,
                round_ids,
                cutoff,
                label='skater',
                authoritative_dates=team_games,
            )
        )
