"""Tests for draft_oracle.features.team_series (US-010).

All fixtures are in-memory — no network, no committed-archive dependency
(SPEC §7). The suite covers each scalar primitive, the Elo replay + update rule,
the leakage guard, and the market / injuries / matchup joins with their explicit
missing-flags.
"""

from __future__ import annotations

import math

import pandas as pd
import pytest

from draft_oracle.features import (
    TEAM_FEATURE_COLUMNS,
    EloConfig,
    LeakageError,
    TeamSeriesFeatureConfig,
    assert_no_leakage,
    build_round_team_series_matrix,
    build_team_series_features,
    compute_elo_ratings,
    days_between,
    expected_score,
    goal_differential_per_game,
    regress_to_mean,
    save_pct,
    update_rating,
)

SEASON = 20232024
ROUND1_START = "2024-04-20"
ROUND2_START = "2024-05-05"

TOR = 10
BOS = 6


def _team_row(
    *,
    game_id: int,
    game_date: str,
    team_id: int,
    team_abbrev: str,
    opponent: str,
    home_road: str,
    goals_for: int,
    goals_against: int,
    shots_for: int,
    shots_against: int,
    power_play_pct: float,
    penalty_kill_pct: float,
    faceoff_win_pct: float,
    game_type: int = 2,
) -> dict[str, object]:
    win = goals_for > goals_against
    return {
        "season_id": SEASON,
        "game_type_id": game_type,
        "game_id": game_id,
        "game_date": game_date,
        "team_id": team_id,
        "team_abbrev": team_abbrev,
        "opponent_team_abbrev": opponent,
        "home_road": home_road,
        "goals_for": goals_for,
        "goals_against": goals_against,
        "shots_for": shots_for,
        "shots_against": shots_against,
        "power_play_pct": power_play_pct,
        "penalty_kill_pct": penalty_kill_pct,
        "faceoff_win_pct": faceoff_win_pct,
        "win": win,
        "shutout_win": win and goals_against == 0,
    }


def _game(
    *,
    game_id: int,
    game_date: str,
    home_id: int,
    home_abbrev: str,
    away_id: int,
    away_abbrev: str,
    home_goals: int,
    away_goals: int,
    game_type: int = 2,
) -> list[dict[str, object]]:
    """Two mirror rows (home + away) for a single game."""
    return [
        _team_row(
            game_id=game_id,
            game_date=game_date,
            team_id=home_id,
            team_abbrev=home_abbrev,
            opponent=away_abbrev,
            home_road="H",
            goals_for=home_goals,
            goals_against=away_goals,
            shots_for=32,
            shots_against=30,
            power_play_pct=0.25,
            penalty_kill_pct=0.80,
            faceoff_win_pct=0.52,
            game_type=game_type,
        ),
        _team_row(
            game_id=game_id,
            game_date=game_date,
            team_id=away_id,
            team_abbrev=away_abbrev,
            opponent=home_abbrev,
            home_road="R",
            goals_for=away_goals,
            goals_against=home_goals,
            shots_for=28,
            shots_against=34,
            power_play_pct=0.15,
            penalty_kill_pct=0.75,
            faceoff_win_pct=0.48,
            game_type=game_type,
        ),
    ]


def _team_games() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    # TOR vs BOS: TOR wins g1 (4-1) and g3 (3-0 shutout); BOS wins g2 and g4.
    rows += _game(
        game_id=1,
        game_date="2024-01-05",
        home_id=TOR,
        home_abbrev="TOR",
        away_id=BOS,
        away_abbrev="BOS",
        home_goals=4,
        away_goals=1,
    )
    rows += _game(
        game_id=2,
        game_date="2024-02-10",
        home_id=BOS,
        home_abbrev="BOS",
        away_id=TOR,
        away_abbrev="TOR",
        home_goals=3,
        away_goals=2,
    )
    rows += _game(
        game_id=3,
        game_date="2024-03-15",
        home_id=TOR,
        home_abbrev="TOR",
        away_id=BOS,
        away_abbrev="BOS",
        home_goals=3,
        away_goals=0,
    )
    rows += _game(
        game_id=4,
        game_date="2024-04-01",
        home_id=BOS,
        home_abbrev="BOS",
        away_id=TOR,
        away_abbrev="TOR",
        home_goals=2,
        away_goals=1,
    )
    return pd.DataFrame(rows)


