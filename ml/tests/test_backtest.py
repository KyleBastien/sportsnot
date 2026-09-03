"""Tests for draft_oracle.backtest.replay (US-025).

All fixtures are in-memory synthetic archives -- no network, no committed data
(SPEC section 7). An eight-team, four-series first round gives a pool large enough
to fill a four-manager draft, so the replay loop, the leakage guard, actual-result
scoring through the rules engine, determinism, and persistence can all be exercised
offline.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from draft_oracle.backtest.replay import (
    BacktestConfig,
    RoundLeakageCheck,
    RoundResult,
    ScoreContext,
    SlotResult,
    _draft_events,
    _league_comparisons,
    _market_series_prob,
    _score_league_roster,
    assert_round_inputs_leakfree,
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
from draft_oracle.models.series_sim import simulate_series
from draft_oracle.models.skater_production import (
    SkaterProductionConfig,
    playoff_round_starts,
)
from draft_oracle.projection_artifact import (
    ProjectArtifactConfig,
    build_projection_artifact,
)
from draft_oracle.rules import goalie_series_points, player_points
from tests.backtest_fixtures import (
    FOUR_ROUND_TARGET,
    SERIES_PAIRS,
    TEAMS,
    TEAMS16,
    _four_round_config,
    _four_round_tables,
    _tables,
)

__all__ = ["SERIES_PAIRS", "TEAMS", "_config", "_tables"]

# ── Four-round end-to-end (M-8): rounds 2, 3 and the combined R3_4 event ─────


def test_run_backtest_replays_rounds_2_and_combined_r3_r4() -> None:
    tables = _four_round_tables()
    result = run_backtest(tables, [FOUR_ROUND_TARGET], config=_four_round_config())
    # Three draft events: R1, R2, and the combined R3_4 (rounds 3+4 share one draft).
    by_round = {r.playoff_round: r for r in result.rounds}
    assert sorted(by_round) == [1, 2, 3]

    r2 = by_round[2]
    assert r2.scored_rounds == [2]
    # Round 2's survivors are the eight round-1 winners (T01..T08), four series.
    assert set(r2.eligible_team_abbrevs) == {f"T{i:02d}" for i in range(1, 9)}
    assert r2.leakage_ok is True
    assert r2.slot_results  # the round was actually drafted, not skipped

    combined = by_round[3]
    # The combined event is drafted before round 3 but scored across rounds 3 AND 4.
    assert combined.scored_rounds == [3, 4]
    # Only the conference-final four (T01..T04) survive to be drafted.
    assert set(combined.eligible_team_abbrevs) == {f"T{i:02d}" for i in range(1, 5)}
    assert combined.leakage_ok is True
    assert combined.slot_results

    # Surviving-team narrowing: later rounds have strictly fewer eligible teams.
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
    skater_actual = skater_actual_points(tables["skater_games"], tables["series"])
    team_actual = team_actual_goalie_points(tables["team_games"], tables["series"])

    def roster_points(playoff_round: int) -> float:
        total = 0.0
        for key in seat_one.roster_keys:
            lookup = skater_actual if key.startswith("P") else team_actual
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
    # build_projection_artifact invoked with playoff_round=3 (not 1): the combined
    # R3_4 valuation must populate the manifest and fold the conditional Cup Final in.
    tables = _four_round_tables()
    config = ProjectArtifactConfig(
        seed=20260827,
        n_sims=60,
        slot_strategies=False,
        production_config=SkaterProductionConfig(
            seed=20260827, n_val_seasons=1, n_test_seasons=1, min_confident_games=5
        ),
    )
    result = build_projection_artifact(
        tables["skater_games"],
        tables["players"],
        tables["team_games"],
        tables["series"],
        season=FOUR_ROUND_TARGET,
        playoff_round=3,
        snapshot_id="four-round",
        config=config,
    )
    combined = result.manifest["combined_event"]
    assert combined is not None
    assert combined["draft_event"] == "R3_4"
    assert combined["draft_round"] == 3
    assert combined["scored_rounds"] == [3, 4]
    # Exactly the final four teams (two conference-final series) are diagnosed.
    assert {d["team_abbrev"] for d in combined["teams"]} == {f"T{i:02d}" for i in range(1, 5)}
    for diagnostic in combined["teams"]:
        p_advance = diagnostic["p_advance"]
        round_three = diagnostic["e_goalie_points_r3"]
        round_four = diagnostic["e_goalie_points_r4"]
        combined_points = diagnostic["e_goalie_points_combined"]
        assert p_advance > 0.0
        assert round_four > 0.0
        assert combined_points == pytest.approx(round_three + p_advance * round_four, abs=2e-5)
    assert set(result.manifest["eligible_team_abbrevs"]) == {f"T{i:02d}" for i in range(1, 5)}


def test_replay_round_two_scores_only_round_two() -> None:
    # replay_round invoked with playoff_round=2 (not 1): a single-round R2 event.
    tables = _four_round_tables()
    config = _four_round_config()
    skater_actual = skater_actual_points(tables["skater_games"], tables["series"])
    team_actual = team_actual_goalie_points(tables["team_games"], tables["series"])
    rnd = replay_round(
        tables,
        season=FOUR_ROUND_TARGET,
        playoff_round=2,
        league_picks=None,
        injuries=None,
        snapshot_id="four-round",
        skater_actual=skater_actual,
        team_actual=team_actual,
        config=config,
        scored_rounds=[2],
    )
    assert rnd.playoff_round == 2
    assert rnd.scored_rounds == [2]
    assert rnd.as_of_cutoff.startswith(f"{FOUR_ROUND_TARGET}-04")
    assert rnd.leakage_ok is True
    assert set(rnd.eligible_team_abbrevs) == {f"T{i:02d}" for i in range(1, 9)}
    assert rnd.slot_results


def test_leakage_guard_spans_the_combined_r3_r4_game_union() -> None:
    tables = _four_round_tables()
    season_id = (FOUR_ROUND_TARGET - 1) * 10000 + FOUR_ROUND_TARGET
    r3_ids = round_game_ids(
        tables["team_games"], tables["series"], season_id=season_id, playoff_round=3
    )
    r4_ids = round_game_ids(
        tables["team_games"], tables["series"], season_id=season_id, playoff_round=4
    )
    assert r3_ids and r4_ids
    union = r3_ids | r4_ids

    starts = playoff_round_starts(tables["team_games"], tables["series"])
    r3_start = starts[season_id][3]
    # The combined event drafts before round 3, so neither round-3 nor round-4 games
    # may appear in the as-of slice -- the guard is clean over the two-round union.
    assert_round_inputs_leakfree(
        RoundLeakageCheck(tables["team_games"], union, r3_start, label="team")
    )
    assert_round_inputs_leakfree(
        RoundLeakageCheck(tables["skater_games"], union, r3_start, label="skater")
    )

    # A cutoff after the final has begun pulls both rounds of the union into the slice.
    leaked_cutoff = f"{FOUR_ROUND_TARGET}-06-01"
    with pytest.raises(LeakageError, match="leaked into the as-of"):
        assert_round_inputs_leakfree(
            RoundLeakageCheck(tables["team_games"], union, leaked_cutoff, label="team")
        )
    with pytest.raises(LeakageError, match="leaked into the as-of"):
        assert_round_inputs_leakfree(
            RoundLeakageCheck(tables["skater_games"], union, leaked_cutoff, label="skater")
        )


def _config(strategies: tuple[str, ...] = ("oracle",), n_drafts: int = 1) -> BacktestConfig:
    project = ProjectArtifactConfig(
        seed=20260827,
        n_sims=200,
        slot_strategies=False,
        production_config=SkaterProductionConfig(
            seed=20260827, n_val_seasons=1, n_test_seasons=1, min_confident_games=5
        ),
    )
    return BacktestConfig(
        seed=20260827,
        managers=4,
        n_drafts=n_drafts,
        rollouts=8,
        max_candidates=5,
        strategies=strategies,  # type: ignore[arg-type]
        project_config=project,
    )


# ── Replay loop ─────────────────────────────────────────────────────────────


def test_draft_events_collapse_r3_and_r4_into_one_combined_draft() -> None:
    # Rounds 1 and 2 are their own events; rounds 3 and 4 share the combined R3_4
    # draft (drafted before round 3, scored across both).
    assert _draft_events([1, 2, 3, 4]) == [(1, [1]), (2, [2]), (3, [3, 4])]
    # A single-round season stays a single event.
    assert _draft_events([1]) == [(1, [1])]
    # A season that only reached round 3 still combines the reachable rounds.
    assert _draft_events([1, 2, 3]) == [(1, [1]), (2, [2]), (3, [3])]


def test_run_backtest_replays_round_and_scores() -> None:
    tables = _tables()
    result = run_backtest(tables, [2022], config=_config())
    assert len(result.rounds) == 1
    rnd = result.rounds[0]
    assert rnd.season == 2022
    assert rnd.playoff_round == 1
    assert rnd.as_of_cutoff.startswith("2022-04")
    assert rnd.opponents_kind == "greedy"  # no league picks in the fixture
    assert rnd.leakage_ok is True
    # Four seats x one draft x one strategy.
    assert len(rnd.slot_results) == 4
    assert {s.seat for s in rnd.slot_results} == {1, 2, 3, 4}
    for slot in rnd.slot_results:
        assert slot.oracle_points >= 0
        assert len(slot.opponent_points) == 3
        # A full 4-manager, no-IR roster is 9 assets (5F/3D/1G).
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
    strategies = ("oracle", "greedy_vor", "one_step", "random_legal")
    result = run_backtest(tables, [2022], config=_config(strategies=strategies))
    rnd = result.rounds[0]
    assert {s.strategy for s in rnd.slot_results} == set(strategies)
    # Four strategies x four seats.
    assert len(rnd.slot_results) == 16


def test_infeasible_round_is_skipped_not_crashed() -> None:
    # Twelve managers cannot be seated by an eight-team round-1 pool (only 8 goalie
    # teams for 12 goalie slots) -- the round is skipped honestly with a warning.
    tables = _tables()
    config = BacktestConfig(
        seed=20260827,
        managers=12,
        rollouts=8,
        strategies=("oracle",),
        project_config=_config().project_config,
    )
    result = run_backtest(tables, [2022], config=config)
    rnd = result.rounds[0]
    assert rnd.slot_results == []
    assert rnd.leakage_ok is True
    assert any("round skipped" in w for w in rnd.warnings)


# ── Actual-result scoring (through the rules engine) ────────────────────────


def test_team_actual_goalie_points_match_rules() -> None:
    tables = _tables()
    season_id = 2021 * 10000 + 2022
    lookup = team_actual_goalie_points(tables["team_games"], tables["series"])
    # AAA won its round-1 series in six: four wins, one of them a shutout (3-0).
    aaa_id = TEAMS.index("AAA") + 1
    assert lookup[(season_id, 1, aaa_id)] == goalie_series_points(4, 1)
    # HHH lost, winning only two games, neither a shutout.
    hhh_id = TEAMS.index("HHH") + 1
    assert lookup[(season_id, 1, hhh_id)] == goalie_series_points(2, 0)


def test_skater_actual_points_use_player_points() -> None:
    tables = _tables()
    season_id = 2021 * 10000 + 2022
    lookup = skater_actual_points(tables["skater_games"], tables["series"])
    # Cross-check one skater's total against the raw round-1 playoff game log.
    po = tables["skater_games"]
    po = po[(po["season_id"] == season_id) & (po["game_type_id"] == 3)]
    pid = int(po["player_id"].iloc[0])
    rows = po[po["player_id"] == pid]
    expected = player_points(int(rows["goals"].sum()), int(rows["assists"].sum()))
    assert lookup[(season_id, 1, pid)] == expected


# ── League roster scoring: retroactive IR swap (M-7, SPEC section 1) ─────────


def _ir_swap_lookups() -> tuple[
    dict[tuple[int, int, int], int], dict[tuple[int, int, int], int]
]:
    """The review's executed scenario: excluded starter 7, activated IR_F 4, goalie 6."""
    season_id = 100
    skater_actual = {(season_id, 1, 1): 7, (season_id, 1, 2): 4}
    team_actual = {(season_id, 1, 10): 6}
    return skater_actual, team_actual


