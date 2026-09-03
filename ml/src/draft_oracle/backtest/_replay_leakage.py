"""Leakage guards for backtest replay inputs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import pandas as pd

from draft_oracle.features.leakage import LeakageError, assert_no_leakage
from draft_oracle.models.skater_production import (
    PLAYOFF_GAME_TYPE,
    _assign_rounds,
    _series_round_map,
)


@dataclass(frozen=True)
class RoundLeakageCheck:
    games: pd.DataFrame
    round_ids: set[int]
    cutoff: str | pd.Timestamp
    date_col: str = "game_date"
    label: str = "games"
    authoritative_dates: pd.DataFrame | Mapping[int, Any] | None = None


def round_game_ids(
    team_games: pd.DataFrame, series: pd.DataFrame, *, season_id: int, playoff_round: int
) -> set[int]:
    """The ``game_id`` set of ``season_id``'s round ``playoff_round`` playoff games."""
    po = team_games.loc[
        (team_games["game_type_id"] == PLAYOFF_GAME_TYPE)
        & (team_games["season_id"].astype(int) == int(season_id))
    ].copy()
    if po.empty:
        return set()
    po["playoff_round"] = _assign_rounds(po, _series_round_map(series))
    po = po.loc[po["playoff_round"] == playoff_round]
    return {int(gid) for gid in po["game_id"].unique()}


def assert_round_inputs_leakfree(check: RoundLeakageCheck) -> None:
    """Fail loudly if the as-of inputs for a round contain that round's data."""
    cutoff_ts = pd.Timestamp(check.cutoff)
    frame = check.games.copy()
    frame[check.date_col] = pd.to_datetime(frame[check.date_col])
    train = frame.loc[frame[check.date_col] < cutoff_ts]
    _assert_authoritative_dates_leakfree(
        train,
        check.authoritative_dates,
        cutoff_ts,
        date_col=check.date_col,
        label=check.label,
    )
    assert_no_leakage(train, cutoff_ts, date_col=check.date_col)
    _assert_round_ids_absent(train, check.round_ids, cutoff_ts, label=check.label)


def _assert_authoritative_dates_leakfree(
    train: pd.DataFrame,
    authoritative_dates: pd.DataFrame | Mapping[int, Any] | None,
    cutoff_ts: pd.Timestamp,
    *,
    date_col: str,
    label: str,
) -> None:
    if authoritative_dates is None or "game_id" not in train.columns:
        return
    auth = _authoritative_date_map(authoritative_dates, date_col=date_col)
    true_dates = train["game_id"].map(auth)
    desynced = train.loc[true_dates.notna() & (true_dates >= cutoff_ts)]
    if desynced.empty:
        return
    latest = true_dates.loc[desynced.index].max()
    raise LeakageError(
        f"{len(desynced)} {label} row(s) desynced past cutoff {cutoff_ts.date()}: "
        f"their own date is pre-cutoff but the authoritative game date is on/after "
        f"it (latest authoritative date {pd.Timestamp(latest).date()})."
    )


def _assert_round_ids_absent(
    train: pd.DataFrame, round_ids: set[int], cutoff_ts: pd.Timestamp, *, label: str
) -> None:
    if "game_id" not in train.columns or not round_ids:
        return
    leaked = {int(gid) for gid in train["game_id"].unique()} & round_ids
    if not leaked:
        return
    raise LeakageError(
        f"{len(leaked)} round game(s) leaked into the as-of {label} inputs "
        f"before cutoff {cutoff_ts.date()} (e.g. game_id {sorted(leaked)[:3]})."
    )


def _authoritative_date_map(
    source: pd.DataFrame | Mapping[int, Any], *, date_col: str = "game_date"
) -> dict[int, pd.Timestamp]:
    """Build a ``game_id -> authoritative game date`` map from a frame or mapping."""
    if isinstance(source, pd.DataFrame):
        pairs = source[["game_id", date_col]].drop_duplicates(subset=["game_id"])
        return {
            int(gid): pd.Timestamp(dt)
            for gid, dt in zip(pairs["game_id"], pd.to_datetime(pairs[date_col]), strict=True)
        }
    return {int(gid): pd.Timestamp(dt) for gid, dt in source.items()}