def _odds() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "season_end_year": 2024,
                "game_date": "2024-01-05",
                "is_playoff": False,
                "home_team_id": TOR,
                "away_team_id": BOS,
                "home_implied": 0.60,
                "away_implied": 0.40,
            },
            {
                "season_end_year": 2024,
                "game_date": "2024-02-10",
                "is_playoff": False,
                "home_team_id": BOS,
                "away_team_id": TOR,
                "home_implied": 0.55,
                "away_implied": 0.45,
            },
        ]
    )


def _injuries() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "player_id": 999,
                "player_name": "Backup Goalie",
                "position": "G",
                "team_id": BOS,
                "team_abbrev": "BOS",
                "status": "out",
            },
            {
                "player_id": 111,
                "player_name": "A Forward",
                "position": "C",
                "team_id": TOR,
                "team_abbrev": "TOR",
                "status": "out",
            },
        ]
    )


def _matchups() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "team_abbrev": "TOR",
                "opponent_team_abbrev": "BOS",
                "home_ice": True,
                "series_implied_win_prob": 0.58,
            },
            {
                "team_abbrev": "BOS",
                "opponent_team_abbrev": "TOR",
                "home_ice": False,
                "series_implied_win_prob": 0.42,
            },
        ]
    )


# ── Scalar primitives ────────────────────────────────────────────────────


def test_goal_differential_per_game() -> None:
    assert goal_differential_per_game(10, 4, 3) == pytest.approx(2.0)
    assert goal_differential_per_game(5, 5, 0) == 0.0


def test_save_pct() -> None:
    assert save_pct(6, 124) == pytest.approx(1 - 6 / 124)
    assert save_pct(3, 0) == 0.0


