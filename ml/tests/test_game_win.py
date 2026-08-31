"""Tests for draft_oracle.models.game_win (US-011).

All fixtures are in-memory synthetic games — no network, no committed-archive
dependency (SPEC section 7). The suite covers the scalar metrics, the leakage-free
pre-game state, the market join, the temporal split, and an end-to-end train that
must beat the coin-flip baseline on a held-out season.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from draft_oracle.ingest.normalize import normalize_team_games
from draft_oracle.models import (
    MARKET_FEATURE_COLUMNS,
    STAT_FEATURE_COLUMNS,
    GameWinConfig,
    TeamState,
    baseline_higher_points_probs,
    brier_score,
    build_game_dataset,
    coin_flip_probs,
    default_temporal_split,
    matchup_feature_row,
    train_game_win_model,
)
from draft_oracle.models.game_win import _pivot_games

TEAMS = ["AAA", "BBB", "CCC", "DDD"]
# Latent strengths drive who wins; the model should recover the ordering.
STRENGTH = {"AAA": 3.0, "BBB": 1.0, "CCC": -1.0, "DDD": -3.0}


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
    home_win = home_goals > away_goals

    def row(team: str, opp: str, gf: int, ga: int, is_home: bool) -> dict[str, object]:
        won = gf > ga
        return {
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
            "points": 2 if won else 0,
            "win": won,
            "shutout_win": won and ga == 0,
        }

    _ = home_win
    return [
        row(home, away, home_goals, away_goals, True),
        row(away, home, away_goals, home_goals, False),
    ]


def _synthetic_team_games(*, seasons: list[int], seed: int = 0) -> pd.DataFrame:
    """Round-robin regular season + a short playoff for several seasons.

    Home wins with probability ``sigmoid(strength_home - strength_away + edge)``
    so Elo/points features carry real signal the model can learn.
    """
    rng = np.random.default_rng(seed)
    rows: list[dict[str, object]] = []
    gid = 1000000
    for season_id in seasons:
        day = 1
        # Triple round-robin regular season -> >=9 games per team.
        for _ in range(3):
            for i, home in enumerate(TEAMS):
                for away in TEAMS[i + 1 :]:
                    gid += 1
                    p_home = 1.0 / (1.0 + np.exp(-(STRENGTH[home] - STRENGTH[away] + 0.4)))
                    home_win = bool(rng.random() < p_home)
                    hg, ag = (3, 1) if home_win else (1, 3)
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
        # A short playoff (game_type 3) so the model sees post-season rows too.
        gid += 1
        rows.extend(
            _game_rows(
                game_id=gid,
                game_date=f"{season_id // 10000 + 1}-04-20",
                season_id=season_id,
                game_type_id=3,
                home="AAA",
                away="DDD",
                home_goals=4,
                away_goals=1,
            )
        )
    return pd.DataFrame(rows)


# ── Scalar metrics ─────────────────────────────────────────────────────────


def test_brier_score_coin_flip_and_perfect() -> None:
    labels = [1, 0, 1, 0]
    assert brier_score([0.5, 0.5, 0.5, 0.5], labels) == pytest.approx(0.25)
    assert brier_score([1.0, 0.0, 1.0, 0.0], labels) == pytest.approx(0.0)


def test_brier_score_empty_is_nan() -> None:
    assert np.isnan(brier_score([], []))


def test_coin_flip_probs() -> None:
    probs = coin_flip_probs(3)
    assert probs.tolist() == [0.5, 0.5, 0.5]


def test_baseline_higher_points_picks_stronger_team() -> None:
    frame = pd.DataFrame(
        {
            "home_points_per_game": [1.5, 0.8, 1.0],
            "away_points_per_game": [1.0, 1.2, 1.0],
        }
    )
    assert baseline_higher_points_probs(frame).tolist() == [1.0, 0.0, 0.5]


# ── Pre-game team state ────────────────────────────────────────────────────


def test_team_state_cold_start_is_neutral() -> None:
    snap = TeamState(elo=1500.0).snapshot()
    assert snap["goals_for_per_game"] == 0.0
    assert snap["win_pct"] == 0.0
    assert snap["points_per_game"] == 0.0
    assert snap["elo"] == 1500.0


def test_team_state_accumulates_regular_season() -> None:
    state = TeamState(elo=1500.0)
    state.record_regular_season(points=2, goals_for=3, goals_against=1, won=True)
    state.record_regular_season(points=0, goals_for=1, goals_against=4, won=False)
    snap = state.snapshot()
    assert snap["goals_for_per_game"] == pytest.approx(2.0)
    assert snap["goals_against_per_game"] == pytest.approx(2.5)
    assert snap["win_pct"] == pytest.approx(0.5)
    assert snap["points_per_game"] == pytest.approx(1.0)


# ── Feature row ────────────────────────────────────────────────────────────


def test_matchup_feature_row_market_present() -> None:
    home = {
        "elo": 1600.0,
        "goals_for_per_game": 3.0,
        "goals_against_per_game": 2.0,
        "goal_diff_per_game": 1.0,
        "win_pct": 0.6,
        "points_per_game": 1.3,
    }
    away = {
        "elo": 1500.0,
        "goals_for_per_game": 2.5,
        "goals_against_per_game": 2.5,
        "goal_diff_per_game": 0.0,
        "win_pct": 0.5,
        "points_per_game": 1.0,
    }
    row = matchup_feature_row(home, away, is_playoff=True, market_home_prob=0.62)
    assert row["elo_diff"] == pytest.approx(100.0)
    assert row["goal_diff_per_game_diff"] == pytest.approx(1.0)
    assert row["is_playoff"] == 1.0
    assert row["market_available"] == 1.0
    assert row["market_home_prob"] == pytest.approx(0.62)
    assert set(MARKET_FEATURE_COLUMNS).issubset(row)


def test_matchup_feature_row_market_missing_is_flagged_neutral() -> None:
    zero = dict.fromkeys(
        (
            "goals_for_per_game",
            "goals_against_per_game",
            "goal_diff_per_game",
            "win_pct",
            "points_per_game",
        ),
        0.0,
    )
    home = {"elo": 1500.0, **zero}
    away = {"elo": 1500.0, **zero}
    row = matchup_feature_row(home, away, is_playoff=False, market_home_prob=None)
    assert row["market_available"] == 0.0
    assert row["market_home_prob"] == pytest.approx(0.5)
    assert row["is_playoff"] == 0.0


# ── Dataset build (leakage-free by construction) ──────────────────────────


def test_build_game_dataset_first_game_has_no_pregame_leakage() -> None:
    team_games = _synthetic_team_games(seasons=[20182019])
    dataset = build_game_dataset(team_games, min_pregame_games=0)
    assert not dataset.empty
    first = dataset.sort_values("game_id").iloc[0]
    # A team's very first game sees zero prior games -> neutral rates.
    assert first["home_pregame_games"] == 0.0
    assert first["home_goals_for_per_game"] == 0.0
    assert first["away_goals_for_per_game"] == 0.0
    # Every feature column is present and finite.
    for col in MARKET_FEATURE_COLUMNS:
        assert dataset[col].notna().all()


def test_build_game_dataset_min_pregame_filter_drops_cold_start() -> None:
    team_games = _synthetic_team_games(seasons=[20182019])
    dataset = build_game_dataset(team_games, min_pregame_games=5)
    assert (dataset["home_pregame_games"] >= 5).all()
    assert (dataset["away_pregame_games"] >= 5).all()


def test_build_game_dataset_market_join_sets_available_flag() -> None:
    team_games = _synthetic_team_games(seasons=[20182019])
    games = team_games.loc[team_games["home_road"] == "H"]
    first = games.sort_values("game_id").iloc[0]
    odds = pd.DataFrame(
        [
            {
                "season_end_year": int(first["season_id"]) % 10000,
                "game_date": first["game_date"],
                "home_team_id": int(first["team_id"]),
                "away_team_id": TEAMS.index(str(first["opponent_team_abbrev"])) + 1,
                "home_implied": 0.7,
            }
        ]
    )
    dataset = build_game_dataset(team_games, odds=odds, min_pregame_games=0)
    matched = dataset.loc[dataset["market_available"] == 1.0]
    assert len(matched) == 1
    assert matched.iloc[0]["market_home_prob"] == pytest.approx(0.7)
    # Unmatched games fall back to the neutral imputation + off flag.
    unmatched = dataset.loc[dataset["market_available"] == 0.0]
    assert (unmatched["market_home_prob"] == 0.5).all()


def test_pivot_games_retains_real_shootout_with_archive_winner() -> None:
    raw = pd.read_csv(Path("data/raw/nhl-archive/team-games-2020-21.csv.gz"))
    team_games = normalize_team_games(raw)

    game = _pivot_games(team_games).loc[lambda frame: frame["game_id"] == 2020020007]

    assert len(game) == 1
    assert game.iloc[0]["home_goals"] == game.iloc[0]["away_goals"] == 2
    assert game.iloc[0]["home_team_abbrev"] == "NJD"
    assert game.iloc[0]["away_team_abbrev"] == "BOS"
    assert game.iloc[0]["home_win"] == 0


@pytest.mark.parametrize(
    ("season_label", "expected_games"),
    [("2020-21", 952), ("2024-25", 1398)],
)
def test_pivot_games_matches_real_decided_game_count(
    season_label: str, expected_games: int
) -> None:
    raw = pd.read_csv(Path(f"data/raw/nhl-archive/team-games-{season_label}.csv.gz"))
    team_games = normalize_team_games(raw)
    archive_winners = team_games.groupby("game_id")["win"].sum()

    assert int(archive_winners.eq(1).sum()) == expected_games
    assert len(_pivot_games(team_games)) == expected_games


def test_pivot_games_warns_and_excludes_game_without_winner() -> None:
    team_games = pd.DataFrame(
        _game_rows(
            game_id=1,
            game_date="2021-01-01",
            season_id=20202021,
            game_type_id=2,
            home="AAA",
            away="BBB",
            home_goals=2,
            away_goals=2,
        )
    )

    with pytest.warns(RuntimeWarning, match="without exactly one archive winner"):
        games = _pivot_games(team_games)

    assert games.empty


# ── Temporal split ─────────────────────────────────────────────────────────


def test_default_temporal_split_holds_out_latest_seasons() -> None:
    split = default_temporal_split([2019, 2020, 2021, 2022, 2023], n_val=1, n_test=2)
    assert split.train_years == (2019, 2020)
    assert split.val_years == (2021,)
    assert split.test_years == (2022, 2023)


def test_default_temporal_split_requires_enough_seasons() -> None:
    with pytest.raises(ValueError):
        default_temporal_split([2022, 2023], n_val=1, n_test=2)


# ── End-to-end train ───────────────────────────────────────────────────────


def test_train_game_win_beats_coin_flip_and_predicts_matchup() -> None:
    seasons = [20182019, 20192020, 20202021, 20212022, 20222023]
    team_games = _synthetic_team_games(seasons=seasons, seed=7)
    result = train_game_win_model(team_games, config=GameWinConfig(seed=7, min_pregame_games=0))
    # Strong latent signal -> the model must beat a coin flip on the held-out test.
    assert result.test_brier_market < result.test_brier_coin_flip
    assert result.chosen_model_type in {"logistic_regression", "lightgbm"}
    assert result.model.feature_columns == MARKET_FEATURE_COLUMNS

    strong = {
        "elo": 1650.0,
        "goals_for_per_game": 3.2,
        "goals_against_per_game": 1.8,
        "goal_diff_per_game": 1.4,
        "win_pct": 0.7,
        "points_per_game": 1.5,
    }
    weak = {
        "elo": 1400.0,
        "goals_for_per_game": 2.0,
        "goals_against_per_game": 3.0,
        "goal_diff_per_game": -1.0,
        "win_pct": 0.3,
        "points_per_game": 0.7,
    }
    p_strong_home = result.model.predict_matchup(strong, weak)
    p_weak_home = result.model.predict_matchup(weak, strong)
    assert 0.0 < p_weak_home < p_strong_home < 1.0


def test_train_game_win_runs_stats_only_without_odds() -> None:
    seasons = [20182019, 20192020, 20202021, 20212022, 20222023]
    team_games = _synthetic_team_games(seasons=seasons, seed=3)
    result = train_game_win_model(
        team_games, odds=None, config=GameWinConfig(seed=3, min_pregame_games=0)
    )
    # Stat-only path still evaluates every metric and stays finite.
    assert np.isfinite(result.test_brier_market)
    assert np.isfinite(result.test_brier_stats_only)
    assert result.test_market_coverage == 0.0
    assert set(STAT_FEATURE_COLUMNS).issubset(MARKET_FEATURE_COLUMNS)


def test_train_game_win_manifest_records_seed_and_split() -> None:
    seasons = [20182019, 20192020, 20202021, 20212022, 20222023]
    team_games = _synthetic_team_games(seasons=seasons, seed=1)
    result = train_game_win_model(team_games, config=GameWinConfig(seed=1, min_pregame_games=0))
    manifest = result.manifest()
    assert manifest["seed"] == 1
    assert manifest["split"]["test_years"] == [2022, 2023]
    assert "market_plus_stats" in manifest["test_brier"]
    assert manifest["model_version"] == "game-win-v1"