def test_score_league_roster_honors_retroactive_ir_swap() -> None:
    skater_actual, team_actual = _ir_swap_lookups()
    picks = pd.DataFrame(
        [
            {"position": "F", "player_id": 1, "team_id": None,
             "points_excluded": True, "ir_activated": False},
            {"position": "IR_F", "player_id": 2, "team_id": None,
             "points_excluded": False, "ir_activated": True},
            {"position": "G", "player_id": None, "team_id": 10,
             "points_excluded": False, "ir_activated": False},
        ]
    )
    total = _score_league_roster(picks, ScoreContext(skater_actual, team_actual, 100, [1]))
    # Excluded starter (7) drops, activated IR_F (4) counts, goalie (6): 10, not 13.
    assert total == 10.0


def test_score_league_roster_no_swap_counts_starter_benches_ir() -> None:
    skater_actual, team_actual = _ir_swap_lookups()
    picks = pd.DataFrame(
        [
            {"position": "F", "player_id": 1, "team_id": None,
             "points_excluded": False, "ir_activated": False},
            {"position": "IR_F", "player_id": 2, "team_id": None,
             "points_excluded": False, "ir_activated": False},
            {"position": "G", "player_id": None, "team_id": 10,
             "points_excluded": False, "ir_activated": False},
        ]
    )
    total = _score_league_roster(picks, ScoreContext(skater_actual, team_actual, 100, [1]))
    # No activation: starter (7) counts, bench IR (4) scores zero, goalie (6): 13.
    assert total == 13.0


