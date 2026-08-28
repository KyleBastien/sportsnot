"""Tests for draft_oracle.features (US-009).

All fixtures are built in-memory — no network, no committed archive dependency
(SPEC §7). The suite covers each scalar feature primitive, the frame-level
builder, and the mandatory leakage guard.
"""

from __future__ import annotations

import math
from pathlib import Path

import pandas as pd
import pytest

from draft_oracle.features import (
    FEATURE_COLUMNS,
    FEATURE_SET_VERSION,
    LeakageError,
    SkaterFeatureConfig,
    age_years,
    as_of,
    assert_no_leakage,
    build_round_feature_matrix,
    build_skater_features,
    linemate_ppg,
    per_game,
    pp_point_share,
    safe_ratio,
    shooting_pct,
    write_feature_matrix,
)

SEASON = 20232024
ROUND1_START = "2024-04-20"
ROUND2_START = "2024-05-05"


def _skater_row(
    *,
    game_id: int,
    game_date: str,
    player_id: int,
    team: str,
    goals: int,
    assists: int,
    shots: int,
    pp_points: int,
    toi: int,
    game_type: int = 2,
) -> dict[str, object]:
    return {
        "season_id": SEASON,
        "game_type_id": game_type,
        "game_id": game_id,
        "game_date": game_date,
        "player_id": player_id,
        "team_abbrev": team,
        "goals": goals,
        "assists": assists,
        "shots": shots,
        "pp_points": pp_points,
        "toi_seconds": toi,
    }


def _skater_games() -> pd.DataFrame:
    rows = [
        # Alice (100, F, TOR): 3 reg games — 6G / 3A / 20 shots / 4 PP pts.
        _skater_row(
            game_id=1,
            game_date="2024-01-05",
            player_id=100,
            team="TOR",
            goals=2,
            assists=1,
            shots=7,
            pp_points=2,
            toi=1200,
        ),
        _skater_row(
            game_id=2,
            game_date="2024-02-10",
            player_id=100,
            team="TOR",
            goals=2,
            assists=1,
            shots=6,
            pp_points=1,
            toi=1200,
        ),
        _skater_row(
            game_id=3,
            game_date="2024-03-15",
            player_id=100,
            team="TOR",
            goals=2,
            assists=1,
            shots=7,
            pp_points=1,
            toi=1200,
        ),
        # Bob (200, D, TOR): 2 reg games — 1G / 1A / 5 shots / 0 PP pts.
        _skater_row(
            game_id=1,
            game_date="2024-01-05",
            player_id=200,
            team="TOR",
            goals=1,
            assists=0,
            shots=3,
            pp_points=0,
            toi=1500,
        ),
        _skater_row(
            game_id=2,
            game_date="2024-02-10",
            player_id=200,
            team="TOR",
            goals=0,
            assists=1,
            shots=2,
            pp_points=0,
            toi=1500,
        ),
        # Gordie (300, goalie/None): must be dropped from the skater pool.
        _skater_row(
            game_id=1,
            game_date="2024-01-05",
            player_id=300,
            team="TOR",
            goals=0,
            assists=0,
            shots=0,
            pp_points=0,
            toi=3600,
        ),
    ]
    return pd.DataFrame(rows)


def _players() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"player_id": 100, "player_name": "Alice", "position": "F", "birth_date": "1998-04-20"},
            {"player_id": 200, "player_name": "Bob", "position": "D", "birth_date": "1995-01-01"},
            {
                "player_id": 300,
                "player_name": "Gordie",
                "position": None,
                "birth_date": "1990-01-01",
            },
        ]
    )


def _team_games() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "season_id": SEASON,
                "game_type_id": 2,
                "game_id": 1,
                "game_date": "2024-01-05",
                "team_abbrev": "TOR",
                "goals_for": 4,
            },
            {
                "season_id": SEASON,
                "game_type_id": 2,
                "game_id": 2,
                "game_date": "2024-02-10",
                "team_abbrev": "TOR",
                "goals_for": 2,
            },
            {
                "season_id": SEASON,
                "game_type_id": 2,
                "game_id": 3,
                "game_date": "2024-03-15",
                "team_abbrev": "TOR",
                "goals_for": 3,
            },
        ]
    )


