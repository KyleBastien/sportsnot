"""Tests for draft_oracle.projection_artifact (US-017).

All fixtures are in-memory synthetic archives -- no network, no committed data
(SPEC section 7). The suite covers artifact assembly, automatic exclusion of teams
that are not in the round's bracket, injury flagging, byte-identical Parquet reruns
on the same snapshot, the run manifest contents, and the ``oracle project`` CLI.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from typer.testing import CliRunner

from draft_oracle.cli.project import app
from draft_oracle.features.skater import FEATURE_SET_VERSION
from draft_oracle.models.series_sim import HOME_ICE_PATTERN
from draft_oracle.models.skater_production import SkaterProductionConfig
from draft_oracle.projection_artifact import (
    LIVE_PROJECTION_VERSION,
    SKATER_COLUMNS,
    TEAM_COLUMNS,
    ProjectArtifactConfig,
    build_projection_artifact,
    build_projection_artifact_from_normalized,
    write_projection_artifact,
)

TEAMS = ["AAA", "BBB", "CCC", "DDD"]
STRENGTH = {"AAA": 3.0, "BBB": 1.0, "CCC": -1.0, "DDD": -3.0}
TEAM_RATE = {"AAA": 0.9, "BBB": 0.6, "CCC": 0.4, "DDD": 0.2}


def _players() -> tuple[pd.DataFrame, dict[int, tuple[str, float, str]]]:
    players: dict[int, tuple[str, float, str]] = {}
    rows: list[dict[str, object]] = []
    pid = 100
    for team in TEAMS:
        for offset, pos in ((0.25, "F"), (-0.1, "D")):
            players[pid] = (team, TEAM_RATE[team] + offset, pos)
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
                "opponent_team_abbrev": opp,
                "home_road": "H" if is_home else "R",
                "goals_for": gf,
                "goals_against": ga,
                "shots_against": 30,
                "points": 2 if won else 0,
                "win": won,
                "shutout_win": won and ga == 0,
            }
        )
    return rows


def _draw_ga(rng: np.random.Generator, rate: float) -> tuple[int, int]:
    return int(rng.poisson(max(rate * 0.5, 0.01))), int(rng.poisson(max(rate * 0.5, 0.01)))


def _synthetic_archive(
    end_years: list[int], *, seed: int = 0, n_reg: int = 36
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Round-robin regular seasons + a first-round AAA-over-DDD best-of-7 each year."""
    rng = np.random.default_rng(seed)
    players_df, players = _players()
    sk_rows: list[dict[str, object]] = []
    tg_rows: list[dict[str, object]] = []
    series_rows: list[dict[str, object]] = []
    gid = 6_000_000

    for end_year in end_years:
        season_id = (end_year - 1) * 10000 + end_year
        day, month = 1, 11
        for _ in range(n_reg // (len(TEAMS) - 1)):
            for i, home in enumerate(TEAMS):
                for away in TEAMS[i + 1 :]:
                    gid += 1
                    date = f"{end_year - 1}-{month:02d}-{day:02d}"
                    day += 1
                    if day > 27:
                        day, month = 1, (12 if month == 11 else 11)
                    home_win = STRENGTH[home] + 0.3 >= STRENGTH[away]
                    hg, ag = (3, 1) if home_win else (1, 3)
                    tg_rows.extend(_team_rows(gid, date, season_id, 2, home, away, hg, ag))
                    for team, opp in ((home, away), (away, home)):
                        for p, (t, rate, pos) in players.items():
                            if t != team:
                                continue
                            g, a = _draw_ga(rng, rate)
                            sk_rows.append(
                                _skater_row(p, pos, gid, date, season_id, 2, team, opp, g, a)
                            )

        top, bottom = "AAA", "DDD"
        results = [
            (top, 3, 0),
            (top, 4, 2),
            (bottom, 3, 1),
            (bottom, 2, 1),
            (top, 3, 2),
            (top, 2, 1),
        ]
        for offset, (winner, wg, lg) in enumerate(results):
            gid += 1
            host = top if HOME_ICE_PATTERN[offset] == "A" else bottom
            visitor = bottom if host == top else top
            hg, ag = (wg, lg) if winner == host else (lg, wg)
            date = f"{end_year}-04-{20 + offset:02d}"
            tg_rows.extend(_team_rows(gid, date, season_id, 3, host, visitor, hg, ag))
            for team, opp in ((top, bottom), (bottom, top)):
                for p, (t, rate, pos) in players.items():
                    if t != team:
                        continue
                    g, a = _draw_ga(rng, rate)
                    sk_rows.append(_skater_row(p, pos, gid, date, season_id, 3, team, opp, g, a))
        series_rows.append(
            {
                "year": end_year,
                "season_id": season_id,
                "series_letter": "A",
                "series_abbrev": "AAADDD",
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


def _config() -> ProjectArtifactConfig:
    return ProjectArtifactConfig(
        seed=20260827,
        n_sims=300,
        production_config=SkaterProductionConfig(
            seed=20260827, n_val_seasons=1, n_test_seasons=1, min_confident_games=5
        ),
    )


def _archive() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    return _synthetic_archive([2018, 2019, 2020, 2021, 2022], seed=1)


# ── Core assembly ──────────────────────────────────────────────────────────


def test_build_projection_artifact_shapes_and_columns() -> None:
    sk, tg, players, series = _archive()
    result = build_projection_artifact(
        sk, players, tg, series, season=2022, playoff_round=1, snapshot_id="snap", config=_config()
    )
    assert list(result.skaters.columns) == list(SKATER_COLUMNS)
    assert list(result.teams.columns) == list(TEAM_COLUMNS)
    # Exactly the two teams in the round's only series appear.
    assert len(result.teams) == 2
    assert set(result.teams["team_abbrev"]) == {"AAA", "DDD"}
    assert result.manifest["counts"]["eligible_series"] == 1


def test_ineligible_teams_and_players_are_excluded() -> None:
    sk, tg, players, series = _archive()
    result = build_projection_artifact(
        sk, players, tg, series, season=2022, playoff_round=1, snapshot_id="snap", config=_config()
    )
    # BBB and CCC are not in the round-1 bracket -> excluded from both tables.
    assert "BBB" not in set(result.teams["team_abbrev"])
    assert "CCC" not in set(result.teams["team_abbrev"])
    assert set(result.skaters["team_abbrev"]).issubset({"AAA", "DDD"})
    assert (result.skaters["expected_points"] >= 0).all()
    assert (result.skaters["p10"] <= result.skaters["p90"]).all()


def test_series_win_probabilities_are_complementary() -> None:
    sk, tg, players, series = _archive()
    result = build_projection_artifact(
        sk, players, tg, series, season=2022, playoff_round=1, snapshot_id="snap", config=_config()
    )
    probs = result.teams.set_index("team_abbrev")["p_series_win"]
    assert probs["AAA"] + probs["DDD"] == pytest.approx(1.0)
    # The stronger top seed is favored.
    assert probs["AAA"] > probs["DDD"]


def test_injury_flag_is_set_from_injuries_table() -> None:
    sk, tg, players, series = _archive()
    injured_pid = 100  # AAA forward
    injuries = pd.DataFrame(
        [
            {
                "player_id": injured_pid,
                "player_name": "AAA-100",
                "position": "F",
                "status": "out",
            }
        ]
    )
    result = build_projection_artifact(
        sk,
        players,
        tg,
        series,
        season=2022,
        playoff_round=1,
        snapshot_id="snap",
        injuries=injuries,
        config=_config(),
    )
    flagged = result.skaters.set_index("player_id")["injured"]
    assert bool(flagged.loc[injured_pid]) is True
    assert result.manifest["counts"]["skaters_injured"] >= 1
    others = result.skaters.loc[result.skaters["player_id"] != injured_pid, "injured"]
    assert not others.any()


def test_missing_round_raises() -> None:
    sk, tg, players, series = _archive()
    with pytest.raises(ValueError, match="no series found"):
        build_projection_artifact(
            sk, players, tg, series, season=2099, playoff_round=1, snapshot_id="x", config=_config()
        )


# ── Manifest ───────────────────────────────────────────────────────────────


def test_manifest_records_versions_seeds_and_snapshot() -> None:
    sk, tg, players, series = _archive()
    result = build_projection_artifact(
        sk,
        players,
        tg,
        series,
        season=2022,
        playoff_round=1,
        snapshot_id="snap-123",
        config=_config(),
        git_sha="deadbeef",
        generated_at="2026-08-28T00:00:00+00:00",
    )
    m = result.manifest
    assert m["artifact_version"] == LIVE_PROJECTION_VERSION
    assert m["snapshot_id"] == "snap-123"
    assert m["git_sha"] == "deadbeef"
    assert m["feature_version"] == FEATURE_SET_VERSION
    assert m["seeds"]["base"] == 20260827
    assert set(m["model_versions"]) == {
        "game_win",
        "shutout",
        "skater_production",
        "series_sim",
        "projection",
    }
    assert m["as_of_cutoff"].startswith("2022-04")


# ── Determinism / byte-identical reruns ────────────────────────────────────


def test_reruns_are_byte_identical_parquet(tmp_path: Path) -> None:
    sk, tg, players, series = _archive()

    def _run(sub: str) -> tuple[bytes, bytes]:
        result = build_projection_artifact(
            sk,
            players,
            tg,
            series,
            season=2022,
            playoff_round=1,
            snapshot_id="snap",
            config=_config(),
            git_sha="sha",
            generated_at="2026-08-28T00:00:00+00:00",
        )
        out = write_projection_artifact(result, tmp_path / sub)
        return (
            (out / "skaters.parquet").read_bytes(),
            (out / "teams.parquet").read_bytes(),
        )

    sk_a, tm_a = _run("run_a")
    sk_b, tm_b = _run("run_b")
    assert sk_a == sk_b
    assert tm_a == tm_b


# ── From-normalized + CLI ──────────────────────────────────────────────────


def _write_normalized(dir_path: Path) -> None:
    sk, tg, players, series = _archive()
    dir_path.mkdir(parents=True, exist_ok=True)
    sk.to_parquet(dir_path / "skater_games.parquet", index=False)
    tg.to_parquet(dir_path / "team_games.parquet", index=False)
    players.to_parquet(dir_path / "players.parquet", index=False)
    series.to_parquet(dir_path / "series.parquet", index=False)


def test_from_normalized_writes_all_files(tmp_path: Path) -> None:
    normalized = tmp_path / "normalized"
    _write_normalized(normalized)
    result, out_dir = build_projection_artifact_from_normalized(
        season=2022,
        playoff_round=1,
        normalized_dir=normalized,
        artifacts_root=tmp_path / "artifacts",
        config=_config(),
    )
    assert out_dir.name == "2022-r1"
    for fname in (
        "skaters.parquet",
        "skaters.csv",
        "teams.parquet",
        "teams.csv",
        "cheatsheet.md",
        "run_manifest.json",
    ):
        assert (out_dir / fname).exists()
    assert result.manifest["snapshot_id"] == "live"
    assert not result.cheatsheet.rows.empty
    assert result.manifest["scarcity"]["managers"] == 4
    assert (
        (out_dir / "cheatsheet.md")
        .read_text(encoding="utf-8")
        .startswith("# Draft Oracle cheat sheet")
    )


def test_cli_project_runs_offline(tmp_path: Path) -> None:
    normalized = tmp_path / "normalized"
    _write_normalized(normalized)
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "project",
            "--season",
            "2022",
            "--round",
            "1",
            "--normalized-dir",
            str(normalized),
            "--artifacts-root",
            str(tmp_path / "artifacts"),
            "--no-refresh",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Projection artifact ->" in result.output
    assert (tmp_path / "artifacts" / "2022-r1" / "skaters.parquet").exists()
