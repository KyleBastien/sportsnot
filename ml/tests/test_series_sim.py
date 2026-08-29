"""Tests for draft_oracle.models.series_sim (US-013).

All fixtures are in-memory synthetic games/series -- no network, no committed
archive dependency (SPEC section 7). The pure simulator is checked against
known-probability edge cases (p=0.5 symmetric, p=1.0/0.0 sweeps), the 2-2-1-1-1
home-ice ordering, exact-vs-Monte-Carlo agreement, and goalie-slot valuation
through the rules engine. The evaluation path is exercised end-to-end on a small
multi-season synthetic league.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from draft_oracle.models import (
    HOME_ICE_PATTERN,
    SeriesSimConfig,
    evaluate_series_sim,
    expected_goalie_points,
    game_win_probs,
    series_length_labels,
    simulate_series,
    simulate_series_monte_carlo,
)
from draft_oracle.models.series_sim import reconstruct_series_matchups
from draft_oracle.rules import goalie_series_points

# ── Home-ice pattern + per-game probability schedule ───────────────────────


def test_home_ice_pattern_is_2_2_1_1_1() -> None:
    # Higher seed (A) hosts games 1, 2, 5, 7; lower seed (B) hosts 3, 4, 6.
    assert HOME_ICE_PATTERN == ("A", "A", "B", "B", "A", "B", "A")
    assert len(HOME_ICE_PATTERN) == 7


def test_game_win_probs_follow_venue() -> None:
    probs = game_win_probs(0.7, 0.4)
    assert probs == (0.7, 0.7, 0.4, 0.4, 0.7, 0.4, 0.7)


def test_series_length_labels() -> None:
    assert series_length_labels() == (4, 5, 6, 7)


# ── Known-probability edge cases ───────────────────────────────────────────


def test_coin_flip_series_is_symmetric() -> None:
    outcome = simulate_series(0.5, 0.5)
    assert outcome.p_a_win_series == pytest.approx(0.5)
    assert outcome.p_b_win_series == pytest.approx(0.5)
    assert outcome.e_wins_a == pytest.approx(outcome.e_wins_b)
    assert sum(outcome.length_probs.values()) == pytest.approx(1.0)


def test_certain_home_and_away_wins_produce_a_sweep() -> None:
    outcome = simulate_series(1.0, 1.0)
    assert outcome.p_a_win_series == pytest.approx(1.0)
    assert outcome.p_b_win_series == pytest.approx(0.0)
    assert outcome.length_probs[4] == pytest.approx(1.0)
    assert outcome.length_probs[5] == pytest.approx(0.0)
    assert outcome.e_games == pytest.approx(4.0)
    assert outcome.e_wins_a == pytest.approx(4.0)
    assert outcome.e_wins_b == pytest.approx(0.0)


def test_certain_losses_hand_the_series_to_b() -> None:
    outcome = simulate_series(0.0, 0.0)
    assert outcome.p_a_win_series == pytest.approx(0.0)
    assert outcome.p_b_win_series == pytest.approx(1.0)
    assert outcome.e_wins_b == pytest.approx(4.0)
    assert outcome.e_games == pytest.approx(4.0)


def test_length_probs_always_sum_to_one() -> None:
    outcome = simulate_series(0.62, 0.48)
    assert set(outcome.length_probs) == {4, 5, 6, 7}
    assert sum(outcome.length_probs.values()) == pytest.approx(1.0)
    # E[games] must lie inside the achievable [4, 7] range.
    assert 4.0 <= outcome.e_games <= 7.0


def test_stronger_team_more_likely_to_win_series() -> None:
    weak = simulate_series(0.55, 0.45)
    strong = simulate_series(0.80, 0.70)
    assert strong.p_a_win_series > weak.p_a_win_series > 0.5


def test_probabilities_are_clamped() -> None:
    outcome = simulate_series(1.5, -0.2)
    assert outcome.p_a_win_series == pytest.approx(1.0)
    assert 0.0 <= outcome.p_b_win_series <= 1.0


# ── Goalie-slot valuation through the rules engine ─────────────────────────


def test_expected_goalie_points_matches_rules_on_a_sweep() -> None:
    # A sweeps in 4. With every win a shutout the goalie slot scores 4*4 = 16
    # (goalie_series_points(4, 4)); with no shutouts 4*2 = 8.
    all_shutouts = simulate_series(1.0, 1.0, shutout_prob_a=1.0)
    no_shutouts = simulate_series(1.0, 1.0, shutout_prob_a=0.0)
    assert all_shutouts.e_goalie_points_a == pytest.approx(goalie_series_points(4, 4))
    assert no_shutouts.e_goalie_points_a == pytest.approx(goalie_series_points(4, 0))


def test_expected_goalie_points_is_linear_mean_of_rules() -> None:
    # E[pts] for 4 wins with per-win shutout prob 0.5 equals the binomial mean of
    # goalie_series_points(4, S), S ~ Binomial(4, 0.5).
    expected = sum(_binom(4, s, 0.5) * goalie_series_points(4, s) for s in range(5))
    assert expected_goalie_points(4.0, 0.5) == pytest.approx(expected)


def _binom(n: int, k: int, p: float) -> float:
    from math import comb

    return comb(n, k) * (p**k) * ((1.0 - p) ** (n - k))


def test_goalie_points_zero_for_the_series_loser_with_no_wins() -> None:
    outcome = simulate_series(1.0, 1.0, shutout_prob_a=0.3, shutout_prob_b=0.9)
    assert outcome.e_goalie_points_b == pytest.approx(0.0)


# ── Exact vs. Monte Carlo (determinism under a fixed seed) ─────────────────


def test_monte_carlo_matches_exact_enumeration() -> None:
    exact = simulate_series(0.63, 0.47, shutout_prob_a=0.2, shutout_prob_b=0.1)
    mc = simulate_series_monte_carlo(
        0.63, 0.47, shutout_prob_a=0.2, shutout_prob_b=0.1, n_sims=40000, seed=7
    )
    assert mc.p_a_win_series == pytest.approx(exact.p_a_win_series, abs=0.02)
    assert mc.e_games == pytest.approx(exact.e_games, abs=0.05)
    assert mc.e_wins_a == pytest.approx(exact.e_wins_a, abs=0.05)


def test_monte_carlo_is_deterministic_under_seed() -> None:
    a = simulate_series_monte_carlo(0.6, 0.5, n_sims=5000, seed=123)
    b = simulate_series_monte_carlo(0.6, 0.5, n_sims=5000, seed=123)
    assert a == b


# ── Synthetic multi-season league for the evaluation path ──────────────────

TEAMS = ["AAA", "BBB", "CCC", "DDD"]
STRENGTH = {"AAA": 3.0, "BBB": 1.0, "CCC": -1.0, "DDD": -3.0}
DEFENCE = {"AAA": 0.7, "BBB": 0.5, "CCC": 0.3, "DDD": 0.1}
SHOTS = 30


def _team_row(
    *,
    season_id: int,
    game_type_id: int,
    game_id: int,
    game_date: str,
    team: str,
    gf: int,
    ga: int,
    is_home: bool,
) -> dict[str, object]:
    won = gf > ga
    return {
        "season_id": season_id,
        "game_type_id": game_type_id,
        "game_id": game_id,
        "game_date": game_date,
        "team_id": TEAMS.index(team) + 1,
        "team_abbrev": team,
        "home_road": "H" if is_home else "R",
        "goals_for": gf,
        "goals_against": ga,
        "shots_against": SHOTS,
        "points": 2 if won else 0,
        "win": won,
        "shutout_win": won and ga == 0,
    }


def _game_rows(
    *,
    season_id: int,
    game_type_id: int,
    game_id: int,
    game_date: str,
    home: str,
    away: str,
    home_goals: int,
    away_goals: int,
) -> list[dict[str, object]]:
    return [
        _team_row(
            season_id=season_id,
            game_type_id=game_type_id,
            game_id=game_id,
            game_date=game_date,
            team=home,
            gf=home_goals,
            ga=away_goals,
            is_home=True,
        ),
        _team_row(
            season_id=season_id,
            game_type_id=game_type_id,
            game_id=game_id,
            game_date=game_date,
            team=away,
            gf=away_goals,
            ga=home_goals,
            is_home=False,
        ),
    ]


def _synthetic_league(end_years: list[int], *, seed: int = 0) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Round-robin regular seasons + one best-of-7 (AAA over DDD) per season."""
    rng = np.random.default_rng(seed)
    team_rows: list[dict[str, object]] = []
    series_rows: list[dict[str, object]] = []
    gid = 5_000_000

    for end_year in end_years:
        season_id = (end_year - 1) * 10000 + end_year
        day = 1
        for _ in range(6):
            for i, home in enumerate(TEAMS):
                for away in TEAMS[i + 1 :]:
                    gid += 1
                    p_home = 1.0 / (1.0 + np.exp(-(STRENGTH[home] - STRENGTH[away] + 0.3)))
                    home_win = bool(rng.random() < p_home)
                    winner = home if home_win else away
                    shutout = bool(rng.random() < DEFENCE[winner])
                    loser_goals = 0 if shutout else 2
                    hg, ag = (3, loser_goals) if home_win else (loser_goals, 3)
                    date = f"{end_year - 1}-11-{day:02d}"
                    day = day + 1 if day < 28 else 1
                    team_rows.extend(
                        _game_rows(
                            season_id=season_id,
                            game_type_id=2,
                            game_id=gid,
                            game_date=date,
                            home=home,
                            away=away,
                            home_goals=hg,
                            away_goals=ag,
                        )
                    )

        # Playoff series: AAA (top seed / home ice) beats DDD 4-1, with one
        # shutout, over five games following the 2-2-1-1-1 hosting pattern.
        top, bottom = "AAA", "DDD"
        game_results = [
            (top, 3, 0),  # game 1 (top home) shutout
            (top, 4, 2),  # game 2 (top home)
            (bottom, 1, 3),  # game 3 (bottom home) upset
            (top, 3, 1),  # game 4 (bottom home)
            (top, 2, 1),  # game 5 (top home) clincher
        ]
        for offset, (winner, wg, lg) in enumerate(game_results):
            gid += 1
            host = top if HOME_ICE_PATTERN[offset] == "A" else bottom
            visitor = bottom if host == top else top
            if winner == host:
                hg, ag = wg, lg
            else:
                hg, ag = lg, wg
            team_rows.extend(
                _game_rows(
                    season_id=season_id,
                    game_type_id=3,
                    game_id=gid,
                    game_date=f"{end_year}-04-{10 + offset:02d}",
                    home=host,
                    away=visitor,
                    home_goals=hg,
                    away_goals=ag,
                )
            )
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
                "bottom_seed_wins": 1,
                "winning_team_id": TEAMS.index(top) + 1,
                "losing_team_id": TEAMS.index(bottom) + 1,
            }
        )

    return pd.DataFrame(team_rows), pd.DataFrame(series_rows)