# ── Scalar primitives ────────────────────────────────────────────────────


def test_safe_ratio_guards_zero_denominator() -> None:
    assert safe_ratio(5, 2) == 2.5
    assert safe_ratio(5, 0) == 0.0


def test_per_game_and_shooting_pct() -> None:
    assert per_game(6, 3) == 2.0
    assert shooting_pct(6, 20) == pytest.approx(0.3)
    assert shooting_pct(3, 0) == 0.0


def test_pp_point_share_range() -> None:
    assert pp_point_share(4, 9) == pytest.approx(4 / 9)
    assert pp_point_share(0, 0) == 0.0


def test_age_years_and_missing_birth_date() -> None:
    age = age_years("1998-04-20", "2024-04-20")
    assert age == pytest.approx(26.0, abs=0.05)
    assert age_years(None, "2024-04-20") == 0.0
    assert age_years(float("nan"), "2024-04-20") == 0.0


def test_linemate_ppg_leave_one_out() -> None:
    assert linemate_ppg([3.0, 1.0], 0) == 1.0
    assert linemate_ppg([3.0, 1.0], 1) == 3.0
    # Single-member team falls back to the player's own PPG.
    assert linemate_ppg([2.5], 0) == 2.5
    assert linemate_ppg([], 0) == 0.0


# ── Leakage guard ────────────────────────────────────────────────────────


def test_as_of_excludes_cutoff_date_games() -> None:
    games = _skater_games()
    games = pd.concat(
        [
            games,
            pd.DataFrame(
                [
                    _skater_row(
                        game_id=9,
                        game_date=ROUND1_START,
                        player_id=100,
                        team="TOR",
                        goals=100,
                        assists=0,
                        shots=1,
                        pp_points=0,
                        toi=1200,
                    ),
                ]
            ),
        ],
        ignore_index=True,
    )
    kept = as_of(games, ROUND1_START)
    assert (kept["game_date"] < pd.Timestamp(ROUND1_START)).all()
    assert 9 not in kept["game_id"].tolist()


def test_assert_no_leakage_raises_on_future_game() -> None:
    leaked = pd.DataFrame(
        [
            _skater_row(
                game_id=9,
                game_date="2024-04-22",
                player_id=100,
                team="TOR",
                goals=5,
                assists=0,
                shots=1,
                pp_points=0,
                toi=1200,
            ),
        ]
    )
    with pytest.raises(LeakageError):
        assert_no_leakage(leaked, ROUND1_START)


def test_build_ignores_games_on_or_after_cutoff() -> None:
    """A future high-scoring game must not inflate as-of rates."""
    base = _skater_games()
    leaked = pd.concat(
        [
            base,
            pd.DataFrame(
                [
                    _skater_row(
                        game_id=9,
                        game_date=ROUND1_START,
                        player_id=100,
                        team="TOR",
                        goals=100,
                        assists=0,
                        shots=1,
                        pp_points=0,
                        toi=1200,
                    ),
                ]
            ),
        ],
        ignore_index=True,
    )
    clean = build_skater_features(
        base, _players(), _team_games(), season_id=SEASON, as_of_date=ROUND1_START
    )
    with_leak = build_skater_features(
        leaked, _players(), _team_games(), season_id=SEASON, as_of_date=ROUND1_START
    )
    alice_clean = clean.loc[clean["player_id"] == 100, "goals_per_game"].iloc[0]
    alice_leak = with_leak.loc[with_leak["player_id"] == 100, "goals_per_game"].iloc[0]
    assert alice_clean == alice_leak == 2.0


# ── Frame-level builder ──────────────────────────────────────────────────


