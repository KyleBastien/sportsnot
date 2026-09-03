"""Tests for draft_oracle.models.skater_production (US-014).

All fixtures are in-memory synthetic games -- no network, no committed-archive
dependency (SPEC section 7). The suite covers the scalar metrics (MAE, Spearman,
credibility shrinkage), playoff-round reconstruction (start dates + labels), the
leakage-free per-round dataset, position+team priors, cold-case handling, and an
end-to-end train that reports honest held-out metrics per season.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import pytest

from draft_oracle.models import (
    LABEL_COLUMN,
    PREDICTOR_COLUMNS,
    ProductionDatasetRequest,
    build_production_dataset,
    credibility_weight,
    fit_priors,
    mean_absolute_error,
    playoff_round_starts,
    shrink_to_prior,
    skater_round_production,
    spearman_correlation,
    train_skater_production_model,
)

TEAMS = ["AAA", "BBB", "CCC", "DDD"]
# Latent per-game scoring talent per team; skaters inherit their team's rate plus
# a per-player offset so within-team ranking is learnable.
TEAM_RATE = {"AAA": 0.9, "BBB": 0.6, "CCC": 0.4, "DDD": 0.2}


# ── Scalar metrics + shrinkage ─────────────────────────────────────────────


def test_mean_absolute_error_basic() -> None:
    assert mean_absolute_error([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == 0.0
    assert mean_absolute_error([1.0, 2.0], [2.0, 4.0]) == pytest.approx(1.5)


def test_mean_absolute_error_empty_is_nan() -> None:
    assert np.isnan(mean_absolute_error([], []))


def test_spearman_perfect_monotone_is_one() -> None:
    preds = [0.1, 0.2, 0.3, 0.4]
    actuals = [10.0, 20.0, 30.0, 40.0]
    assert spearman_correlation(preds, actuals) == pytest.approx(1.0)


def test_spearman_reverse_monotone_is_minus_one() -> None:
    preds = [0.1, 0.2, 0.3, 0.4]
    actuals = [40.0, 30.0, 20.0, 10.0]
    assert spearman_correlation(preds, actuals) == pytest.approx(-1.0)


def test_spearman_handles_ties_via_average_ranks() -> None:
    # Two tied predictions get the mean rank; correlation stays finite.
    value = spearman_correlation([1.0, 1.0, 2.0, 3.0], [5.0, 6.0, 7.0, 8.0])
    assert -1.0 <= value <= 1.0


def test_spearman_degenerate_is_nan() -> None:
    assert np.isnan(spearman_correlation([1.0], [1.0]))
    assert np.isnan(spearman_correlation([2.0, 2.0, 2.0], [1.0, 2.0, 3.0]))


def test_credibility_weight_bounds() -> None:
    assert credibility_weight(0, 10) == 0.0
    assert credibility_weight(10, 10) == pytest.approx(0.5)
    assert 0.0 < credibility_weight(90, 10) < 1.0
    assert credibility_weight(90, 10) == pytest.approx(0.9)


def test_shrink_to_prior_blends_by_sample_size() -> None:
    # No games -> pure prior; many games -> mostly the estimate.
    assert shrink_to_prior(1.0, 0.3, 0, 10) == pytest.approx(0.3)
    assert shrink_to_prior(1.0, 0.3, 10, 10) == pytest.approx(0.65)
    # With k=0 and at least one game the estimate is returned unchanged.
    assert shrink_to_prior(1.0, 0.3, 5, 0) == pytest.approx(1.0)


# ── Synthetic archive ──────────────────────────────────────────────────────


def _series_rows(seasons: list[int]) -> pd.DataFrame:
    """One first-round series per season: AAA (top seed) vs DDD (bottom)."""
    rows = [
        {
            "year": s // 10000 + 1,
            "season_id": s,
            "series_letter": "A",
            "series_abbrev": "A",
            "playoff_round": 1,
            "top_seed_team_id": 1,
            "top_seed_abbrev": "AAA",
            "top_seed_wins": 4,
            "bottom_seed_team_id": 4,
            "bottom_seed_abbrev": "DDD",
            "bottom_seed_wins": 2,
            "winning_team_id": 1,
            "losing_team_id": 4,
        }
        for s in seasons
    ]
    return pd.DataFrame(rows)


def _synthetic_archive(
    *, seasons: list[int], seed: int = 0, n_reg: int = 40
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Regular season (all teams) + a first-round AAA/DDD playoff, several seasons.

    Each of two skaters per team scores at ``team_rate + offset`` per game in the
    regular season and in the playoffs, so a model on the regular-season rate should
    track playoff production and rank skaters sensibly.
    """
    rng = np.random.default_rng(seed)
    sk_rows: list[dict[str, object]] = []
    tg_rows: list[dict[str, object]] = []
    player_rows: list[dict[str, object]] = []

    players: dict[int, tuple[str, float, str]] = {}
    pid = 100
    for team in TEAMS:
        for offset, pos in ((0.25, "F"), (-0.1, "D")):
            players[pid] = (team, TEAM_RATE[team] + offset, pos)
            player_rows.append(
                {
                    "player_id": pid,
                    "player_name": f"{team}-{pid}",
                    "last_name": f"L{pid}",
                    "birth_date": "1996-01-01",
                    "position_code": "C" if pos == "F" else "D",
                    "position": pos,
                    "shoots_catches": "L",
                    "height": 72,
                    "weight": 190,
                    "birth_country_code": "CAN",
                    "nationality_code": "CAN",
                    "draft_year": 2014,
                    "draft_round": 1,
                    "draft_overall": 5,
                    "current_team_abbrev": team,
                    "last_season_id": seasons[-1],
                }
            )
            pid += 1

    gid = 3_000_000
    for season_id in seasons:
        year = season_id // 10000
        # Regular season: a round-robin repeated to reach ~n_reg games per team.
        day = 1
        month = 11
        for _ in range(n_reg // (len(TEAMS) - 1)):
            for i, home in enumerate(TEAMS):
                for away in TEAMS[i + 1 :]:
                    gid += 1
                    date = f"{year}-{month:02d}-{day:02d}"
                    day += 1
                    if day > 27:
                        day = 1
                        month = 12 if month == 11 else 11
                    _emit_team_game(tg_rows, gid, date, season_id, 2, home, away)
                    for team, opp in ((home, away), (away, home)):
                        for p, (t, rate, _pos) in players.items():
                            if t != team:
                                continue
                            g, a = _draw_ga(rng, rate)
                            sk_rows.append(
                                _skater_row(
                                    _SkaterRowInput(
                                        p, players[p], gid, date, season_id, 2, team, opp, g, a
                                    )
                                )
                            )
        # First-round playoff: AAA vs DDD, six games.
        for gnum in range(6):
            gid += 1
            date = f"{year + 1}-04-{20 + gnum:02d}"
            home, away = ("AAA", "DDD") if gnum % 2 == 0 else ("DDD", "AAA")
            _emit_team_game(tg_rows, gid, date, season_id, 3, home, away)
            for team, opp in (("AAA", "DDD"), ("DDD", "AAA")):
                for p, (t, rate, _pos) in players.items():
                    if t != team:
                        continue
                    g, a = _draw_ga(rng, rate)
                    sk_rows.append(
                        _skater_row(
                            _SkaterRowInput(
                                p, players[p], gid, date, season_id, 3, team, opp, g, a
                            )
                        )
                    )

    skater_games = pd.DataFrame(sk_rows)
    team_games = pd.DataFrame(tg_rows)
    players_df = pd.DataFrame(player_rows)
    series = _series_rows(seasons)
    return skater_games, team_games, players_df, series


def _draw_ga(rng: np.random.Generator, rate: float) -> tuple[int, int]:
    return _draw_count(rng, rate), _draw_count(rng, rate)


def _draw_count(rng: np.random.Generator, rate: float) -> int:
    return int(rng.poisson(max(rate * 0.5, 0.01)))


@dataclass(frozen=True)
class _SkaterRowInput:
    player_id: int
    meta: tuple[str, float, str]
    game_id: int
    game_date: str
    season_id: int
    game_type_id: int
    team: str
    opp: str
    goals: int
    assists: int

def _skater_row(spec: _SkaterRowInput) -> dict[str, object]:
    _team, _rate, pos = spec.meta
    return {
        "season_id": spec.season_id,
        "game_type_id": spec.game_type_id,
        "game_id": spec.game_id,
        "game_date": spec.game_date,
        "player_id": spec.player_id,
        "player_name": f"{spec.team}-{spec.player_id}",
        "position_code": "C" if pos == "F" else "D",
        "position": pos,
        "shoots_catches": "L",
        "team_abbrev": spec.team,
        "opponent_team_abbrev": spec.opp,
        "home_road": "H",
        "goals": spec.goals,
        "assists": spec.assists,
        "points": spec.goals + spec.assists,
        "shots": spec.goals * 3 + 2,
        "toi_seconds": 1000,
        "pp_goals": 0,
        "pp_points": 0,
        "sh_goals": 0,
        "sh_points": 0,
        "ev_goals": spec.goals,
        "ev_points": spec.goals + spec.assists,
        "plus_minus": 0,
        "penalty_minutes": 0,
        "game_winning_goals": 0,
        "ot_goals": 0,
        "shooting_pct": 0.1,
        "faceoff_win_pct": 0.5,
    }


def _emit_team_game(
    rows: list[dict[str, object]],
    game_id: int,
    game_date: str,
    season_id: int,
    game_type_id: int,
    home: str,
    away: str,
) -> None:
    for team, opp, is_home in ((home, away, True), (away, home, False)):
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
                "goals_for": 3,
                "goals_against": 2,
                "wins": 1,
                "losses": 0,
                "ot_losses": 0,
                "regulation_and_ot_wins": 1,
                "wins_in_regulation": 1,
                "wins_in_shootout": 0,
                "points": 2,
                "shots_for": 30,
                "shots_against": 28,
                "faceoff_win_pct": 0.5,
                "power_play_pct": 0.2,
                "power_play_net_pct": 0.2,
                "penalty_kill_pct": 0.8,
                "penalty_kill_net_pct": 0.8,
                "team_shutouts": 0,
                "win": True,
                "shutout_win": False,
            }
        )