# ── Reconstruction (leakage-free pre-series states) ────────────────────────


def test_reconstruct_captures_pre_series_snapshots_and_shutouts() -> None:
    team_games, _ = _synthetic_league([2019], seed=3)
    matchups = reconstruct_series_matchups(team_games)
    assert len(matchups) == 1
    (record,) = matchups.values()
    top_id = TEAMS.index("AAA") + 1
    bottom_id = TEAMS.index("DDD") + 1
    assert top_id in record.win_snapshots
    assert bottom_id in record.shutout_snapshots
    # The AAA/DDD series had exactly one shutout (game 1) over five games.
    assert record.observed_shutouts == 1
    assert record.playoff_games == 5
    # Pre-series snapshots read a full regular season -> non-cold-start.
    assert record.win_snapshots[top_id]["points_per_game"] > 0.0


def _overlap_row(
    *,
    game_id: str,
    game_date: str,
    team: str,
    team_id: int,
    opp: str,
    gf: int,
    ga: int,
    is_home: bool,
    game_type_id: int = 3,
) -> dict[str, object]:
    won = gf > ga
    return {
        "season_id": 20212022,
        "game_type_id": game_type_id,
        "game_id": game_id,
        "game_date": game_date,
        "team_id": team_id,
        "team_abbrev": team,
        "opponent_team_abbrev": opp,
        "home_road": "H" if is_home else "R",
        "goals_for": gf,
        "goals_against": ga,
        "shots_against": SHOTS,
        "points": 2 if won else 0,
    }


