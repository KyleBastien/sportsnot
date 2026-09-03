"""Tests for draft_oracle.models.projections (US-016).

All fixtures are in-memory synthetic games/series -- no network, no committed
archive dependency (SPEC section 7). The suite covers the pure Monte-Carlo
primitives (length normalization, expected series length, seeded round sampling,
quantile ordering, availability haircut) and an end-to-end evaluation that composes
the production, per-game win, and shutout sub-models and reports honest held-out
metrics against the two fixed baselines.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from draft_oracle.models import (
    BASELINE_REG_GAMES,
    PROJECTION_VERSION,
    ProjectionConfig,
    SkaterProductionConfig,
    evaluate_skater_projections,
    expected_series_length,
    normalize_length_probs,
    project_skater_round,
    simulate_round_points,
)
from draft_oracle.models.projections import project_skater_combined
from draft_oracle.models.series_sim import HOME_ICE_PATTERN

# ── Pure primitives ────────────────────────────────────────────────────────


def test_normalize_length_probs_renormalizes_to_one() -> None:
    probs = normalize_length_probs({4: 1.0, 5: 1.0, 6: 1.0, 7: 1.0})
    assert set(probs) == {4, 5, 6, 7}
    assert sum(probs.values()) == pytest.approx(1.0)
    assert all(v == pytest.approx(0.25) for v in probs.values())


def test_normalize_length_probs_fills_missing_and_clips_negatives() -> None:
    probs = normalize_length_probs({5: 3.0, 6: 1.0, 7: -5.0})
    assert probs[4] == 0.0
    assert probs[7] == 0.0
    assert sum(probs.values()) == pytest.approx(1.0)
    assert probs[5] == pytest.approx(0.75)


def test_normalize_length_probs_degenerate_falls_back_to_six() -> None:
    probs = normalize_length_probs({4: 0.0, 5: 0.0, 6: 0.0, 7: 0.0})
    assert probs[6] == pytest.approx(1.0)
    assert sum(probs.values()) == pytest.approx(1.0)


def test_expected_series_length_of_point_mass() -> None:
    assert expected_series_length({7: 1.0}) == pytest.approx(7.0)
    assert expected_series_length({4: 1.0, 6: 1.0}) == pytest.approx(5.0)


# ── Monte-Carlo round sampling ─────────────────────────────────────────────


def test_simulate_round_points_zero_availability_is_all_zero() -> None:
    rng = np.random.default_rng(0)
    avail = np.zeros(7, dtype=float)
    samples = simulate_round_points(rng, 1.0, {6: 1.0}, avail, n_sims=200)
    assert np.all(samples == 0.0)


def test_simulate_round_points_mean_matches_rate_times_games() -> None:
    rng = np.random.default_rng(7)
    avail = np.ones(7, dtype=float)
    # Fixed 6-game series, fully available -> E[points] = 0.8 * 6.
    samples = simulate_round_points(rng, 0.8, {6: 1.0}, avail, n_sims=40000)
    assert float(np.mean(samples)) == pytest.approx(0.8 * 6, rel=0.05)


def test_project_skater_round_is_reproducible_under_seed() -> None:
    length_probs = {4: 0.1, 5: 0.3, 6: 0.35, 7: 0.25}
    a = project_skater_round(0.7, length_probs, seed=123, n_sims=500)
    b = project_skater_round(0.7, length_probs, seed=123, n_sims=500)
    assert a == b


def test_project_skater_round_quantiles_are_ordered() -> None:
    proj = project_skater_round(0.6, {5: 0.5, 6: 0.5}, seed=42, n_sims=3000)
    assert proj.p10 <= proj.p50 <= proj.p90
    assert proj.expected_points == pytest.approx(proj.pts_per_game * proj.expected_games, rel=0.1)


# ── Combined R3+R4 round sampling ──────────────────────────────────────────


def test_project_skater_combined_reduces_to_single_round_when_no_advance() -> None:
    length_probs = {4: 0.1, 5: 0.3, 6: 0.35, 7: 0.25}
    single = project_skater_round(0.7, length_probs, seed=99, n_sims=6000)
    combined = project_skater_combined(
        0.7, length_probs, 0.0, {6: 1.0}, seed=99, n_sims=6000
    )
    # p_advance == 0 never plays the second series, so the totals match the single
    # round (same seed drives the first-series draws identically).
    assert combined.expected_points == pytest.approx(single.expected_points, rel=0.05)
    assert combined.expected_games == pytest.approx(single.expected_games, rel=1e-9)


def test_project_skater_combined_adds_conditional_next_round() -> None:
    first = {5: 0.5, 6: 0.5}
    second = {5: 0.5, 6: 0.5}
    p_advance = 0.6
    r3 = project_skater_round(0.8, first, seed=7, n_sims=8000)
    r4 = project_skater_round(0.8, second, seed=7, n_sims=8000)
    combined = project_skater_combined(
        0.8, first, p_advance, second, seed=7, n_sims=8000
    )
    # Expected points and games are additive: R3 + p_advance * R4.
    assert combined.expected_points == pytest.approx(
        r3.expected_points + p_advance * r4.expected_points, rel=0.05
    )
    assert combined.expected_games == pytest.approx(
        r3.expected_games + p_advance * r4.expected_games, rel=1e-9
    )
    # Spanning a possible second series widens the ceiling.
    assert combined.p90 >= r3.p90


def test_project_skater_combined_is_reproducible_under_seed() -> None:
    a = project_skater_combined(0.6, {6: 1.0}, 0.5, {6: 1.0}, seed=5, n_sims=1000)
    b = project_skater_combined(0.6, {6: 1.0}, 0.5, {6: 1.0}, seed=5, n_sims=1000)
    assert a == b


def test_project_skater_round_availability_curve_wins_over_multiplier() -> None:
    length_probs = {6: 1.0}
    # A curve that blanks the first three games halves a 6-game slate roughly.
    curve = [0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0]
    proj = project_skater_round(
        1.0, length_probs, availability_curve=curve, availability=1.0, seed=1, n_sims=8000
    )
    # 6-game series, available only for games 4,5,6 -> 3 expected games.
    assert proj.expected_games == pytest.approx(3.0)
    assert proj.availability_multiplier == pytest.approx(0.5)


def test_project_skater_round_scalar_availability_haircut() -> None:
    proj = project_skater_round(1.0, {6: 1.0}, availability=0.5, seed=2, n_sims=8000)
    assert proj.expected_games == pytest.approx(3.0)
    assert proj.availability_multiplier == pytest.approx(0.5)


@settings(max_examples=25, deadline=None)
@given(
    ppg=st.floats(min_value=0.0, max_value=2.0),
    seed=st.integers(min_value=0, max_value=10_000),
)
def test_quantiles_never_decrease_property(ppg: float, seed: int) -> None:
    proj = project_skater_round(ppg, {4: 0.25, 5: 0.25, 6: 0.25, 7: 0.25}, seed=seed, n_sims=400)
    assert proj.p10 <= proj.p50 <= proj.p90
    assert proj.expected_points >= 0.0


# ── End-to-end evaluation fixture ──────────────────────────────────────────

TEAMS = ["AAA", "BBB", "CCC", "DDD"]
STRENGTH = {"AAA": 3.0, "BBB": 1.0, "CCC": -1.0, "DDD": -3.0}
# Latent per-game scoring talent; skaters inherit it plus a per-position offset.
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
    goals = int(rng.poisson(max(rate * 0.5, 0.01)))
    assists = int(rng.poisson(max(rate * 0.5, 0.01)))
    return goals, assists


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

        # Playoff series: AAA (top seed) beats DDD 4-2 over six games.
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


def _projection_config() -> ProjectionConfig:
    production_config = _production_config()
    return ProjectionConfig(
        seed=20260827,
        n_test_seasons=2,
        n_sims=300,
        production_config=production_config,
    )


def _production_config() -> SkaterProductionConfig:
    return SkaterProductionConfig(
        seed=20260827,
        n_val_seasons=1,
        n_test_seasons=1,
        min_confident_games=5,
    )


def test_evaluate_skater_projections_runs_end_to_end() -> None:
    end_years = [2018, 2019, 2020, 2021, 2022, 2023]
    sk, tg, players, series = _synthetic_archive(end_years, seed=1)
    result = evaluate_skater_projections(sk, players, tg, series, config=_projection_config())

    assert result.test_years == (2022, 2023)
    assert result.n_projected > 0
    assert len(result.per_season) == 2
    assert not np.isnan(result.test_mae_model)
    # Uncertainty band is ordered on the held-out means.
    assert result.mean_p10 <= result.mean_p90


def test_evaluate_skater_projections_report_and_manifest_are_consistent() -> None:
    end_years = [2018, 2019, 2020, 2021, 2022, 2023]
    sk, tg, players, series = _synthetic_archive(end_years, seed=2)
    result = evaluate_skater_projections(sk, players, tg, series, config=_projection_config())

    report = "\n".join(result.report_lines())
    assert PROJECTION_VERSION in report
    assert "p10/p50/p90" in report
    assert f"reg-ppg x {BASELINE_REG_GAMES:g}" in report
    assert "previous round" in report

    manifest = result.manifest()
    assert manifest["model_version"] == PROJECTION_VERSION
    assert manifest["test_years"] == [2022, 2023]
    assert manifest["baseline_reg_games"] == BASELINE_REG_GAMES
    assert set(manifest["test_mae"]) == {
        "model",
        "baseline_reg_ppg_x_games",
        "baseline_prev_round",
    }
    assert manifest["beats_both_baselines"] == result.beats_both_baselines


def test_evaluate_skater_projections_is_reproducible() -> None:
    end_years = [2018, 2019, 2020, 2021, 2022, 2023]
    sk, tg, players, series = _synthetic_archive(end_years, seed=3)
    cfg = _projection_config()
    a = evaluate_skater_projections(sk, players, tg, series, config=cfg)
    b = evaluate_skater_projections(sk, players, tg, series, config=cfg)
    assert a.test_mae_model == pytest.approx(b.test_mae_model)
    assert a.mean_expected_points == pytest.approx(b.mean_expected_points)


def test_evaluate_skater_projections_requires_enough_seasons() -> None:
    sk, tg, players, series = _synthetic_archive([2022, 2023], seed=4)
    with pytest.raises(ValueError, match="not enough seasons"):
        evaluate_skater_projections(sk, players, tg, series, config=_projection_config())