# ── Round reconstruction ───────────────────────────────────────────────────


def test_playoff_round_starts_uses_first_game_date() -> None:
    _sk, tg, _pl, series = _synthetic_archive(seasons=[20182019])
    starts = playoff_round_starts(tg, series)
    assert starts[20182019][1] == "2019-04-20"


def test_skater_round_production_computes_per_game_rate() -> None:
    sk, _tg, _pl, series = _synthetic_archive(seasons=[20182019], seed=3)
    labels = skater_round_production(sk, series)
    assert not labels.empty
    assert set(labels["playoff_round"].unique()) == {1}
    # Only AAA/DDD skaters played the modeled series.
    assert set(labels["player_id"]).issubset({100, 101, 106, 107})
    for rec in labels.to_dict("records"):
        assert rec["round_games"] == 6
        assert rec["actual_points_per_game"] == pytest.approx(
            (rec["round_goals"] + rec["round_assists"]) / rec["round_games"]
        )


def test_skater_round_production_ignores_unmapped_pairs() -> None:
    sk, _tg, _pl, series = _synthetic_archive(seasons=[20182019])
    # Drop the series row -> no game maps to a round -> empty labels.
    labels = skater_round_production(sk, series.iloc[0:0])
    assert labels.empty


def test_playoff_round_digit_reads_the_round_from_the_game_id() -> None:
    from draft_oracle.models.skater_production import _playoff_round_digit

    assert _playoff_round_digit("2019030091") == "0"  # 2020 qualifying / round-robin
    assert _playoff_round_digit("2021030111") == "1"
    assert _playoff_round_digit(2021030421) == "4"
    assert _playoff_round_digit("not-a-game") is None
    assert _playoff_round_digit("202103021") is None  # too short


