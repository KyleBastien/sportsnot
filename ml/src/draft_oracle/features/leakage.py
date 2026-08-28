"""As-of / leakage guards for feature engineering (SPEC §6).

A feature for playoff round ``N`` may use ONLY games played *before* round ``N``
started. Every feature builder funnels its game inputs through :func:`as_of`
(a strict, exclusive cutoff filter) and asserts the invariant with
:func:`assert_no_leakage`. A violation raises :class:`LeakageError`, which the
automated leakage test turns into a build failure.
"""

from __future__ import annotations

import pandas as pd

__all__ = ["LeakageError", "as_of", "assert_no_leakage", "to_cutoff"]


class LeakageError(ValueError):
    """Raised when a feature computation would use games on/after the cutoff.

    The cutoff is the round-start date; games played on the round-start date or
    later belong to the round being projected (or a future round) and must never
    feed an as-of feature.
    """


def to_cutoff(as_of_date: str | pd.Timestamp) -> pd.Timestamp:
    """Normalize a round-start date to a ``pd.Timestamp`` cutoff."""
    return pd.Timestamp(as_of_date)


def as_of(
    games: pd.DataFrame,
    as_of_date: str | pd.Timestamp,
    *,
    date_col: str = "game_date",
) -> pd.DataFrame:
    """Return only ``games`` played strictly before ``as_of_date``.

    The cutoff is exclusive: a game whose ``date_col`` equals ``as_of_date`` is
    dropped, because the round starts on that date. The returned frame is a copy
    with ``date_col`` coerced to ``datetime64``.
    """
    cutoff = to_cutoff(as_of_date)
    out = games.copy()
    out[date_col] = pd.to_datetime(out[date_col])
    kept = out.loc[out[date_col] < cutoff]
    return kept.copy()


def assert_no_leakage(
    games: pd.DataFrame,
    as_of_date: str | pd.Timestamp,
    *,
    date_col: str = "game_date",
) -> None:
    """Raise :class:`LeakageError` if any game is on/after ``as_of_date``.

    Called on the exact set of games a feature builder consumed, so a leaked
    future game fails the build instead of silently poisoning a projection.
    """
    cutoff = to_cutoff(as_of_date)
    dates = pd.to_datetime(games[date_col])
    violating = games.loc[dates >= cutoff]
    if not violating.empty:
        count = len(violating)
        latest = pd.to_datetime(violating[date_col]).max()
        raise LeakageError(
            f"{count} game(s) on/after cutoff {cutoff.date()} would leak into "
            f"an as-of feature (latest offending date {latest.date()})."
        )
