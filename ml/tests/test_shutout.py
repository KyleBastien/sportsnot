"""Tests for draft_oracle.models.shutout (US-012).

All fixtures are in-memory synthetic games -- no network, no committed-archive
dependency (SPEC section 7). The suite covers the base-rate baseline, the
leakage-free running goaltending state, the feature row + missing flags, the
winner-framed dataset build, probability bounds, monotonicity in goalie quality,
and an end-to-end train that beats the base-rate baseline on a held-out season.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from draft_oracle.models import (
    NEUTRAL_SAVE_PCT,
    SHUTOUT_FEATURE_COLUMNS,
    ShutoutConfig,
    ShutoutTeamState,
    base_rate_probs,
    build_shutout_dataset,
    shutout_feature_row,
    train_shutout_model,
)

TEAMS = ["AAA", "BBB", "CCC", "DDD"]
# Latent win strength (who wins) and defence quality (how often the winner
# records a shutout). Strong defence -> more shutouts + higher save %.
STRENGTH = {"AAA": 3.0, "BBB": 1.0, "CCC": -1.0, "DDD": -3.0}
DEFENCE = {"AAA": 0.85, "BBB": 0.6, "CCC": 0.3, "DDD": 0.1}
SHOTS = 30


def _game_rows(
    *,
    game_id: int,
    game_date: str,
    season_id: int,
    game_type_id: int,
    home: str,
    away: str,
    home_goals: int,
    away_goals: int,
) -> list[dict[str, object]]:
    """Two archive-shaped rows (home + away) for one decided game."""

    def row(team: str, gf: int, ga: int, is_home: bool) -> dict[str, object]:
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

    return [
        row(home, home_goals, away_goals, True),
        row(away, away_goals, home_goals, False),
    ]


def _synthetic_team_games(*, seasons: list[int], seed: int = 0) -> pd.DataFrame:
    """Round-robin regular season + a short playoff for several seasons.

    The winner is drawn from ``sigmoid(strength_home - strength_away + edge)``; the
    winner records a shutout with probability equal to its defence quality. Strong
    defences therefore shut opponents out more often *and* face fewer goals (higher
    save %), so the model can learn goalie quality -> shutout upside.
    """
    rng = np.random.default_rng(seed)
    rows: list[dict[str, object]] = []
    gid = 2000000
    for season_id in seasons:
        day = 1
        for _ in range(4):
            for i, home in enumerate(TEAMS):
                for away in TEAMS[i + 1 :]:
                    gid += 1
                    p_home = 1.0 / (1.0 + np.exp(-(STRENGTH[home] - STRENGTH[away] + 0.4)))
                    home_win = bool(rng.random() < p_home)
                    winner = home if home_win else away
                    shutout = bool(rng.random() < DEFENCE[winner])
                    loser_goals = 0 if shutout else 2
                    if home_win:
                        hg, ag = 3, loser_goals
                    else:
                        hg, ag = loser_goals, 3
                    date = f"{season_id // 10000}-11-{day:02d}"
                    day = day + 1 if day < 28 else 1
                    rows.extend(
                        _game_rows(
                            game_id=gid,
                            game_date=date,
                            season_id=season_id,
                            game_type_id=2,
                            home=home,
                            away=away,
                            home_goals=hg,
                            away_goals=ag,
                        )
                    )
        gid += 1
        rows.extend(
            _game_rows(
                game_id=gid,
                game_date=f"{season_id // 10000 + 1}-04-20",
                season_id=season_id,
                game_type_id=3,
                home="AAA",
                away="DDD",
                home_goals=3,
                away_goals=0,
            )
        )
    return pd.DataFrame(rows)


# ── Baseline ───────────────────────────────────────────────────────────────


def test_base_rate_probs() -> None:
    probs = base_rate_probs(3, 0.08)
    assert probs.tolist() == [0.08, 0.08, 0.08]


# ── Running goaltending state ──────────────────────────────────────────────


def test_state_cold_start_is_zero() -> None:
    snap = ShutoutTeamState().snapshot()
    assert snap["save_pct_season"] == 0.0
    assert snap["save_pct_l15"] == 0.0
    assert snap["team_shutout_rate"] == 0.0
    assert snap["goals_for_per_game"] == 0.0


def test_state_accumulates_save_pct_and_shutouts() -> None:
    state = ShutoutTeamState()
    state.record_regular_season(goals_for=3, goals_against=0, shots_against=30, won=True)
    state.record_regular_season(goals_for=1, goals_against=3, shots_against=30, won=False)
    snap = state.snapshot()
    # 3 goals allowed on 60 shots -> save pct 0.95.
    assert snap["save_pct_season"] == pytest.approx(0.95)
    assert snap["team_shutout_rate"] == pytest.approx(0.5)
    assert snap["goals_for_per_game"] == pytest.approx(2.0)


def test_state_l15_window_only_keeps_recent() -> None:
    state = ShutoutTeamState(last_n=2)
    state.record_regular_season(goals_for=1, goals_against=6, shots_against=30, won=False)
    state.record_regular_season(goals_for=1, goals_against=0, shots_against=30, won=True)
    state.record_regular_season(goals_for=1, goals_against=0, shots_against=30, won=True)
    snap = state.snapshot()
    # Only the last two games (0 + 0 GA on 60 shots) count -> perfect L15 save pct.
    assert snap["save_pct_l15"] == pytest.approx(1.0)


def test_state_reset_season_clears_counters() -> None:
    state = ShutoutTeamState()
    state.record_regular_season(goals_for=3, goals_against=0, shots_against=30, won=True)
    state.reset_season()
    snap = state.snapshot()
    assert snap["save_pct_season"] == 0.0
    assert snap["team_shutout_rate"] == 0.0


# ── Feature row ────────────────────────────────────────────────────────────


def _snap(save_season: float, save_l15: float, sho_rate: float, gf: float) -> dict[str, float]:
    return {
        "save_pct_season": save_season,
        "save_pct_l15": save_l15,
        "team_shutout_rate": sho_rate,
        "goals_for_per_game": gf,
    }


def test_feature_row_missing_backup_is_flagged_neutral() -> None:
    row = shutout_feature_row(_snap(0.92, 0.9, 0.1, 3.0), _snap(0.9, 0.9, 0.05, 2.8))
    assert row["winner_save_pct_season"] == pytest.approx(0.92)
    assert row["opponent_goals_for_per_game"] == pytest.approx(2.8)
    assert row["backup_save_pct"] == pytest.approx(NEUTRAL_SAVE_PCT)
    assert row["goalie_split_available"] == 0.0
    assert row["starter_unavailability_risk"] == 0.0
    assert row["goalie_injury_data_available"] == 0.0
    assert set(SHUTOUT_FEATURE_COLUMNS) == set(row)


def test_feature_row_supplied_backup_and_risk_are_flagged() -> None:
    row = shutout_feature_row(
        _snap(0.92, 0.9, 0.1, 3.0),
        _snap(0.9, 0.9, 0.05, 2.8),
        backup_save_pct=0.88,
        starter_unavailability_risk=1.0,
        goalie_injury_data_available=True,
    )
    assert row["backup_save_pct"] == pytest.approx(0.88)
    assert row["goalie_split_available"] == 1.0
    assert row["starter_unavailability_risk"] == 1.0
    assert row["goalie_injury_data_available"] == 1.0


# ── Dataset build (leakage-free, winner-framed) ────────────────────────────


def test_build_dataset_first_game_has_no_pregame_leakage() -> None:
    team_games = _synthetic_team_games(seasons=[20182019])
    dataset = build_shutout_dataset(team_games, min_pregame_games=0)
    assert not dataset.empty
    first = dataset.sort_values("game_id").iloc[0]
    # The winner's very first game sees zero prior games -> neutral proxies.
    assert first["winner_pregame_games"] == 0.0
    assert first["winner_save_pct_season"] == 0.0
    for col in SHUTOUT_FEATURE_COLUMNS:
        assert dataset[col].notna().all()


def test_build_dataset_label_is_shutout_flag() -> None:
    team_games = _synthetic_team_games(seasons=[20182019], seed=2)
    dataset = build_shutout_dataset(team_games, min_pregame_games=0)
    assert set(dataset["is_shutout"].unique()).issubset({0.0, 1.0})
    # Some shutouts and some non-shutouts exist in the synthetic set.
    assert 0.0 < dataset["is_shutout"].mean() < 1.0


def test_build_dataset_min_pregame_filter_drops_cold_start() -> None:
    team_games = _synthetic_team_games(seasons=[20182019])
    dataset = build_shutout_dataset(team_games, min_pregame_games=5)
    assert (dataset["winner_pregame_games"] >= 5).all()


# ── End-to-end train ───────────────────────────────────────────────────────


def test_train_beats_base_rate_and_bounds_probabilities() -> None:
    seasons = [20182019, 20192020, 20202021, 20212022, 20222023]
    team_games = _synthetic_team_games(seasons=seasons, seed=7)
    result = train_shutout_model(team_games, config=ShutoutConfig(seed=7, min_pregame_games=0))
    assert result.test_brier_model <= result.test_brier_base_rate
    assert result.chosen_model_type in {"logistic_regression", "lightgbm"}
    probs = result.model.predict_shutout_prob(
        build_shutout_dataset(team_games, min_pregame_games=0)
    )
    assert np.all(probs >= 0.0) and np.all(probs <= 1.0)


def test_train_is_monotone_in_goalie_quality() -> None:
    seasons = [20182019, 20192020, 20202021, 20212022, 20222023]
    team_games = _synthetic_team_games(seasons=seasons, seed=11)
    result = train_shutout_model(team_games, config=ShutoutConfig(seed=11, min_pregame_games=0))
    loser = _snap(0.9, 0.9, 0.05, 2.5)
    weak_goalie = _snap(0.80, 0.80, 0.02, 2.8)
    strong_goalie = _snap(0.94, 0.94, 0.25, 2.8)
    p_weak = result.model.predict_matchup(weak_goalie, loser)
    p_strong = result.model.predict_matchup(strong_goalie, loser)
    assert 0.0 <= p_weak <= p_strong <= 1.0
    assert p_strong > p_weak


def test_train_manifest_records_seed_and_calibration() -> None:
    seasons = [20182019, 20192020, 20202021, 20212022, 20222023]
    team_games = _synthetic_team_games(seasons=seasons, seed=1)
    result = train_shutout_model(team_games, config=ShutoutConfig(seed=1, min_pregame_games=0))
    manifest = result.manifest()
    assert manifest["seed"] == 1
    assert manifest["split"]["test_years"] == [2022, 2023]
    assert manifest["model_version"] == "shutout-v1"
    assert "relative_error" in manifest["calibration"]
    assert np.isfinite(result.test_observed_rate)
    assert np.isfinite(result.test_predicted_rate)
    # The report renders without error and mentions the model.
    assert any("Shutout probability model" in line for line in result.report_lines())