def test_assign_rounds_excludes_2020_qualifying_and_round_robin() -> None:
    from draft_oracle.models.skater_production import _assign_rounds

    # A 2019-20 round-robin game (game_id round digit 0) between two teams that ALSO
    # meet in a real round-2 series must never inherit that series' round via the
    # team-pair map (CODE_REVIEW m-6).
    round_map = {(20192020, ("AAA", "BBB")): 2}
    games = pd.DataFrame(
        [
            {"game_id": "2019030091", "season_id": 20192020, "team_abbrev": "AAA",
             "opponent_team_abbrev": "BBB"},
            {"game_id": "2019030211", "season_id": 20192020, "team_abbrev": "AAA",
             "opponent_team_abbrev": "BBB"},
        ]
    )
    assert _assign_rounds(games, round_map) == [None, 2]


# ── Dataset build ──────────────────────────────────────────────────────────


def test_build_dataset_has_features_labels_and_no_leakage_columns() -> None:
    sk, tg, pl, series = _synthetic_archive(seasons=[20172018, 20182019], seed=5)
    data = build_production_dataset(ProductionDatasetRequest(sk, pl, tg, series))
    assert not data.empty
    assert LABEL_COLUMN in data.columns
    assert "season_end_year" in data.columns
    assert "is_defense" in data.columns
    for col in PREDICTOR_COLUMNS:
        if col == "is_defense":
            continue
        assert col in data.columns
    # As-of features use only regular-season games, so games_played is the reg count,
    # never inflated by the six playoff games of the round.
    assert (data["games_played"] <= 40).all()


