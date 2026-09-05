"""Tests for Elo primitives shared by live team outcome models."""

from __future__ import annotations

import pytest

import draft_oracle.features as features
from draft_oracle.features.elo import (
    EloConfig,
    expected_score,
    regress_to_mean,
    update_rating,
)


def test_expected_score_is_symmetric_without_home_ice() -> None:
    probability_a = expected_score(1600, 1400)
    probability_b = expected_score(1400, 1600)

    assert probability_a + probability_b == pytest.approx(1.0)
    assert expected_score(1500, 1500) == pytest.approx(0.5)


def test_expected_score_applies_home_advantage() -> None:
    assert expected_score(1500, 1500, home_advantage=50) > 0.5


def test_update_rating_is_zero_sum_for_two_team_result() -> None:
    home = update_rating(1500, expected=0.5, actual=1.0, k=20)
    away = update_rating(1500, expected=0.5, actual=0.0, k=20)

    assert home == pytest.approx(1510.0)
    assert away == pytest.approx(1490.0)
    assert home + away == pytest.approx(3000.0)


@pytest.mark.parametrize(
    ("fraction", "expected"),
    [(0.0, 1600.0), (0.25, 1575.0), (1.0, 1500.0)],
)
def test_regress_to_mean(fraction: float, expected: float) -> None:
    assert regress_to_mean(1600, 1500, fraction) == pytest.approx(expected)


def test_default_config_matches_model_contract() -> None:
    assert EloConfig() == EloConfig(
        k=20.0,
        home_advantage=50.0,
        initial=1500.0,
        season_regression=0.25,
    )


def test_dead_team_series_matrix_is_not_public_api() -> None:
    assert not hasattr(features, "build_team_series_features")
    assert not hasattr(features, "build_round_team_series_matrix")