def _overlap_game(
    *,
    game_id: str,
    game_date: str,
    home: str,
    home_id: int,
    away: str,
    away_id: int,
    hg: int,
    ag: int,
) -> list[dict[str, object]]:
    return [
        _overlap_row(
            game_id=game_id, game_date=game_date, team=home, team_id=home_id,
            opp=away, gf=hg, ga=ag, is_home=True,
        ),
        _overlap_row(
            game_id=game_id, game_date=game_date, team=away, team_id=away_id,
            opp=home, gf=ag, ga=hg, is_home=False,
        ),
    ]


def test_reconstruct_freezes_at_round_cutoff_not_matchup_first_game() -> None:
    # Overlapping rounds (CODE_REVIEW m-3): round 2's declared cutoff is the earliest
    # round-2 game (G/H on 05-01). Team E is still finishing round 1 on 05-01..05-03
    # -- those games are on/after the round-2 cutoff. E's round-2 (E/F) snapshot must
    # freeze at the cutoff (before E has played), never at E/F's later first game.
    e_id, f_id, g_id, h_id, x_id = 11, 12, 13, 14, 15
    rows: list[dict[str, object]] = []
    # E's round-1 series (digit 1) overlaps the round-2 window; E wins all three.
    for i, date in enumerate(("2022-05-01", "2022-05-02", "2022-05-03")):
        rows += _overlap_game(
            game_id=f"202103011{i + 1}", game_date=date,
            home="E", home_id=e_id, away="X", away_id=x_id, hg=3, ag=0,
        )
    # Round-2 series P (G/H, digit 2) sets the round-2 cutoff at 05-01.
    rows += _overlap_game(
        game_id="2021030211", game_date="2022-05-01",
        home="G", home_id=g_id, away="H", away_id=h_id, hg=3, ag=1,
    )
    # Round-2 series Q (E/F, digit 2) starts late, on 05-06.
    rows += _overlap_game(
        game_id="2021030221", game_date="2022-05-06",
        home="E", home_id=e_id, away="F", away_id=f_id, hg=2, ag=1,
    )
    team_games = pd.DataFrame(rows)
    series = pd.DataFrame(
        [
            {"season_id": 20212022, "top_seed_abbrev": "E",
             "bottom_seed_abbrev": "X", "playoff_round": 1},
            {"season_id": 20212022, "top_seed_abbrev": "G",
             "bottom_seed_abbrev": "H", "playoff_round": 2},
            {"season_id": 20212022, "top_seed_abbrev": "E",
             "bottom_seed_abbrev": "F", "playoff_round": 2},
        ]
    )
    q_key = (2022, min(e_id, f_id), max(e_id, f_id))

    # Legacy per-series freeze (no series context): E/F snapshot is frozen at E/F's
    # first game (05-06) and so absorbs E's post-cutoff round-1 wins -> elo != initial.
    legacy = reconstruct_series_matchups(team_games)
    assert legacy[q_key].win_snapshots[e_id]["elo"] != pytest.approx(1500.0)

    # Round-cutoff freeze: E has played nothing before the 05-01 cutoff, so its E/F
    # snapshot is the cold initial rating -- the overlapping round-1 games are excluded.
    fixed = reconstruct_series_matchups(team_games, series=series)
    assert fixed[q_key].win_snapshots[e_id]["elo"] == pytest.approx(1500.0)


