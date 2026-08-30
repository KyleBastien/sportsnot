"""Leakage-safe Elo primitives shared by team outcome models.

The per-game win and series models maintain their own chronological team state,
but use one implementation of the Elo expectation, update, and between-season
regression rules.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "EloConfig",
    "expected_score",
    "regress_to_mean",
    "update_rating",
]


@dataclass(frozen=True)
class EloConfig:
    """Elo update knobs used by chronological team models.

    ``k`` is the per-game learning rate. ``home_advantage`` is added to the
    home team's rating before computing its expectation. ``initial`` is the
    rating for an unseen team. ``season_regression`` is the fraction of each
    team's deviation from ``initial`` removed at a season boundary.
    """

    k: float = 20.0
    home_advantage: float = 50.0
    initial: float = 1500.0
    season_regression: float = 0.25


def expected_score(rating_a: float, rating_b: float, home_advantage: float = 0.0) -> float:
    """Return Elo win expectation for team A, optionally including home ice."""
    return float(1.0 / (1.0 + 10.0 ** ((rating_b - (rating_a + home_advantage)) / 400.0)))


def update_rating(rating: float, expected: float, actual: float, k: float) -> float:
    """Return post-game rating ``rating + k * (actual - expected)``."""
    return float(rating) + float(k) * (float(actual) - float(expected))


def regress_to_mean(rating: float, mean: float, fraction: float) -> float:
    """Shrink a rating toward ``mean`` by ``fraction``."""
    return float(mean) + (float(rating) - float(mean)) * (1.0 - float(fraction))
