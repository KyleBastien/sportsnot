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

import numpy as np
import pandas as pd
import pytest
from typer.testing import CliRunner

from draft_oracle.backtest.replay import (
    BacktestConfig,
    _draft_events,
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

TEAMS = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG", "HHH"]
# Round-1 bracket: four series pairing all eight teams; the first-named wins each.
SERIES_PAIRS = [("AAA", "HHH"), ("BBB", "GGG"), ("CCC", "FFF"), ("DDD", "EEE")]
STRENGTH = {t: 3.5 - i for i, t in enumerate(TEAMS)}
FORWARDS_PER_TEAM = 5
DEFENSE_PER_TEAM = 4
# Fixed best-of-7 result: winner takes it in six (games 1,2,5,6), one of them a shutout.
SERIES_RESULT = [
    ("top", 3, 0),
    ("top", 4, 2),
    ("bottom", 3, 1),
    ("bottom", 2, 1),
    ("top", 3, 2),
    ("top", 2, 1),
]
HOME_PATTERN = ["top", "top", "bottom", "bottom", "top", "top"]


def _players() -> tuple[pd.DataFrame, dict[int, tuple[str, str, float]]]:
    players: dict[int, tuple[str, str, float]] = {}
    rows: list[dict[str, object]] = []
    pid = 100
    for team in TEAMS:
        for i in range(FORWARDS_PER_TEAM + DEFENSE_PER_TEAM):
            pos = "F" if i < FORWARDS_PER_TEAM else "D"
            rate = 0.6 + 0.05 * (STRENGTH[team]) - 0.03 * i
            players[pid] = (team, pos, max(rate, 0.15))
            rows.append(
                {
                    "player_id": pid,
                    "player_name": f"{team}-{pid}",
                    "last_name": f"L{pid}",
                    "birth_date": "1996-01-01",
                    "position_code": "C" if pos == "F" else "D",
                    "position": pos,
                    "shoots_catches": "L",
                    "current_team_abbrev": team,
                }
            )
            pid += 1
    return pd.DataFrame(rows), players


def _skater_row(
    player_id: int,
    pos: str,
    game_id: int,
    game_date: str,
    season_id: int,
    game_type_id: int,
    team: str,
    opp: str,
    goals: int,
    assists: int,
) -> dict[str, object]:
    return {
        "season_id": season_id,
        "game_type_id": game_type_id,
        "game_id": game_id,
        "game_date": game_date,
        "player_id": player_id,
        "player_name": f"{team}-{player_id}",
        "position_code": "C" if pos == "F" else "D",
        "position": pos,
        "shoots_catches": "L",
        "team_abbrev": team,
        "opponent_team_abbrev": opp,
        "home_road": "H",
        "goals": goals,
        "assists": assists,
        "points": goals + assists,
        "shots": goals * 3 + 2,
        "toi_seconds": 1000,
        "pp_goals": 0,
        "pp_points": 0,
        "sh_goals": 0,
        "sh_points": 0,
        "ev_goals": goals,
        "ev_points": goals + assists,
        "plus_minus": 0,
        "penalty_minutes": 0,
        "game_winning_goals": 0,
        "ot_goals": 0,
        "shooting_pct": 0.1,
        "faceoff_win_pct": 0.5,
    }


def _team_rows(
    game_id: int,
    game_date: str,
    season_id: int,
    game_type_id: int,
    home: str,
    away: str,
    home_goals: int,
    away_goals: int,
    team_ids: dict[str, int] | None = None,
) -> list[dict[str, object]]:
    def _team_id(team: str) -> int:
        return team_ids[team] if team_ids is not None else TEAMS.index(team) + 1

    rows: list[dict[str, object]] = []
    for team, opp, gf, ga, is_home in (
        (home, away, home_goals, away_goals, True),
        (away, home, away_goals, home_goals, False),
    ):
        won = gf > ga
        rows.append(
            {
                "season_id": season_id,
                "game_type_id": game_type_id,
                "game_id": game_id,
                "game_date": game_date,
                "team_id": _team_id(team),
                "team_abbrev": team,
                "team_full_name": team,
                "opponent_team_abbrev": opp,
                "home_road": "H" if is_home else "R",
                "goals_for": gf,
                "goals_against": ga,
                "wins": 1 if won else 0,
                "losses": 0 if won else 1,
                "ot_losses": 0,
                "regulation_and_ot_wins": 1 if won else 0,
                "wins_in_regulation": 1 if won else 0,
                "wins_in_shootout": 0,
                "points": 2 if won else 0,
                "shots_for": 30,
                "shots_against": 30,
                "faceoff_win_pct": 0.5,
                "power_play_pct": 0.2,
                "power_play_net_pct": 0.2,
                "penalty_kill_pct": 0.8,
                "penalty_kill_net_pct": 0.8,
                "team_shutouts": 1 if (won and ga == 0) else 0,
                "win": won,
                "shutout_win": won and ga == 0,
            }
        )
    return rows


def _draw_ga(rng: np.random.Generator, rate: float) -> tuple[int, int]:
    return int(rng.poisson(max(rate * 0.5, 0.01))), int(rng.poisson(max(rate * 0.5, 0.01)))


def _synthetic_archive(
    end_years: list[int], *, seed: int = 0, reg_cycles: int = 2
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Round-robin regular seasons + a four-series first round for each end year."""
    rng = np.random.default_rng(seed)
    players_df, players = _players()
    sk_rows: list[dict[str, object]] = []
    tg_rows: list[dict[str, object]] = []
    series_rows: list[dict[str, object]] = []
    gid = 6_000_000

    for end_year in end_years:
        season_id = (end_year - 1) * 10000 + end_year
        day, month = 1, 10
        for _ in range(reg_cycles):
            for i, home in enumerate(TEAMS):
                for away in TEAMS[i + 1 :]:
                    gid += 1
                    date = f"{end_year - 1}-{month:02d}-{day:02d}"
                    day += 1
                    if day > 27:
                        day = 1
                        month = 11 if month == 10 else (12 if month == 11 else 10)
                    diff = STRENGTH[home] - STRENGTH[away]
                    home_win = rng.random() < 1.0 / (1.0 + np.exp(-0.5 * diff))
                    if home_win:
                        hg = int(rng.integers(2, 5))
                        ag = int(rng.integers(0, hg))
                    else:
                        ag = int(rng.integers(2, 5))
                        hg = int(rng.integers(0, ag))
                    tg_rows.extend(_team_rows(gid, date, season_id, 2, home, away, hg, ag))
                    for team, opp in ((home, away), (away, home)):
                        for p, (t, pos, rate) in players.items():
                            if t != team:
                                continue
                            g, a = _draw_ga(rng, rate)
                            sk_rows.append(
                                _skater_row(p, pos, gid, date, season_id, 2, team, opp, g, a)
                            )

        for letter_idx, (top, bottom) in enumerate(SERIES_PAIRS):
            for offset, (winner_side, wg, lg) in enumerate(SERIES_RESULT):
                gid += 1
                host = top if HOME_PATTERN[offset] == "top" else bottom
                visitor = bottom if host == top else top
                winner = top if winner_side == "top" else bottom
                hg, ag = (wg, lg) if winner == host else (lg, wg)
                date = f"{end_year}-04-{15 + offset:02d}"
                tg_rows.extend(_team_rows(gid, date, season_id, 3, host, visitor, hg, ag))
                for team, opp in ((top, bottom), (bottom, top)):
                    for p, (t, pos, rate) in players.items():
                        if t != team:
                            continue
                        g, a = _draw_ga(rng, rate)
                        sk_rows.append(
                            _skater_row(p, pos, gid, date, season_id, 3, team, opp, g, a)
                        )
            series_rows.append(
                {
                    "year": end_year,
                    "season_id": season_id,
                    "series_letter": chr(ord("A") + letter_idx),
                    "series_abbrev": f"{top}{bottom}",
                    "playoff_round": 1,
                    "top_seed_team_id": TEAMS.index(top) + 1,
                    "top_seed_abbrev": top,
                    "top_seed_wins": 4,
                    "bottom_seed_team_id": TEAMS.index(bottom) + 1,
                    "bottom_seed_abbrev": bottom,
                    "bottom_seed_wins": 2,
                    "winning_team_id": TEAMS.index(top) + 1,
                    "losing_team_id": TEAMS.index(bottom) + 1,
                }
            )

    return (
        pd.DataFrame(sk_rows),
        pd.DataFrame(tg_rows),
        players_df,
        pd.DataFrame(series_rows),
    )


def _tables(seed: int = 1) -> dict[str, pd.DataFrame]:
    sk, tg, players, series = _synthetic_archive([2017, 2018, 2019, 2020, 2021, 2022], seed=seed)
    return {"skater_games": sk, "players": players, "team_games": tg, "series": series}


# ── Four-round fixture (M-8): a full 16-team bracket through the Cup Final ────
#
# Eight teams only reach a conference final (round 3); a genuine round-4 event and
# the combined R3_4 draft need a sixteen-team first round. The lower-indexed seed
# wins every series (SERIES_RESULT: 4-2 in six), so the survivors are deterministic:
# R1 -> T01..T08, R2 -> T01..T04, R3 (conference finals) -> T01,T02, R4 -> T01.
TEAMS16 = [f"T{i:02d}" for i in range(1, 17)]
TEAM16_ID = {t: i + 1 for i, t in enumerate(TEAMS16)}
STRENGTH16 = {t: 8.0 - 0.4 * i for i, t in enumerate(TEAMS16)}
FORWARDS16 = 6
DEFENSE16 = 4
FOUR_ROUND_YEARS = [2019, 2020, 2021, 2022]
FOUR_ROUND_TARGET = 2022

# Bracket pairings per round; first-named (lower seed index) wins each series.
ROUND_PAIRS: dict[int, list[tuple[str, str]]] = {
    1: [(TEAMS16[i], TEAMS16[15 - i]) for i in range(8)],
    2: [(TEAMS16[i], TEAMS16[7 - i]) for i in range(4)],
    3: [(TEAMS16[0], TEAMS16[3]), (TEAMS16[1], TEAMS16[2])],
    4: [(TEAMS16[0], TEAMS16[1])],
}
# Six strictly increasing game dates per round (round N is played after round N-1).
ROUND_DATES: dict[int, list[str]] = {
    1: [f"-04-{15 + o:02d}" for o in range(6)],
    2: [f"-04-{24 + o:02d}" for o in range(6)],
    3: [f"-05-{5 + o:02d}" for o in range(6)],
    4: [f"-05-{15 + o:02d}" for o in range(6)],
}


def _players16() -> tuple[pd.DataFrame, dict[int, tuple[str, str, float]]]:
    players: dict[int, tuple[str, str, float]] = {}
    rows: list[dict[str, object]] = []
    pid = 1000
    for team in TEAMS16:
        for i in range(FORWARDS16 + DEFENSE16):
            pos = "F" if i < FORWARDS16 else "D"
            rate = 0.6 + 0.05 * STRENGTH16[team] - 0.03 * i
            players[pid] = (team, pos, max(rate, 0.15))
            rows.append(
                {
                    "player_id": pid,
                    "player_name": f"{team}-{pid}",
                    "last_name": f"L{pid}",
                    "birth_date": "1996-01-01",
                    "position_code": "C" if pos == "F" else "D",
                    "position": pos,
                    "shoots_catches": "L",
                    "current_team_abbrev": team,
                }
            )
            pid += 1
    return pd.DataFrame(rows), players


def _four_round_archive(
    *, seed: int = 3, reg_cycles: int = 1
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Round-robin regular seasons plus a bracket that reaches the Cup Final.

    Only :data:`FOUR_ROUND_TARGET` plays all four rounds; the earlier seasons play a
    single round (enough history to train the sub-models) so the fixture stays small.
    """
    rng = np.random.default_rng(seed)
    players_df, players = _players16()
    sk_rows: list[dict[str, object]] = []
    tg_rows: list[dict[str, object]] = []
    series_rows: list[dict[str, object]] = []
    gid = 7_000_000

    for end_year in FOUR_ROUND_YEARS:
        season_id = (end_year - 1) * 10000 + end_year
        day, month = 1, 10
        for _ in range(reg_cycles):
            for i, home in enumerate(TEAMS16):
                for away in TEAMS16[i + 1 :]:
                    gid += 1
                    date = f"{end_year - 1}-{month:02d}-{day:02d}"
                    day += 1
                    if day > 27:
                        day = 1
                        month = 11 if month == 10 else (12 if month == 11 else 10)
                    diff = STRENGTH16[home] - STRENGTH16[away]
                    home_win = rng.random() < 1.0 / (1.0 + np.exp(-0.5 * diff))
                    if home_win:
                        hg = int(rng.integers(2, 5))
                        ag = int(rng.integers(0, hg))
                    else:
                        ag = int(rng.integers(2, 5))
                        hg = int(rng.integers(0, ag))
                    tg_rows.extend(
                        _team_rows(gid, date, season_id, 2, home, away, hg, ag, team_ids=TEAM16_ID)
                    )
                    for team, opp in ((home, away), (away, home)):
                        for p, (t, pos, rate) in players.items():
                            if t != team:
                                continue
                            g, a = _draw_ga(rng, rate)
                            sk_rows.append(
                                _skater_row(p, pos, gid, date, season_id, 2, team, opp, g, a)
                            )

        rounds = [1, 2, 3, 4] if end_year == FOUR_ROUND_TARGET else [1]
        for rnd in rounds:
            pairs = ROUND_PAIRS[rnd]
            dates = ROUND_DATES[rnd]
            for letter_idx, (top, bottom) in enumerate(pairs):
                for offset, (winner_side, wg, lg) in enumerate(SERIES_RESULT):
                    gid += 1
                    host = top if HOME_PATTERN[offset] == "top" else bottom
                    visitor = bottom if host == top else top
                    winner = top if winner_side == "top" else bottom
                    hg, ag = (wg, lg) if winner == host else (lg, wg)
                    date = f"{end_year}{dates[offset]}"
                    tg_rows.extend(
                        _team_rows(
                            gid, date, season_id, 3, host, visitor, hg, ag, team_ids=TEAM16_ID
                        )
                    )
                    for team, opp in ((top, bottom), (bottom, top)):
                        for p, (t, pos, rate) in players.items():
                            if t != team:
                                continue
                            g, a = _draw_ga(rng, rate)
                            sk_rows.append(
                                _skater_row(p, pos, gid, date, season_id, 3, team, opp, g, a)
                            )
                series_rows.append(
                    {
                        "year": end_year,
                        "season_id": season_id,
                        "series_letter": chr(ord("A") + letter_idx),
                        "series_abbrev": f"{top}{bottom}",
                        "playoff_round": rnd,
                        "top_seed_team_id": TEAM16_ID[top],
                        "top_seed_abbrev": top,
                        "top_seed_wins": 4,
                        "bottom_seed_team_id": TEAM16_ID[bottom],
                        "bottom_seed_abbrev": bottom,
                        "bottom_seed_wins": 2,
                        "winning_team_id": TEAM16_ID[top],
                        "losing_team_id": TEAM16_ID[bottom],
                    }
                )

    return (
        pd.DataFrame(sk_rows),
        pd.DataFrame(tg_rows),
        players_df,
        pd.DataFrame(series_rows),
    )


def _four_round_tables() -> dict[str, pd.DataFrame]:
    sk, tg, players, series = _four_round_archive()
    return {"skater_games": sk, "players": players, "team_games": tg, "series": series}


def _four_round_config() -> BacktestConfig:
    # Smaller sims/rollouts than _config: this fixture replays three events across a
    # sixteen-team archive, and the assertions are structural, not statistical.
    project = ProjectArtifactConfig(
        seed=20260827,
        n_sims=60,
        slot_strategies=False,
        production_config=SkaterProductionConfig(
            seed=20260827, n_val_seasons=1, n_test_seasons=1, min_confident_games=5
        ),
    )
    return BacktestConfig(
        seed=20260827,
        managers=4,
        n_drafts=1,
        rollouts=4,
        max_candidates=5,
        strategies=("oracle",),
        project_config=project,
    )


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
    assert_round_inputs_leakfree(tables["team_games"], union, r3_start, label="team")
    assert_round_inputs_leakfree(tables["skater_games"], union, r3_start, label="skater")

    # A cutoff after the final has begun pulls both rounds of the union into the slice.
    leaked_cutoff = f"{FOUR_ROUND_TARGET}-06-01"
    with pytest.raises(LeakageError, match="leaked into the as-of"):
        assert_round_inputs_leakfree(
            tables["team_games"], union, leaked_cutoff, label="team"
        )
    with pytest.raises(LeakageError, match="leaked into the as-of"):
        assert_round_inputs_leakfree(
            tables["skater_games"], union, leaked_cutoff, label="skater"
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
    total = _score_league_roster(
        picks, skater_actual, team_actual, season_id=100, scored_rounds=[1]
    )
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
    total = _score_league_roster(
        picks, skater_actual, team_actual, season_id=100, scored_rounds=[1]
    )
    # No activation: starter (7) counts, bench IR (4) scores zero, goalie (6): 13.
    assert total == 13.0


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
    assert_round_inputs_leakfree(tables["team_games"], ids, "2022-04-15", label="team")


def test_leakage_guard_raises_when_round_games_leak() -> None:
    tables = _tables()
    season_id = 2021 * 10000 + 2022
    ids = round_game_ids(
        tables["team_games"], tables["series"], season_id=season_id, playoff_round=1
    )
    # A cutoff after the round has begun pulls round-1 games into the as-of slice.
    with pytest.raises(LeakageError, match="leaked into the as-of"):
        assert_round_inputs_leakfree(tables["team_games"], ids, "2022-05-01", label="team")


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
    assert_round_inputs_leakfree(skater_games, round_ids, cutoff, label="skater")

    # The independent authoritative-date source catches the leak.
    with pytest.raises(LeakageError, match="desynced past cutoff"):
        assert_round_inputs_leakfree(
            skater_games,
            round_ids,
            cutoff,
            label="skater",
            authoritative_dates=team_games,
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