# ── End-to-end evaluation ──────────────────────────────────────────────────


def test_evaluate_series_sim_scores_held_out_series() -> None:
    end_years = [2016, 2017, 2018, 2019, 2020, 2021]
    team_games, series = _synthetic_league(end_years, seed=5)
    result = evaluate_series_sim(
        team_games, series, config=SeriesSimConfig(seed=5, n_test_seasons=2)
    )
    assert result.test_years == (2020, 2021)
    assert result.n_series_scored == 2
    assert result.n_series_skipped == 0
    assert np.isfinite(result.brier_series)
    # Length distribution predicted rates sum to 1.
    total_predicted = sum(b.predicted_rate for b in result.length_bins)
    assert total_predicted == pytest.approx(1.0)
    # Observed lengths sum to 1 too (both held-out series went five games).
    observed = {b.length: b.observed_rate for b in result.length_bins}
    assert observed[5] == pytest.approx(1.0)


def test_evaluate_series_sim_shutouts_by_round() -> None:
    end_years = [2016, 2017, 2018, 2019, 2020, 2021]
    team_games, series = _synthetic_league(end_years, seed=9)
    result = evaluate_series_sim(
        team_games, series, config=SeriesSimConfig(seed=9, n_test_seasons=2)
    )
    # Each held-out series had one observed shutout -> two in round 1.
    assert result.observed_shutouts_by_round.get(1) == 2
    assert result.predicted_shutouts_by_round.get(1, 0.0) >= 0.0


def test_evaluate_series_sim_manifest_and_report() -> None:
    end_years = [2016, 2017, 2018, 2019, 2020, 2021]
    team_games, series = _synthetic_league(end_years, seed=1)
    result = evaluate_series_sim(
        team_games, series, config=SeriesSimConfig(seed=1, n_test_seasons=2)
    )
    manifest = result.manifest()
    assert manifest["model_version"] == "series-sim-v1"
    assert manifest["seed"] == 1
    assert manifest["test_years"] == [2020, 2021]
    assert "series_model" in manifest["brier"]
    assert any("series simulator" in line.lower() for line in result.report_lines())
