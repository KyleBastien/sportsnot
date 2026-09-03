"""Tests for draft_oracle.models.shutout (US-012).

Most fixtures are in-memory synthetic games. Focused shootout regressions read the
committed NHL archive; no network is used (SPEC section 7). The suite covers the
base-rate baseline, the leakage-free running goaltending state, the feature row +
missing flags, the winner-framed dataset build, probability bounds, monotonicity in
goalie quality, and an end-to-end train that beats the base-rate baseline on a
held-out season.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from draft_oracle.ingest.normalize import normalize_team_games
from draft_oracle.models import (
    NEUTRAL_SAVE_PCT,
    SHUTOUT_FEATURE_COLUMNS,
    ShutoutConfig,
    ShutoutFeatureContext,
    ShutoutTeamState,
    base_rate_probs,
    build_shutout_dataset,
    shutout_feature_row,
    train_shutout_model,
)
from draft_oracle.models.shutout import _pivot_games

TEAMS = ["AAA", "BBB", "CCC", "DDD"]
# Latent win strength (who wins) and defence quality (how often the winner
# records a shutout). Strong defence -> more shutouts + higher save %.
STRENGTH = {"AAA": 3.0, "BBB": 1.0, "CCC": -1.0, "DDD": -3.0}
DEFENCE = {"AAA": 0.85, "BBB": 0.6, "CCC": 0.3, "DDD": 0.1}
SHOTS = 30


@dataclass(frozen=True)
class _GameRowsInput:
    game_id: int
    game_date: str
    season_id: int
    game_type_id: int
    home: str
    away: str
    home_goals: int
    away_goals: int


@dataclass(frozen=True)
class _RegularGameInput:
    season_id: int
    gid: int
    day: int
    home: str
    away: str


@dataclass(frozen=True)
class _TeamRowInput:
    game: _GameRowsInput
    team: str
    gf: int
    ga: int
    is_home: bool


def _team_row(spec: _TeamRowInput) -> dict[str, object]:
    won = spec.gf > spec.ga
    return {
        "season_id": spec.game.season_id,
        "game_type_id": spec.game.game_type_id,
        "game_id": spec.game.game_id,
        "game_date": spec.game.game_date,
        "team_id": TEAMS.index(spec.team) + 1,
        "team_abbrev": spec.team,
        "home_road": "H" if spec.is_home else "R",
        "goals_for": spec.gf,
        "goals_against": spec.ga,
        "shots_against": SHOTS,
        "points": 2 if won else 0,
        "win": won,
        "shutout_win": won and spec.ga == 0,
    }


def _game_rows(game: _GameRowsInput) -> list[dict[str, object]]:
    """Two archive-shaped rows (home + away) for one decided game."""

    return [
        _team_row(_TeamRowInput(game, game.home, game.home_goals, game.away_goals, True)),
        _team_row(_TeamRowInput(game, game.away, game.away_goals, game.home_goals, False)),
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
        regular_rows, gid = _regular_season_rows(season_id, gid, rng)
        rows.extend(regular_rows)
        playoff_rows, gid = _playoff_rows(season_id, gid)
        rows.extend(playoff_rows)
    return pd.DataFrame(rows)


def _regular_season_rows(
    season_id: int,
    starting_gid: int,
    rng: np.random.Generator,
) -> tuple[list[dict[str, object]], int]:
    rows: list[dict[str, object]] = []
    gid = starting_gid
    day = 1
    for _ in range(4):
        for home, away in _regular_matchups():
            gid += 1
            rows.extend(
                _regular_game_rows(_RegularGameInput(season_id, gid, day, home, away), rng)
            )
            day = day + 1 if day < 28 else 1
    return rows, gid


def _regular_matchups() -> list[tuple[str, str]]:
    return [(home, away) for i, home in enumerate(TEAMS) for away in TEAMS[i + 1 :]]


def _regular_game_rows(
    game: _RegularGameInput,
    rng: np.random.Generator,
) -> list[dict[str, object]]:
    p_home = 1.0 / (1.0 + np.exp(-(STRENGTH[game.home] - STRENGTH[game.away] + 0.4)))
    home_win = bool(rng.random() < p_home)
    winner = game.home if home_win else game.away
    shutout = bool(rng.random() < DEFENCE[winner])
    loser_goals = 0 if shutout else 2
    hg, ag = _goals_for_result(home_win, loser_goals)
    date = f"{game.season_id // 10000}-11-{game.day:02d}"
    return _game_rows(
        _GameRowsInput(game.gid, date, game.season_id, 2, game.home, game.away, hg, ag)
    )


def _goals_for_result(home_win: bool, loser_goals: int) -> tuple[int, int]:
    if home_win:
        return 3, loser_goals
    return loser_goals, 3


def _playoff_rows(season_id: int, starting_gid: int) -> tuple[list[dict[str, object]], int]:
    gid = starting_gid + 1
    date = f"{season_id // 10000 + 1}-04-20"
    return _game_rows(_GameRowsInput(gid, date, season_id, 3, "AAA", "DDD", 3, 0)), gid


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
        context=ShutoutFeatureContext(
            backup_save_pct=0.88,
            starter_unavailability_risk=1.0,
            goalie_injury_data_available=True,
        ),
    )
    assert row["backup_save_pct"] == pytest.approx(0.88)
    assert row["goalie_split_available"] == 1.0
    assert row["starter_unavailability_risk"] == 1.0
    assert row["goalie_injury_data_available"] == 1.0


# ── Dataset build (leakage-free, winner-framed) ────────────────────────────


def _real_team_games(season_label: str | None = None) -> pd.DataFrame:
    archive_dir = Path("data/raw/nhl-archive")
    paths = (
        [archive_dir / f"team-games-{season_label}.csv.gz"]
        if season_label is not None
        else sorted(archive_dir.glob("team-games-*.csv.gz"))
    )
    return pd.concat(
        [normalize_team_games(pd.read_csv(path)) for path in paths],
        ignore_index=True,
    )


def test_pivot_games_matches_all_real_archive_decisions() -> None:
    team_games = _real_team_games()
    archive_winners = team_games.groupby("game_id")["win"].sum()

    assert int(archive_winners.eq(1).sum()) == 14_508
    assert len(_pivot_games(team_games)) == 14_508


def test_pivot_games_retains_real_shootout_winner() -> None:
    team_games = _real_team_games("2020-21")
    game = _pivot_games(team_games).loc[lambda frame: frame["game_id"] == 2020020007]

    assert len(game) == 1
    assert game.iloc[0]["home_goals"] == game.iloc[0]["away_goals"] == 2
    assert game.iloc[0]["home_abbrev"] == "NJD"
    assert game.iloc[0]["away_abbrev"] == "BOS"
    assert game.iloc[0]["home_win"] == 0


def test_build_dataset_counts_zero_zero_shootout_wins_as_shutouts() -> None:
    team_games = _real_team_games()
    games = _pivot_games(team_games)
    zero_zero_ids = (
        games
        .loc[lambda frame: frame["home_goals"].eq(0) & frame["away_goals"].eq(0), "game_id"]
        .astype(int)
    )
    dataset = build_shutout_dataset(team_games, min_pregame_games=0)
    zero_zero_shutouts = dataset.loc[
        dataset["game_id"].astype(int).isin(zero_zero_ids), "is_shutout"
    ]

    assert len(zero_zero_ids) == 16
    assert len(zero_zero_shutouts) == 16
    assert zero_zero_shutouts.eq(1.0).all()
    assert 2016020785 in dataset["game_id"].astype(int).to_numpy()
    example = games.loc[games["game_id"] == 2016020785].iloc[0]
    assert example["home_abbrev"] == "MTL"
    assert example["away_abbrev"] == "EDM"
    assert example["home_win"] == 0


def test_pivot_games_warns_and_excludes_game_without_winner() -> None:
    team_games = pd.DataFrame(
        _game_rows(_GameRowsInput(1, "2021-01-01", 20202021, 2, "AAA", "BBB", 2, 2))
    )

    with pytest.warns(RuntimeWarning, match="without exactly one archive winner"):
        games = _pivot_games(team_games)

    assert games.empty


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


# ── Base-rate shrinkage (US-105) ───────────────────────────────────────────


def test_apply_shrinkage_blends_toward_base_rate() -> None:
    from draft_oracle.models.shutout import _apply_shrinkage

    probs = np.array([0.0, 0.2, 0.8, 1.0])
    # w=1.0 is a no-op (pure model).
    assert np.allclose(_apply_shrinkage(probs, weight=1.0, base_rate=0.1), probs)
    # w=0.0 collapses entirely onto the base rate.
    assert np.allclose(
        _apply_shrinkage(probs, weight=0.0, base_rate=0.1), np.full_like(probs, 0.1)
    )
    # w=0.5 lands halfway between model and base rate; result stays in [0, 1].
    half = _apply_shrinkage(probs, weight=0.5, base_rate=0.1)
    assert np.allclose(half, 0.5 * probs + 0.5 * 0.1)
    assert np.all(half >= 0.0) and np.all(half <= 1.0)


def test_select_shrinkage_prefers_base_rate_for_a_skill_less_model() -> None:
    from draft_oracle.models.shutout import _select_shrinkage_weight

    rng = np.random.default_rng(0)
    labels = (rng.random(4000) < 0.1).astype(float)
    # A "model" that is pure noise around the base rate carries no skill, so the
    # validation sweep should pull it toward the base rate (weight below 1.0).
    noisy = np.clip(0.1 + rng.normal(0.0, 0.25, size=labels.size), 0.0, 1.0)
    weight, by_weight = _select_shrinkage_weight(
        noisy, labels, base_rate=0.1, grid=(1.0, 0.5, 0.0)
    )
    assert weight < 1.0
    assert set(by_weight) == {"1.00", "0.50", "0.00"}


def test_shutout_model_applies_shrinkage_in_predictions() -> None:
    seasons = [20182019, 20192020, 20202021, 20212022, 20222023]
    team_games = _synthetic_team_games(seasons=seasons, seed=7)
    result = train_shutout_model(team_games, config=ShutoutConfig(seed=7, min_pregame_games=0))
    dataset = build_shutout_dataset(team_games, min_pregame_games=0)
    # Force a shrunk copy of the fitted model and confirm predictions move toward
    # the base rate relative to the pure-model estimator.
    from draft_oracle.models.shutout import ShutoutModel, _apply_shrinkage

    pure = ShutoutModel(
        estimator=result.model.estimator,
        feature_columns=result.model.feature_columns,
        model_type=result.model.model_type,
    )
    shrunk = ShutoutModel(
        estimator=result.model.estimator,
        feature_columns=result.model.feature_columns,
        model_type=result.model.model_type,
        shrinkage_weight=0.5,
        base_rate=0.1,
    )
    pure_probs = pure.predict_shutout_prob(dataset)
    shrunk_probs = shrunk.predict_shutout_prob(dataset)
    assert np.allclose(shrunk_probs, _apply_shrinkage(pure_probs, weight=0.5, base_rate=0.1))
    assert np.all(shrunk_probs >= 0.0) and np.all(shrunk_probs <= 1.0)


def test_manifest_records_shrinkage_decision() -> None:
    seasons = [20182019, 20192020, 20202021, 20212022, 20222023]
    team_games = _synthetic_team_games(seasons=seasons, seed=3)
    result = train_shutout_model(team_games, config=ShutoutConfig(seed=3, min_pregame_games=0))
    manifest = result.manifest()
    shrink = manifest["shrinkage"]
    assert 0.0 <= shrink["weight"] <= 1.0
    assert shrink["adopted"] == (shrink["weight"] < 1.0)
    assert shrink["validation_brier_by_weight"]
    assert np.isfinite(manifest["test_brier"]["model_unshrunk"])
    # The decision is spelled out in the human-readable report either way.
    assert any("Base-rate shrinkage" in line for line in result.report_lines())