def test_build_skater_features_values() -> None:
    matrix = build_skater_features(
        _skater_games(),
        _players(),
        _team_games(),
        season_id=SEASON,
        as_of_date=ROUND1_START,
        playoff_round=1,
    )
    assert list(matrix.columns) == list(FEATURE_COLUMNS)
    # Goalie dropped; only F/D remain.
    assert set(matrix["player_id"]) == {100, 200}

    alice = matrix.loc[matrix["player_id"] == 100].iloc[0]
    assert alice["goals_per_game"] == 2.0
    assert alice["assists_per_game"] == 1.0
    assert alice["points_per_game"] == 3.0
    assert alice["shots_per_game"] == pytest.approx(20 / 3)
    assert alice["shooting_pct"] == pytest.approx(6 / 20)
    assert alice["pp_points_per_game"] == pytest.approx(4 / 3)
    assert alice["pp_point_share"] == pytest.approx(4 / 9)
    assert alice["avg_toi_seconds"] == pytest.approx(1200.0)
    assert alice["team_goals_for_per_game"] == pytest.approx(3.0)
    assert alice["linemate_ppg"] == pytest.approx(1.0)  # Bob's PPG
    assert alice["position"] == "F"
    assert alice["playoff_round"] == 1
    assert alice["as_of_date"] == ROUND1_START

    bob = matrix.loc[matrix["player_id"] == 200].iloc[0]
    assert bob["linemate_ppg"] == pytest.approx(3.0)  # Alice's PPG


def test_min_games_filter_drops_thin_samples() -> None:
    cfg = SkaterFeatureConfig(min_games=3)
    matrix = build_skater_features(
        _skater_games(),
        _players(),
        _team_games(),
        season_id=SEASON,
        as_of_date=ROUND1_START,
        config=cfg,
    )
    # Bob has only 2 reg games; dropped. Alice has 3; kept.
    assert set(matrix["player_id"]) == {100}


def test_last_n_window_reflects_prior_playoff_games() -> None:
    games = pd.concat(
        [
            _skater_games(),
            pd.DataFrame(
                [
                    _skater_row(
                        game_id=50,
                        game_date="2024-04-22",
                        player_id=100,
                        team="TOR",
                        goals=0,
                        assists=0,
                        shots=1,
                        pp_points=0,
                        toi=1200,
                        game_type=3,
                    ),
                ]
            ),
        ],
        ignore_index=True,
    )
    stacked = build_round_feature_matrix(
        games,
        _players(),
        _team_games(),
        season_id=SEASON,
        round_start_dates={1: ROUND1_START, 2: ROUND2_START},
    )
    r1 = stacked.loc[(stacked["player_id"] == 100) & (stacked["playoff_round"] == 1)].iloc[0]
    r2 = stacked.loc[(stacked["player_id"] == 100) & (stacked["playoff_round"] == 2)].iloc[0]
    # Regular-season rate is stable across rounds (playoff game excluded).
    assert r1["points_per_game"] == r2["points_per_game"] == 3.0
    # The round-1 playoff shutout drags the round-2 last-N points/game down.
    assert r2["points_per_game_l25"] < r1["points_per_game_l25"]


def test_build_round_feature_matrix_stacks_rounds() -> None:
    stacked = build_round_feature_matrix(
        _skater_games(),
        _players(),
        _team_games(),
        season_id=SEASON,
        round_start_dates={1: ROUND1_START, 2: ROUND2_START},
    )
    assert set(stacked["playoff_round"]) == {1, 2}
    assert not stacked.empty


def test_empty_when_no_games_before_cutoff() -> None:
    matrix = build_skater_features(
        _skater_games(),
        _players(),
        _team_games(),
        season_id=SEASON,
        as_of_date="2023-12-01",
    )
    assert matrix.empty
    assert list(matrix.columns) == list(FEATURE_COLUMNS)


def test_write_feature_matrix_roundtrip(tmp_path: Path) -> None:
    matrix = build_skater_features(
        _skater_games(),
        _players(),
        _team_games(),
        season_id=SEASON,
        as_of_date=ROUND1_START,
        playoff_round=1,
    )
    path = write_feature_matrix(matrix, features_dir=tmp_path)
    assert path == tmp_path / FEATURE_SET_VERSION / "skater_features.parquet"
    assert path.exists()
    roundtrip = pd.read_parquet(path)
    assert list(roundtrip.columns) == list(FEATURE_COLUMNS)
    assert len(roundtrip) == len(matrix)


def test_no_nan_in_output_features() -> None:
    matrix = build_skater_features(
        _skater_games(),
        _players(),
        _team_games(),
        season_id=SEASON,
        as_of_date=ROUND1_START,
    )
    numeric = matrix.select_dtypes(include="number")
    assert not numeric.map(lambda v: isinstance(v, float) and math.isnan(v)).to_numpy().any()