def test_combined_league_comparison_scores_rounds_three_and_four() -> None:
    tables = _four_round_tables()
    season_id = (FOUR_ROUND_TARGET - 1) * 10000 + FOUR_ROUND_TARGET
    skater_actual = skater_actual_points(tables["skater_games"], tables["series"])
    team_actual = team_actual_goalie_points(tables["team_games"], tables["series"])
    picks = pd.DataFrame(
        [
            {
                "season": FOUR_ROUND_TARGET,
                "league_name": "Combined Fixture League",
                "draft_event": "R3_4",
                "manager": "alice",
                "position": "F",
                "player_id": 1000,
                "team_id": None,
                "points_excluded": False,
                "ir_activated": False,
            },
            {
                "season": FOUR_ROUND_TARGET,
                "league_name": "Combined Fixture League",
                "draft_event": "R3_4",
                "manager": "alice",
                "position": "G",
                "player_id": None,
                "team_id": 1,
                "points_excluded": False,
                "ir_activated": False,
            },
        ]
    )
    combined_round = RoundResult(
        season=FOUR_ROUND_TARGET,
        season_id=season_id,
        playoff_round=3,
        as_of_cutoff=f"{FOUR_ROUND_TARGET}-05-05",
        opponents_kind="greedy",
        eligible_team_abbrevs=TEAMS16[:4],
        leakage_ok=True,
        scored_rounds=[3, 4],
        slot_results=[
            SlotResult(
                strategy="oracle",
                seat=1,
                oracle_manager="seat1",
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


def _require_real_backtest_tables(normalized: Path) -> None:
    required = (
        "league_draft_picks.parquet",
        "series.parquet",
        "skater_games.parquet",
        "team_games.parquet",
    )
    missing = [name for name in required if not (normalized / name).exists()]
    if missing:
        pytest.skip(f"generated normalized tables not present: {', '.join(missing)}")


def test_real_2026_league_comparisons_never_pool_leagues() -> None:
    """Committed two-league fixture keeps kyle's real R1 rosters independent."""
    normalized = Path("data/normalized")
    _require_real_backtest_tables(normalized)
    league_picks = pd.read_parquet(normalized / "league_draft_picks.parquet")
    series = pd.read_parquet(normalized / "series.parquet")
    skater_actual = skater_actual_points(
        pd.read_parquet(normalized / "skater_games.parquet"), series
    )
    team_actual = team_actual_goalie_points(
        pd.read_parquet(normalized / "team_games.parquet"), series
    )
    rnd = RoundResult(
        season=2026,
        season_id=20252026,
        playoff_round=1,
        as_of_cutoff="2026-04-18",
        opponents_kind="fitted",
        eligible_team_abbrevs=[],
        leakage_ok=True,
        scored_rounds=[1],
        slot_results=[
            SlotResult(
                strategy="oracle",
                seat=1,
                oracle_manager="kyle",
                draft_index=0,
                oracle_points=42.0,
                opponent_points={},
                roster_keys=[],
            )
        ],
    )

    comparisons = _league_comparisons([rnd], league_picks, skater_actual, team_actual)
    by_league = {comparison.league_name: comparison for comparison in comparisons}

    assert set(by_league) == {"Press Play-offs", "The Gemmell Cup"}
    assert all(len(comparison.managers) == 4 for comparison in comparisons)
    kyle_points = {
        league: next(
            manager.actual_points for manager in comparison.managers if manager.manager == "kyle"
        )
        for league, comparison in by_league.items()
    }
    assert kyle_points == {"Press Play-offs": 50.0, "The Gemmell Cup": 37.0}
    assert 72.0 not in kyle_points.values()


def test_real_2024_levi_r3_4_roster_scores_corrected_64_points() -> None:
    """The raw "McDavid" row is Draisaitl; Connor remains on judah's roster."""
    normalized = Path("data/normalized")
    _require_real_backtest_tables(normalized)
    league_picks = pd.read_parquet(normalized / "league_draft_picks.parquet")
    series = pd.read_parquet(normalized / "series.parquet")
    skater_actual = skater_actual_points(
        pd.read_parquet(normalized / "skater_games.parquet"), series
    )
    team_actual = team_actual_goalie_points(
        pd.read_parquet(normalized / "team_games.parquet"), series
    )
    roster = league_picks.loc[
        (league_picks["season"] == 2024)
        & (league_picks["league_name"] == "The Gemmell Cup")
        & (league_picks["draft_event"] == "R3_4")
        & (league_picks["manager"] == "levi")
    ]
    corrected = roster.loc[roster["player_or_team_name"] == "McDavid"].iloc[0]

    assert int(corrected["player_id"]) == 8477934
    assert corrected["matched_name"] == "Leon Draisaitl"
    assert (
        _score_league_roster(
            roster,
            ScoreContext(skater_actual, team_actual, 20232024, [3, 4]),
        )
        == 64.0
    )


# ── Market-series benchmark (US-109, CODE_REVIEW M-5) ───────────────────────


def _series_odds_frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    """Minimal odds frame with the columns ``_market_series_prob`` reads."""
    return pd.DataFrame(
        rows,
        columns=[
            "season_end_year",
            "game_date",
            "is_playoff",
            "home_team_id",
            "away_team_id",
            "home_implied",
            "away_implied",
        ],
    )


def test_market_series_prob_uses_only_game_one_line() -> None:
    top_id, bottom_id, season = 10, 20, 2024
    # Game 1 (top seed at home) prices the top seed at 0.55. Later in-series games swing
    # the closing line hard toward the bottom seed; an as-of-round-start benchmark must
    # ignore them entirely.
    odds = _series_odds_frame(
        [
            {"season_end_year": season, "game_date": "2024-04-20", "is_playoff": True,
             "home_team_id": top_id, "away_team_id": bottom_id,
             "home_implied": 0.55, "away_implied": 0.45},
            {"season_end_year": season, "game_date": "2024-04-22", "is_playoff": True,
             "home_team_id": top_id, "away_team_id": bottom_id,
             "home_implied": 0.05, "away_implied": 0.95},
            {"season_end_year": season, "game_date": "2024-04-24", "is_playoff": True,
             "home_team_id": bottom_id, "away_team_id": top_id,
             "home_implied": 0.95, "away_implied": 0.05},
        ]
    )
    got = _market_series_prob(odds, top_id, bottom_id, season)
    # Only the game-1 line (0.55) feeds the best-of-7 model, applied symmetrically.
    expected = simulate_series(0.55, 0.55).p_a_win_series
    assert got is not None
    assert got == pytest.approx(expected)
    # A 0.55 per-game edge yields a clear (>0.5) series favorite, not the sub-0.5 number
    # the old mid-series averaging would have produced from the late blowout lines.
    assert got > 0.5


def test_market_series_prob_reads_game_one_when_top_seed_is_away() -> None:
    top_id, bottom_id, season = 10, 20, 2024
    # Defensive: if the earliest game has the top seed on the road, read its away line.
    odds = _series_odds_frame(
        [
            {"season_end_year": season, "game_date": "2024-05-01", "is_playoff": True,
             "home_team_id": bottom_id, "away_team_id": top_id,
             "home_implied": 0.40, "away_implied": 0.60},
            {"season_end_year": season, "game_date": "2024-05-03", "is_playoff": True,
             "home_team_id": top_id, "away_team_id": bottom_id,
             "home_implied": 0.99, "away_implied": 0.01},
        ]
    )
    got = _market_series_prob(odds, top_id, bottom_id, season)
    expected = simulate_series(0.60, 0.60).p_a_win_series
    assert got == pytest.approx(expected)


def test_market_series_prob_none_when_uncovered() -> None:
    odds = _series_odds_frame([])
    assert _market_series_prob(odds, 10, 20, 2024) is None
    assert _market_series_prob(None, 10, 20, 2024) is None


# ── Leakage guard ───────────────────────────────────────────────────────────


def test_leakage_guard_passes_on_correct_cutoff() -> None:
    tables = _tables()
    season_id = 2021 * 10000 + 2022
    ids = round_game_ids(
        tables["team_games"], tables["series"], season_id=season_id, playoff_round=1
    )
    assert ids  # the round has games
    # The true cutoff is the round-1 start; no round game precedes it.
    assert_round_inputs_leakfree(
        RoundLeakageCheck(tables["team_games"], ids, "2022-04-15", label="team")
    )


def test_leakage_guard_raises_when_round_games_leak() -> None:
    tables = _tables()
    season_id = 2021 * 10000 + 2022
    ids = round_game_ids(
        tables["team_games"], tables["series"], season_id=season_id, playoff_round=1
    )
    # A cutoff after the round has begun pulls round-1 games into the as-of slice.
    with pytest.raises(LeakageError, match="leaked into the as-of"):
        assert_round_inputs_leakfree(
            RoundLeakageCheck(tables["team_games"], ids, "2022-05-01", label="team")
        )


def test_leakage_guard_catches_skater_team_date_desync() -> None:
    # CODE_REVIEW m-2: a skater row can carry a stale (pre-cutoff) date for a game the
    # authoritative team table dates on/after the cutoff. The self-date filter is blind
    # to this (it already dropped every post-cutoff *self* date -- tautological), so the
    # guard must compare against the authoritative team-games date source.
    cutoff = "2022-05-01"
    team_games = pd.DataFrame([{"game_id": 99, "game_date": "2022-05-10"}])
    skater_games = pd.DataFrame([{"game_id": 99, "game_date": "2022-04-20", "player_id": 1}])
    round_ids: set[int] = set()  # a future round, so the game-id identity check can't catch it

    # Self-date check alone passes -- the desynced row survives the pre-cutoff filter.
    assert_round_inputs_leakfree(
        RoundLeakageCheck(skater_games, round_ids, cutoff, label="skater")
    )

    # The independent authoritative-date source catches the leak.
    with pytest.raises(LeakageError, match="desynced past cutoff"):
        assert_round_inputs_leakfree(
            RoundLeakageCheck(
                skater_games,
                round_ids,
                cutoff,
                label="skater",
                authoritative_dates=team_games,
            )
        )


def _config_ir() -> BacktestConfig:
    base = _config()
    return replace(base, ir=True)


def test_from_normalized_never_injects_live_injuries(tmp_path: Path) -> None:
    # CODE_REVIEW m-4: historical rounds must run with an empty injuries input, never
    # today's live snapshot. The backtest must not even read injuries.parquet -- an
    # unreadable one is proof the loader is gone (the old path would raise here).
    normalized = tmp_path / "normalized"
    normalized.mkdir(parents=True, exist_ok=True)
    tables = _tables()
    for name, frame in tables.items():
        frame.to_parquet(normalized / f"{name}.parquet", index=False)
    (normalized / "injuries.parquet").write_bytes(b"not a parquet file")

    result, out_dir = run_backtest_from_normalized(
        seasons=[2022],
        normalized_dir=normalized,
        backtest_root=tmp_path / "backtests",
        config=_config_ir(),
    )
    assert (out_dir / "manifest.json").exists()
    assert result.rounds and result.rounds[0].leakage_ok


# ── Persistence ─────────────────────────────────────────────────────────────


def test_write_backtest_persists_manifest_and_rounds(tmp_path: Path) -> None:
    tables = _tables()
    result = run_backtest(tables, [2022], config=_config())
    out_dir = write_backtest(result, tmp_path / "backtests")
    manifest = out_dir / "manifest.json"
    round_file = out_dir / "rounds" / "2022-r1.json"
    assert manifest.exists()
    assert round_file.exists()
    import json

    loaded = json.loads(manifest.read_text(encoding="utf-8"))
    assert loaded["leakage_ok"] is True
    assert loaded["seasons"] == [2022]
    assert out_dir.name == result.run_id


def test_from_normalized_and_cli(tmp_path: Path) -> None:
    normalized = tmp_path / "normalized"
    normalized.mkdir(parents=True, exist_ok=True)
    tables = _tables()
    for name, frame in tables.items():
        frame.to_parquet(normalized / f"{name}.parquet", index=False)

    result, out_dir = run_backtest_from_normalized(
        seasons=[2022],
        normalized_dir=normalized,
        backtest_root=tmp_path / "backtests",
        config=_config(),
    )
    assert (out_dir / "manifest.json").exists()
    assert len(result.rounds) == 1

    runner = CliRunner()
    invoked = runner.invoke(
        app,
        [
            "backtest",
            "--seasons",
            "2022",
            "--normalized-dir",
            str(normalized),
            "--backtest-root",
            str(tmp_path / "cli-backtests"),
            "--rollouts",
            "8",
        ],
    )
    assert invoked.exit_code == 0, invoked.output
    assert "Backtest run" in invoked.output
    assert "leakage_ok (all rounds): True" in invoked.output
