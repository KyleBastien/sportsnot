"""Round orchestration and persistence tests for backtest replay."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from typer.testing import CliRunner

from draft_oracle.backtest.replay import (
    BacktestConfig,
    Strategy,
    replay_round,
    round_game_ids,
    run_backtest,
    run_backtest_from_normalized,
    skater_actual_points,
    team_actual_goalie_points,
    write_backtest,
)
from draft_oracle.cli.project import app
from draft_oracle.features.leakage import LeakageError
from draft_oracle.models.skater_production import (
    SkaterProductionConfig,
    playoff_round_starts,
)
from draft_oracle.projection_artifact import ProjectArtifactConfig, build_projection_artifact
from tests._backtest_shared import _config, _config_ir, _tables
from tests.backtest_fixtures import (
    FOUR_ROUND_TARGET,
    _four_round_config,
    _four_round_tables,
)


def test_run_backtest_replays_rounds_2_and_combined_r3_r4() -> None:
    tables = _four_round_tables()
    result = run_backtest(tables, [FOUR_ROUND_TARGET], config=_four_round_config())
    by_round = {r.playoff_round: r for r in result.rounds}
    assert sorted(by_round) == [1, 2, 3]

    r2 = by_round[2]
    assert r2.scored_rounds == [2]
    assert set(r2.eligible_team_abbrevs) == {f'T{i:02d}' for i in range(1, 9)}
    assert r2.leakage_ok is True
    assert r2.slot_results

    combined = by_round[3]
    assert combined.scored_rounds == [3, 4]
    assert set(combined.eligible_team_abbrevs) == {f'T{i:02d}' for i in range(1, 5)}
    assert combined.leakage_ok is True
    assert combined.slot_results

    assert (
        len(by_round[1].eligible_team_abbrevs)
        > len(r2.eligible_team_abbrevs)
        > len(combined.eligible_team_abbrevs)
    )


def test_combined_r3_r4_roster_scoring_uses_both_rounds() -> None:
    tables = _four_round_tables()
    result = run_backtest(tables, [FOUR_ROUND_TARGET], config=_four_round_config())
    combined = next(rnd for rnd in result.rounds if rnd.playoff_round == 3)
    seat_one = next(slot for slot in combined.slot_results if slot.seat == 1)
    season_id = (FOUR_ROUND_TARGET - 1) * 10000 + FOUR_ROUND_TARGET
    skater_actual = skater_actual_points(tables['skater_games'], tables['series'])
    team_actual = team_actual_goalie_points(tables['team_games'], tables['series'])

    def roster_points(playoff_round: int) -> float:
        total = 0.0
        for key in seat_one.roster_keys:
            lookup = skater_actual if key.startswith('P') else team_actual
            total += lookup.get((season_id, playoff_round, int(key[1:])), 0)
        return total

    round_three_points = roster_points(3)
    round_four_points = roster_points(4)
    assert round_three_points == 63.0
    assert round_four_points == 38.0
    assert seat_one.oracle_points == 101.0
    assert seat_one.oracle_points == round_three_points + round_four_points
    assert seat_one.oracle_points > round_three_points


def test_build_projection_artifact_combined_event_folds_r3_and_r4() -> None:
    tables = _four_round_tables()
    config = ProjectArtifactConfig(
        seed=20260827,
        n_sims=60,
        slot_strategies=False,
        production_config=SkaterProductionConfig(
            seed=20260827,
            n_val_seasons=1,
            n_test_seasons=1,
            min_confident_games=5,
        ),
    )
    result = build_projection_artifact(
        tables['skater_games'],
        tables['players'],
        tables['team_games'],
        tables['series'],
        season=FOUR_ROUND_TARGET,
        playoff_round=3,
        snapshot_id='four-round',
        config=config,
    )
    combined = result.manifest['combined_event']
    assert combined is not None
    assert combined['draft_event'] == 'R3_4'
    assert combined['draft_round'] == 3
    assert combined['scored_rounds'] == [3, 4]
    assert {d['team_abbrev'] for d in combined['teams']} == {f'T{i:02d}' for i in range(1, 5)}
    for diagnostic in combined['teams']:
        p_advance = diagnostic['p_advance']
        round_three = diagnostic['e_goalie_points_r3']
        round_four = diagnostic['e_goalie_points_r4']
        combined_points = diagnostic['e_goalie_points_combined']
        assert p_advance > 0.0
        assert round_four > 0.0
        assert combined_points == pytest.approx(round_three + p_advance * round_four, abs=2e-5)
    assert set(result.manifest['eligible_team_abbrevs']) == {f'T{i:02d}' for i in range(1, 5)}


def test_replay_round_two_scores_only_round_two() -> None:
    tables = _four_round_tables()
    config = _four_round_config()
    skater_actual = skater_actual_points(tables['skater_games'], tables['series'])
    team_actual = team_actual_goalie_points(tables['team_games'], tables['series'])
    rnd = replay_round(
        tables,
        season=FOUR_ROUND_TARGET,
        playoff_round=2,
        league_picks=None,
        injuries=None,
        snapshot_id='four-round',
        skater_actual=skater_actual,
        team_actual=team_actual,
        config=config,
        scored_rounds=[2],
    )
    assert rnd.playoff_round == 2
    assert rnd.scored_rounds == [2]
    assert rnd.as_of_cutoff.startswith(f'{FOUR_ROUND_TARGET}-04')
    assert rnd.leakage_ok is True
    assert set(rnd.eligible_team_abbrevs) == {f'T{i:02d}' for i in range(1, 9)}
    assert rnd.slot_results


def test_leakage_guard_spans_the_combined_r3_r4_game_union() -> None:
    tables = _four_round_tables()
    season_id = (FOUR_ROUND_TARGET - 1) * 10000 + FOUR_ROUND_TARGET
    r3_ids = round_game_ids(
        tables['team_games'],
        tables['series'],
        season_id=season_id,
        playoff_round=3,
    )
    r4_ids = round_game_ids(
        tables['team_games'],
        tables['series'],
        season_id=season_id,
        playoff_round=4,
    )
    assert r3_ids and r4_ids
    union = r3_ids | r4_ids

    starts = playoff_round_starts(tables['team_games'], tables['series'])
    r3_start = starts[season_id][3]
    from draft_oracle.backtest.replay import RoundLeakageCheck, assert_round_inputs_leakfree

    assert_round_inputs_leakfree(
        RoundLeakageCheck(tables['team_games'], union, r3_start, label='team')
    )
    assert_round_inputs_leakfree(
        RoundLeakageCheck(tables['skater_games'], union, r3_start, label='skater')
    )

    leaked_cutoff = f'{FOUR_ROUND_TARGET}-06-01'
    with pytest.raises(LeakageError, match='leaked into the as-of'):
        assert_round_inputs_leakfree(
            RoundLeakageCheck(tables['team_games'], union, leaked_cutoff, label='team')
        )
    with pytest.raises(LeakageError, match='leaked into the as-of'):
        assert_round_inputs_leakfree(
            RoundLeakageCheck(tables['skater_games'], union, leaked_cutoff, label='skater')
        )


def test_draft_events_collapse_r3_and_r4_into_one_combined_draft() -> None:
    from draft_oracle.backtest.replay import _draft_events

    assert _draft_events([1, 2, 3, 4]) == [(1, [1]), (2, [2]), (3, [3, 4])]
    assert _draft_events([1]) == [(1, [1])]
    assert _draft_events([1, 2, 3]) == [(1, [1]), (2, [2]), (3, [3])]


def test_run_backtest_replays_round_and_scores() -> None:
    tables = _tables()
    result = run_backtest(tables, [2022], config=_config())
    assert len(result.rounds) == 1
    rnd = result.rounds[0]
    assert rnd.season == 2022
    assert rnd.playoff_round == 1
    assert rnd.as_of_cutoff.startswith('2022-04')
    assert rnd.opponents_kind == 'greedy'
    assert rnd.leakage_ok is True
    assert len(rnd.slot_results) == 4
    assert {s.seat for s in rnd.slot_results} == {1, 2, 3, 4}
    for slot in rnd.slot_results:
        assert slot.oracle_points >= 0
        assert len(slot.opponent_points) == 3
        assert len(slot.roster_keys) == 9


def test_backtest_is_deterministic() -> None:
    tables = _tables()
    a = run_backtest(tables, [2022], config=_config())
    b = run_backtest(tables, [2022], config=_config())
    points_a = [s.oracle_points for s in a.rounds[0].slot_results]
    points_b = [s.oracle_points for s in b.rounds[0].slot_results]
    assert points_a == points_b


def test_baseline_strategies_run_in_every_slot() -> None:
    tables = _tables()
    strategies = cast(
        tuple[Strategy, ...],
        ('oracle', 'greedy_vor', 'one_step', 'random_legal'),
    )
    result = run_backtest(tables, [2022], config=_config(strategies=strategies))
    rnd = result.rounds[0]
    assert {s.strategy for s in rnd.slot_results} == set(strategies)
    assert len(rnd.slot_results) == 16


def test_infeasible_round_is_skipped_not_crashed() -> None:
    tables = _tables()
    config = BacktestConfig(
        seed=20260827,
        managers=12,
        rollouts=8,
        strategies=('oracle',),
        project_config=_config().project_config,
    )
    result = run_backtest(tables, [2022], config=config)
    rnd = result.rounds[0]
    assert rnd.slot_results == []
    assert rnd.leakage_ok is True
    assert any('round skipped' in warning for warning in rnd.warnings)


def test_from_normalized_never_injects_live_injuries(tmp_path: Path) -> None:
    normalized = tmp_path / 'normalized'
    normalized.mkdir(parents=True, exist_ok=True)
    tables = _tables()
    for name, frame in tables.items():
        frame.to_parquet(normalized / f'{name}.parquet', index=False)
    (normalized / 'injuries.parquet').write_bytes(b'not a parquet file')

    result, out_dir = run_backtest_from_normalized(
        seasons=[2022],
        normalized_dir=normalized,
        backtest_root=tmp_path / 'backtests',
        config=_config_ir(),
    )
    assert (out_dir / 'manifest.json').exists()
    assert result.rounds and result.rounds[0].leakage_ok


def test_write_backtest_persists_manifest_and_rounds(tmp_path: Path) -> None:
    tables = _tables()
    result = run_backtest(tables, [2022], config=_config())
    out_dir = write_backtest(result, tmp_path / 'backtests')
    manifest = out_dir / 'manifest.json'
    round_file = out_dir / 'rounds' / '2022-r1.json'
    assert manifest.exists()
    assert round_file.exists()
    import json

    loaded = json.loads(manifest.read_text(encoding='utf-8'))
    assert loaded['leakage_ok'] is True
    assert loaded['seasons'] == [2022]
    assert out_dir.name == result.run_id


def test_from_normalized_and_cli(tmp_path: Path) -> None:
    normalized = tmp_path / 'normalized'
    normalized.mkdir(parents=True, exist_ok=True)
    tables = _tables()
    for name, frame in tables.items():
        frame.to_parquet(normalized / f'{name}.parquet', index=False)

    result, out_dir = run_backtest_from_normalized(
        seasons=[2022],
        normalized_dir=normalized,
        backtest_root=tmp_path / 'backtests',
        config=_config(),
    )
    assert (out_dir / 'manifest.json').exists()
    assert len(result.rounds) == 1

    runner = CliRunner()
    invoked = runner.invoke(
        app,
        [
            'backtest',
            '--seasons',
            '2022',
            '--normalized-dir',
            str(normalized),
            '--backtest-root',
            str(tmp_path / 'cli-backtests'),
            '--rollouts',
            '8',
        ],
    )
    assert invoked.exit_code == 0, invoked.output
    assert 'Backtest run' in invoked.output
    assert 'leakage_ok (all rounds): True' in invoked.output
