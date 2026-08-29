"""Tests for draft_oracle.backtest.replay (US-025).

All fixtures are in-memory synthetic archives -- no network, no committed data
(SPEC section 7). An eight-team, four-series first round gives a pool large enough
to fill a four-manager draft, so the replay loop, the leakage guard, actual-result
scoring through the rules engine, determinism, and persistence can all be exercised
offline.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from typer.testing import CliRunner

from draft_oracle.backtest.replay import (
    BacktestConfig,
    _draft_events,
    assert_round_inputs_leakfree,
    round_game_ids,
    run_backtest,
    run_backtest_from_normalized,
    skater_actual_points,
    team_actual_goalie_points,
    write_backtest,
)
from draft_oracle.cli.project import app
from draft_oracle.features.leakage import LeakageError
from draft_oracle.models.skater_production import SkaterProductionConfig
from draft_oracle.projection_artifact import ProjectArtifactConfig
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
) -> list[dict[str, object]]:
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
                "team_id": TEAMS.index(team) + 1,
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