def test_days_between() -> None:
    dates = [pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-04"), pd.Timestamp("2024-01-05")]
    assert days_between(dates) == pytest.approx(2.0)  # gaps 3 and 1
    assert days_between([pd.Timestamp("2024-01-01")]) == 0.0


def test_expected_score_symmetry_and_home_edge() -> None:
    assert expected_score(1500, 1500) == pytest.approx(0.5)
    assert expected_score(1500, 1500, 50) > 0.5
    a = expected_score(1600, 1400)
    b = expected_score(1400, 1600)
    assert a + b == pytest.approx(1.0)


def test_update_rating() -> None:
    assert update_rating(1500, 0.5, 1.0, 20) == pytest.approx(1510.0)
    assert update_rating(1500, 0.5, 0.0, 20) == pytest.approx(1490.0)


def test_regress_to_mean() -> None:
    assert regress_to_mean(1600, 1500, 0.25) == pytest.approx(1575.0)
    assert regress_to_mean(1600, 1500, 0.0) == pytest.approx(1600.0)
    assert regress_to_mean(1600, 1500, 1.0) == pytest.approx(1500.0)


# ── Elo replay ───────────────────────────────────────────────────────────


def test_compute_elo_ratings_conserves_total_and_excludes_cutoff() -> None:
    ratings = compute_elo_ratings(_team_games(), as_of_date=ROUND1_START)
    assert set(ratings) == {"TOR", "BOS"}
    # Elo is zero-sum around the initial mean: total stays at 2 * initial.
    assert sum(ratings.values()) == pytest.approx(3000.0)


def test_compute_elo_ratings_ignores_games_on_or_after_cutoff() -> None:
    base = _team_games()
    leaked = pd.concat(
        [
            base,
            pd.DataFrame(
                _game(
                    game_id=99,
                    game_date=ROUND1_START,
                    home_id=TOR,
                    home_abbrev="TOR",
                    away_id=BOS,
                    away_abbrev="BOS",
                    home_goals=10,
                    away_goals=0,
                )
            ),
        ],
        ignore_index=True,
    )
    assert compute_elo_ratings(base, as_of_date=ROUND1_START) == compute_elo_ratings(
        leaked, as_of_date=ROUND1_START
    )


def test_season_regression_applied_across_seasons() -> None:
    prior = pd.DataFrame(
        _game(
            game_id=500,
            game_date="2023-01-05",
            home_id=TOR,
            home_abbrev="TOR",
            away_id=BOS,
            away_abbrev="BOS",
            home_goals=6,
            away_goals=0,
        )
    )
    prior["season_id"] = 20222023
    combined = pd.concat([prior, _team_games()], ignore_index=True)
    with_regress = compute_elo_ratings(
        combined, as_of_date=ROUND1_START, config=EloConfig(season_regression=0.5)
    )
    no_regress = compute_elo_ratings(
        combined, as_of_date=ROUND1_START, config=EloConfig(season_regression=0.0)
    )
    # Both stay zero-sum, but heavy regression pulls the leader back toward mean.
    assert sum(with_regress.values()) == pytest.approx(3000.0)
    assert abs(with_regress["TOR"] - 1500) < abs(no_regress["TOR"] - 1500)


# ── Leakage guard ────────────────────────────────────────────────────────


def test_assert_no_leakage_raises_on_future_team_game() -> None:
    leaked = pd.DataFrame(
        _game(
            game_id=99,
            game_date="2024-04-22",
            home_id=TOR,
            home_abbrev="TOR",
            away_id=BOS,
            away_abbrev="BOS",
            home_goals=1,
            away_goals=0,
        )
    )
    with pytest.raises(LeakageError):
        assert_no_leakage(leaked, ROUND1_START)


def test_build_ignores_games_on_or_after_cutoff() -> None:
    base = _team_games()
    leaked = pd.concat(
        [
            base,
            pd.DataFrame(
                _game(
                    game_id=99,
                    game_date=ROUND1_START,
                    home_id=TOR,
                    home_abbrev="TOR",
                    away_id=BOS,
                    away_abbrev="BOS",
                    home_goals=10,
                    away_goals=0,
                )
            ),
        ],
        ignore_index=True,
    )
    clean = build_team_series_features(base, season_id=SEASON, as_of_date=ROUND1_START)
    dirty = build_team_series_features(leaked, season_id=SEASON, as_of_date=ROUND1_START)
    tor_clean = clean.loc[clean["team_abbrev"] == "TOR", "goals_for_per_game"].iloc[0]
    tor_dirty = dirty.loc[dirty["team_abbrev"] == "TOR", "goals_for_per_game"].iloc[0]
    assert tor_clean == tor_dirty


# ── Frame-level builder ──────────────────────────────────────────────────


def test_build_team_series_features_core_values() -> None:
    matrix = build_team_series_features(
        _team_games(), season_id=SEASON, as_of_date=ROUND1_START, playoff_round=1
    )
    assert list(matrix.columns) == list(TEAM_FEATURE_COLUMNS)
    assert set(matrix["team_abbrev"]) == {"TOR", "BOS"}

    tor = matrix.loc[matrix["team_abbrev"] == "TOR"].iloc[0]
    # TOR scored 4+2+3+1 = 10 over 4 games; allowed 1+3+0+2 = 6.
    assert tor["goals_for_per_game"] == pytest.approx(10 / 4)
    assert tor["goals_against_per_game"] == pytest.approx(6 / 4)
    assert tor["goal_differential_per_game"] == pytest.approx(1.0)
    # TOR shots-against: 30 (g1) + 34 (g2) + 30 (g3) + 34 (g4) = 128; GA = 6.
    assert tor["starter_save_pct_season"] == pytest.approx(1 - 6 / 128)
    # One shutout win (g3) over 4 games.
    assert tor["team_shutout_rate"] == pytest.approx(0.25)
    assert tor["playoff_round"] == 1
    assert tor["as_of_date"] == ROUND1_START
    # Per-goalie split is unavailable in the committed archive.
    assert bool(tor["goalie_split_available"]) is False
    assert pd.isna(tor["backup_save_pct"])
    assert tor["rest_days"] == pytest.approx(
        (pd.Timestamp(ROUND1_START) - pd.Timestamp("2024-04-01")).days
    )


def test_min_games_filter() -> None:
    cfg = TeamSeriesFeatureConfig(min_games=5)
    matrix = build_team_series_features(
        _team_games(), season_id=SEASON, as_of_date=ROUND1_START, config=cfg
    )
    assert matrix.empty
    assert list(matrix.columns) == list(TEAM_FEATURE_COLUMNS)


def test_market_join_and_missing_flag() -> None:
    with_odds = build_team_series_features(
        _team_games(), season_id=SEASON, as_of_date=ROUND1_START, odds=_odds()
    )
    tor = with_odds.loc[with_odds["team_abbrev"] == "TOR"].iloc[0]
    # TOR implied: 0.60 (home g1) and 0.45 (away g2) -> mean 0.525.
    assert bool(tor["market_available"]) is True
    assert tor["market_implied_win_prob"] == pytest.approx(0.525)

    no_odds = build_team_series_features(_team_games(), season_id=SEASON, as_of_date=ROUND1_START)
    tor_no = no_odds.loc[no_odds["team_abbrev"] == "TOR"].iloc[0]
    assert bool(tor_no["market_available"]) is False
    assert pd.isna(tor_no["market_implied_win_prob"])


def test_injury_starter_unavailability_flag() -> None:
    matrix = build_team_series_features(
        _team_games(), season_id=SEASON, as_of_date=ROUND1_START, injuries=_injuries()
    )
    bos = matrix.loc[matrix["team_abbrev"] == "BOS"].iloc[0]
    tor = matrix.loc[matrix["team_abbrev"] == "TOR"].iloc[0]
    assert bool(bos["starter_unavailability_risk"]) is True  # injured goalie
    assert bool(tor["starter_unavailability_risk"]) is False  # injured forward only
    assert bool(bos["goalie_injury_data_available"]) is True

    none = build_team_series_features(_team_games(), season_id=SEASON, as_of_date=ROUND1_START)
    assert bool(none.iloc[0]["goalie_injury_data_available"]) is False


def test_matchup_head_to_head_and_home_ice() -> None:
    matrix = build_team_series_features(
        _team_games(),
        season_id=SEASON,
        as_of_date=ROUND1_START,
        matchups=_matchups(),
    )
    tor = matrix.loc[matrix["team_abbrev"] == "TOR"].iloc[0]
    assert bool(tor["matchup_available"]) is True
    assert tor["opponent_team_abbrev"] == "BOS"
    assert tor["home_ice_advantage"] == 1.0
    # TOR beat BOS twice in four head-to-head games.
    assert tor["head_to_head_games"] == pytest.approx(4.0)
    assert tor["head_to_head_win_pct"] == pytest.approx(0.5)
    # Expected opponent strength is BOS's as-of Elo.
    assert tor["expected_opponent_strength"] == pytest.approx(
        matrix.loc[matrix["team_abbrev"] == "BOS", "elo_rating"].iloc[0]
    )
    assert bool(tor["series_market_available"]) is True
    assert tor["series_implied_win_prob"] == pytest.approx(0.58)


def test_matchup_absent_defaults() -> None:
    matrix = build_team_series_features(_team_games(), season_id=SEASON, as_of_date=ROUND1_START)
    tor = matrix.loc[matrix["team_abbrev"] == "TOR"].iloc[0]
    assert bool(tor["matchup_available"]) is False
    assert pd.isna(tor["opponent_team_abbrev"])
    assert tor["home_ice_advantage"] == 0.0
    assert bool(tor["series_market_available"]) is False


def test_build_round_matrix_stacks_rounds() -> None:
    stacked = build_round_team_series_matrix(
        _team_games(),
        season_id=SEASON,
        round_start_dates={1: ROUND1_START, 2: ROUND2_START},
    )
    assert set(stacked["playoff_round"]) == {1, 2}
    assert not stacked.empty


def test_empty_when_no_games_before_cutoff() -> None:
    matrix = build_team_series_features(_team_games(), season_id=SEASON, as_of_date="2023-09-01")
    assert matrix.empty
    assert list(matrix.columns) == list(TEAM_FEATURE_COLUMNS)


def test_no_nan_in_required_numeric_features() -> None:
    matrix = build_team_series_features(_team_games(), season_id=SEASON, as_of_date=ROUND1_START)
    required = [
        "goals_for_per_game",
        "goals_against_per_game",
        "goal_differential_per_game",
        "power_play_pct",
        "penalty_kill_pct",
        "starter_save_pct_season",
        "starter_save_pct_l15",
        "elo_rating",
        "rest_days",
        "days_between_games",
    ]
    for col in required:
        assert not matrix[col].map(lambda v: isinstance(v, float) and math.isnan(v)).any()
