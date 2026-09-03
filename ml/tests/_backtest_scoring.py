"""Scoring and league-comparison tests for backtest replay."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from draft_oracle.backtest.replay import (
    RoundResult,
    ScoreContext,
    SlotResult,
    _league_comparisons,
    _score_league_roster,
    skater_actual_points,
    team_actual_goalie_points,
)
from draft_oracle.rules import goalie_series_points, player_points
from tests._backtest_shared import _require_real_backtest_tables, _tables
from tests.backtest_fixtures import FOUR_ROUND_TARGET, TEAMS, TEAMS16, _four_round_tables


def test_team_actual_goalie_points_match_rules() -> None:
    tables = _tables()
    season_id = 2021 * 10000 + 2022
    lookup = team_actual_goalie_points(tables['team_games'], tables['series'])
    aaa_id = TEAMS.index('AAA') + 1
    assert lookup[(season_id, 1, aaa_id)] == goalie_series_points(4, 1)
    hhh_id = TEAMS.index('HHH') + 1
    assert lookup[(season_id, 1, hhh_id)] == goalie_series_points(2, 0)


def test_skater_actual_points_use_player_points() -> None:
    tables = _tables()
    season_id = 2021 * 10000 + 2022
    lookup = skater_actual_points(tables['skater_games'], tables['series'])
    po = tables['skater_games']
    po = po[(po['season_id'] == season_id) & (po['game_type_id'] == 3)]
    pid = int(po['player_id'].iloc[0])
    rows = po[po['player_id'] == pid]
    expected = player_points(int(rows['goals'].sum()), int(rows['assists'].sum()))
    assert lookup[(season_id, 1, pid)] == expected


def _ir_swap_lookups() -> tuple[
    dict[tuple[int, int, int], int],
    dict[tuple[int, int, int], int],
]:
    season_id = 100
    skater_actual = {(season_id, 1, 1): 7, (season_id, 1, 2): 4}
    team_actual = {(season_id, 1, 10): 6}
    return skater_actual, team_actual


def _league_row(
    position: str,
    *,
    player_id: int | None = None,
    team_id: int | None = None,
    points_excluded: bool = False,
    ir_activated: bool = False,
) -> dict[str, object]:
    return {
        'position': position,
        'player_id': player_id,
        'team_id': team_id,
        'points_excluded': points_excluded,
        'ir_activated': ir_activated,
    }


def test_score_league_roster_honors_retroactive_ir_swap() -> None:
    skater_actual, team_actual = _ir_swap_lookups()
    picks = pd.DataFrame(
        [
            _league_row('F', player_id=1, points_excluded=True),
            _league_row('IR_F', player_id=2, ir_activated=True),
            _league_row('G', team_id=10),
        ]
    )
    total = _score_league_roster(picks, ScoreContext(skater_actual, team_actual, 100, [1]))
    assert total == 10.0


def test_score_league_roster_no_swap_counts_starter_benches_ir() -> None:
    skater_actual, team_actual = _ir_swap_lookups()
    picks = pd.DataFrame(
        [
            _league_row('F', player_id=1),
            _league_row('IR_F', player_id=2),
            _league_row('G', team_id=10),
        ]
    )
    total = _score_league_roster(picks, ScoreContext(skater_actual, team_actual, 100, [1]))
    assert total == 13.0


def test_combined_league_comparison_scores_rounds_three_and_four() -> None:
    tables = _four_round_tables()
    season_id = (FOUR_ROUND_TARGET - 1) * 10000 + FOUR_ROUND_TARGET
    skater_actual = skater_actual_points(tables['skater_games'], tables['series'])
    team_actual = team_actual_goalie_points(tables['team_games'], tables['series'])
    picks = pd.DataFrame(
        [
            _league_event_row('F', player_id=1000),
            _league_event_row('G', team_id=1),
        ]
    )
    combined_round = RoundResult(
        season=FOUR_ROUND_TARGET,
        season_id=season_id,
        playoff_round=3,
        as_of_cutoff=f'{FOUR_ROUND_TARGET}-05-05',
        opponents_kind='greedy',
        eligible_team_abbrevs=TEAMS16[:4],
        leakage_ok=True,
        scored_rounds=[3, 4],
        slot_results=[
            SlotResult(
                strategy='oracle',
                seat=1,
                oracle_manager='seat1',
                draft_index=0,
                oracle_points=40.0,
                opponent_points={},
                roster_keys=[],
            )
        ],
    )

    comparisons = _league_comparisons([combined_round], picks, skater_actual, team_actual)
    assert len(comparisons) == 1
    actual_points = comparisons[0].managers[0].actual_points
    round_three_only = _score_league_roster(
        picks,
        ScoreContext(skater_actual, team_actual, season_id, [3]),
    )
    assert round_three_only == 16.0
    assert actual_points == 37.0
    assert actual_points > round_three_only


def _league_event_row(
    position: str,
    *,
    player_id: int | None = None,
    team_id: int | None = None,
) -> dict[str, object]:
    row = _league_row(position, player_id=player_id, team_id=team_id)
    row.update(
        {
            'season': FOUR_ROUND_TARGET,
            'league_name': 'Combined Fixture League',
            'draft_event': 'R3_4',
            'manager': 'alice',
        }
    )
    return row


def test_real_2026_league_comparisons_never_pool_leagues() -> None:
    normalized = Path('data/normalized')
    _require_real_backtest_tables(normalized)
    league_picks = pd.read_parquet(normalized / 'league_draft_picks.parquet')
    series = pd.read_parquet(normalized / 'series.parquet')
    skater_actual = skater_actual_points(
        pd.read_parquet(normalized / 'skater_games.parquet'),
        series,
    )
    team_actual = team_actual_goalie_points(
        pd.read_parquet(normalized / 'team_games.parquet'),
        series,
    )
    rnd = RoundResult(
        season=2026,
        season_id=20252026,
        playoff_round=1,
        as_of_cutoff='2026-04-18',
        opponents_kind='fitted',
        eligible_team_abbrevs=[],
        leakage_ok=True,
        scored_rounds=[1],
        slot_results=[
            SlotResult(
                strategy='oracle',
                seat=1,
                oracle_manager='kyle',
                draft_index=0,
                oracle_points=42.0,
                opponent_points={},
                roster_keys=[],
            )
        ],
    )

    comparisons = _league_comparisons([rnd], league_picks, skater_actual, team_actual)
    by_league = {comparison.league_name: comparison for comparison in comparisons}

    assert set(by_league) == {'Press Play-offs', 'The Gemmell Cup'}
    assert all(len(comparison.managers) == 4 for comparison in comparisons)
    kyle_points = {
        league: next(
            manager.actual_points
            for manager in comparison.managers
            if manager.manager == 'kyle'
        )
        for league, comparison in by_league.items()
    }
    assert kyle_points == {'Press Play-offs': 50.0, 'The Gemmell Cup': 37.0}
    assert 72.0 not in kyle_points.values()


def test_real_2024_levi_r3_4_roster_scores_corrected_64_points() -> None:
    normalized = Path('data/normalized')
    _require_real_backtest_tables(normalized)
    league_picks = pd.read_parquet(normalized / 'league_draft_picks.parquet')
    series = pd.read_parquet(normalized / 'series.parquet')
    skater_actual = skater_actual_points(
        pd.read_parquet(normalized / 'skater_games.parquet'),
        series,
    )
    team_actual = team_actual_goalie_points(
        pd.read_parquet(normalized / 'team_games.parquet'),
        series,
    )
    roster = league_picks.loc[
        (league_picks['season'] == 2024)
        & (league_picks['league_name'] == 'The Gemmell Cup')
        & (league_picks['draft_event'] == 'R3_4')
        & (league_picks['manager'] == 'levi')
    ]
    corrected = roster.loc[roster['player_or_team_name'] == 'McDavid'].iloc[0]

    assert int(corrected['player_id']) == 8477934
    assert corrected['matched_name'] == 'Leon Draisaitl'
    assert (
        _score_league_roster(
            roster,
            ScoreContext(skater_actual, team_actual, 20232024, [3, 4]),
        )
        == 64.0
    )