# ── Priors + cold cases ────────────────────────────────────────────────────


def test_fit_priors_falls_back_specific_to_global() -> None:
    frame = pd.DataFrame(
        [
            {"position": "F", "team_abbrev": "AAA", LABEL_COLUMN: 1.0},
            {"position": "F", "team_abbrev": "AAA", LABEL_COLUMN: 0.6},
            {"position": "D", "team_abbrev": "BBB", LABEL_COLUMN: 0.2},
        ]
    )
    priors = fit_priors(frame)
    assert priors.prior_for("F", "AAA") == pytest.approx(0.8)
    # Unknown team -> position prior.
    assert priors.prior_for("F", "ZZZ") == pytest.approx(0.8)
    # Unknown position -> global mean.
    assert priors.prior_for("G", "ZZZ") == pytest.approx((1.0 + 0.6 + 0.2) / 3)


def test_project_cold_returns_prior_and_low_confidence() -> None:
    seasons = [20162017, 20172018, 20182019, 20192020, 20202021]
    sk, tg, pl, series = _synthetic_archive(seasons=seasons, seed=9)
    result = train_skater_production_model(sk, pl, tg, series)
    proj, low_conf = result.model.project_cold("F", "AAA")
    assert low_conf is True
    assert proj > 0.0
    # An unknown team still yields a finite, non-crashing projection.
    proj2, low2 = result.model.project_cold("D", "ZZZ")
    assert low2 is True
    assert np.isfinite(proj2)


def test_project_flags_low_confidence_and_blends() -> None:
    seasons = [20162017, 20172018, 20182019, 20192020, 20202021]
    sk, tg, pl, series = _synthetic_archive(seasons=seasons, seed=4)
    result = train_skater_production_model(sk, pl, tg, series)
    data = build_production_dataset(ProductionDatasetRequest(sk, pl, tg, series))
    projected = result.model.project(data)
    assert "projected_points_per_game" in projected.columns
    assert "low_confidence" in projected.columns
    assert (projected["projected_points_per_game"] >= 0.0).all()
    # Projection lies between the raw estimate and the prior (a convex blend).
    for rec in projected.to_dict("records"):
        raw = float(rec["raw_points_per_game"])
        prior = float(rec["prior_points_per_game"])
        proj = float(rec["projected_points_per_game"])
        assert min(raw, prior) - 1e-9 <= proj <= max(raw, prior) + 1e-9


# ── End-to-end train ───────────────────────────────────────────────────────


def test_train_reports_temporal_split_and_metrics() -> None:
    seasons = [20152016, 20162017, 20172018, 20182019, 20192020, 20202021]
    sk, tg, pl, series = _synthetic_archive(seasons=seasons, seed=7)
    result = train_skater_production_model(sk, pl, tg, series)
    assert result.chosen_model_type in {"poisson", "lightgbm"}
    # Two held-out seasons, one validation season by default.
    assert result.split.test_years == (2020, 2021)
    assert result.split.val_years == (2019,)
    assert len(result.per_season) == 2
    for m in result.per_season:
        assert m.n > 0
        assert np.isfinite(m.mae)
    assert np.isfinite(result.test_mae_model)
    assert np.isfinite(result.test_spearman_model)


def test_train_manifest_and_report_render() -> None:
    seasons = [20152016, 20162017, 20172018, 20182019, 20192020, 20202021]
    sk, tg, pl, series = _synthetic_archive(seasons=seasons, seed=2)
    result = train_skater_production_model(sk, pl, tg, series)
    manifest = result.manifest()
    assert manifest["model_version"] == "skater-production-v1"
    assert manifest["seed"] == result.config.seed
    assert manifest["split"]["test_years"] == [2020, 2021]
    assert "model" in manifest["test_mae"]
    assert len(manifest["per_season"]) == 2
    assert any("Skater per-game production model" in line for line in result.report_lines())
    # Cold-case count is reported (>= 0, non-crashing).
    assert result.n_cold_cases_test >= 0


def test_train_beats_mean_baseline_on_signal() -> None:
    # With a clear team/player rate signal the model should at least track the
    # actuals better than predicting a constant mean (MAE).
    seasons = [20152016, 20162017, 20172018, 20182019, 20192020, 20202021]
    sk, tg, pl, series = _synthetic_archive(seasons=seasons, seed=1, n_reg=60)
    result = train_skater_production_model(sk, pl, tg, series)
    assert result.test_mae_model <= result.test_mae_baseline_mean + 1e-9
