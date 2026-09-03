"""Odds-source consolidation and NHL archive alignment helpers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, cast

import pandas as pd


@dataclass
class _ConsolidationStats:
    xval_flagged_rows: int = 0
    unmatched_uncovered_rows: int = 0
    orientation_unmatched_rows: int = 0


@dataclass(frozen=True)
class _ConsolidationContext:
    buckets: Mapping[tuple[int, int, int], list[dict[str, Any]]]
    columns: list[str]
    local_game_dates: Mapping[tuple[int, int, int], tuple[date, ...]] | None
    local_game_types: Mapping[tuple[int, int, int], Mapping[date, int]] | None
    stats: _ConsolidationStats


@dataclass(frozen=True)
class _GameTypeLookup:
    season_end_year: int
    home_id: int
    away_id: int
    game_date: date


def consolidate_odds(
    source_odds: pd.DataFrame,
    local_game_dates: Mapping[tuple[int, int, int], tuple[date, ...]] | None = None,
    local_game_types: Mapping[tuple[int, int, int], Mapping[date, int]] | None = None,
) -> pd.DataFrame:
    """Collapse the per-source table to one best row per game."""
    from draft_oracle.ingest.odds import _ODDS_COLUMNS

    keep = [*list(_ODDS_COLUMNS), "xval_delta", "source_count"]
    if source_odds.empty:
        return _empty_consolidated_odds(keep)

    records = _prepare_records(source_odds)
    buckets = _bucket_records(records)
    stats = _ConsolidationStats()
    context = _ConsolidationContext(
        buckets=buckets,
        columns=keep,
        local_game_dates=local_game_dates,
        local_game_types=local_game_types,
        stats=stats,
    )
    out_rows: list[dict[str, Any]] = []
    for anchor in _consolidation_order(records):
        if anchor["_used"] or _has_missing_team_ids(anchor):
            continue
        out_rows.append(_consolidated_anchor_row(anchor, context))

    out = pd.DataFrame.from_records(out_rows, columns=keep)
    out = out.sort_values(["season_end_year", "game_date", "game_key"], kind="stable")
    out = out.reset_index(drop=True)
    _attach_stats(out, stats)
    return out


def _consolidated_anchor_row(
    anchor: dict[str, Any],
    context: _ConsolidationContext,
) -> dict[str, Any]:
    from draft_oracle.ingest.odds import XVAL_DELTA_THRESHOLD

    members = _claim_cluster_members(anchor, context.buckets)
    best = _best_cluster_row(anchor, members, context.columns)
    _blank_if_archive_unmatched(
        best, context.local_game_dates, context.local_game_types, context.stats
    )
    if bool(best["covered"]) and best["xval_delta"] > XVAL_DELTA_THRESHOLD:
        from draft_oracle.ingest.odds import _blank_market_fields

        _blank_market_fields(best)
        context.stats.xval_flagged_rows += 1
    return best


def _empty_consolidated_odds(columns: list[str]) -> pd.DataFrame:
    out = pd.DataFrame(columns=columns)
    _attach_stats(out, _ConsolidationStats())
    return out


def _attach_stats(out: pd.DataFrame, stats: _ConsolidationStats) -> None:
    out.attrs["xval_flagged_rows"] = stats.xval_flagged_rows
    out.attrs["unmatched_uncovered_rows"] = stats.unmatched_uncovered_rows
    out.attrs["orientation_unmatched_rows"] = stats.orientation_unmatched_rows


def _prepare_records(source_odds: pd.DataFrame) -> list[dict[str, Any]]:
    from draft_oracle.ingest.odds import _SOURCE_PRIORITY

    raw_records = source_odds.to_dict("records")
    records: list[dict[str, Any]] = [cast("dict[str, Any]", r) for r in raw_records]
    for i, rec in enumerate(records):
        rec["_priority"] = _SOURCE_PRIORITY.get(str(rec["source"]), 0)
        rec["_date"] = _parse_date_str(str(rec["game_date"]))
        rec["_pos"] = i
        rec["_used"] = False
        rec["_home_prob"] = rec.get("home_implied")
    return records


def _bucket_records(
    records: list[dict[str, Any]],
) -> dict[tuple[int, int, int], list[dict[str, Any]]]:
    buckets: dict[tuple[int, int, int], list[dict[str, Any]]] = {}
    for rec in records:
        if _has_missing_team_ids(rec):
            continue
        buckets.setdefault(_record_key(rec), []).append(rec)
    return buckets


def _consolidation_order(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        records,
        key=lambda r: (-int(r["_priority"]), not bool(r["covered"]), r["_pos"]),
    )


def _claim_cluster_members(
    anchor: dict[str, Any], buckets: Mapping[tuple[int, int, int], list[dict[str, Any]]]
) -> list[dict[str, Any]]:
    members = _cluster_members(anchor, buckets.get(_record_key(anchor), []))
    for member in members:
        member["_used"] = True
    return members


def _best_cluster_row(
    anchor: dict[str, Any], members: list[dict[str, Any]], columns: list[str]
) -> dict[str, Any]:
    from draft_oracle.ingest.odds import _ODDS_COLUMNS

    home_probs = _covered_home_probs(members)
    best = {col: anchor[col] for col in _ODDS_COLUMNS}
    best["xval_delta"] = (max(home_probs) - min(home_probs)) if len(home_probs) > 1 else 0.0
    best["source_count"] = len(members)
    return {col: best[col] for col in columns}


def _covered_home_probs(members: list[dict[str, Any]]) -> list[float]:
    return [
        float(m["_home_prob"])
        for m in members
        if bool(m["covered"]) and m["_home_prob"] is not None and not pd.isna(m["_home_prob"])
    ]


def _blank_if_archive_unmatched(
    row: dict[str, Any],
    local_game_dates: Mapping[tuple[int, int, int], tuple[date, ...]] | None,
    local_game_types: Mapping[tuple[int, int, int], Mapping[date, int]] | None,
    stats: _ConsolidationStats,
) -> bool:
    reversed_only = _snap_to_local_date(row, local_game_dates)
    archive_unmatched = _label_playoff_from_archive(row, local_game_types)
    has_archive_gap = archive_unmatched or reversed_only
    is_covered = bool(row["covered"])
    if not has_archive_gap:
        return False
    if not is_covered:
        return False

    from draft_oracle.ingest.odds import _blank_market_fields

    _blank_market_fields(row)
    stats.unmatched_uncovered_rows += 1
    if reversed_only:
        stats.orientation_unmatched_rows += 1
    return True


def _has_missing_team_ids(row: dict[str, Any]) -> bool:
    away_id = row["away_team_id"]
    home_id = row["home_team_id"]
    return away_id is None or home_id is None or pd.isna(away_id) or pd.isna(home_id)


def _record_key(row: dict[str, Any]) -> tuple[int, int, int]:
    return (
        int(row["season_end_year"]),
        int(row["away_team_id"]),
        int(row["home_team_id"]),
    )


def _cluster_members(anchor: dict[str, Any], bucket: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Select the anchor plus the nearest unused row from each other source."""
    members = [anchor]
    taken_sources = {anchor["source"]}
    anchor_date = anchor["_date"]
    candidates = sorted(
        (
            rec
            for rec in bucket
            if not rec["_used"]
            and rec["_pos"] != anchor["_pos"]
            and rec["_date"] is not None
            and abs((rec["_date"] - anchor_date).days) <= 1
        ),
        key=lambda r: abs((r["_date"] - anchor_date).days),
    )
    for rec in candidates:
        if rec["source"] in taken_sources:
            continue
        members.append(rec)
        taken_sources.add(rec["source"])
    return members


def _parse_date_str(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _snap_to_local_date(
    row: dict[str, Any],
    local_game_dates: Mapping[tuple[int, int, int], tuple[date, ...]] | None,
) -> bool:
    """Rewrite ``game_date`` to the NHL-archive local date."""
    if not local_game_dates:
        return False
    snap = _local_date_snap(row)
    if snap is None:
        return False
    nearest = _nearest_local_date(local_game_dates.get(snap.key, ()), snap.current)
    if _apply_local_date_snap(row, snap.key, nearest):
        return False
    return _has_reversed_local_match(local_game_dates, snap)


@dataclass(frozen=True)
class _LocalDateSnap:
    key: tuple[int, int, int]
    current: date


def _local_date_snap(row: dict[str, Any]) -> _LocalDateSnap | None:
    key = _local_date_key(row)
    if key is None:
        return None
    current = _parse_date_str(str(row["game_date"]))
    if current is None:
        return None
    return _LocalDateSnap(key, current)


def _apply_local_date_snap(
    row: dict[str, Any], key: tuple[int, int, int], nearest: date | None
) -> bool:
    if nearest is None:
        return False
    _rewrite_local_game_date(row, key, nearest)
    return True


def _has_reversed_local_match(
    local_game_dates: Mapping[tuple[int, int, int], tuple[date, ...]],
    snap: _LocalDateSnap,
) -> bool:
    key = snap.key
    reversed_candidates = local_game_dates.get((key[0], key[2], key[1]), ())
    return _nearest_local_date(reversed_candidates, snap.current) is not None


def _local_date_key(row: dict[str, Any]) -> tuple[int, int, int] | None:
    home_id = row.get("home_team_id")
    away_id = row.get("away_team_id")
    if home_id is None or away_id is None:
        return None
    if pd.isna(home_id) or pd.isna(away_id):
        return None
    return (int(row["season_end_year"]), int(home_id), int(away_id))


def _nearest_local_date(candidates: tuple[date, ...], current: date) -> date | None:
    within = [d for d in candidates if abs((d - current).days) <= 1]
    if not within:
        return None
    return min(within, key=lambda d: (abs((d - current).days), d.toordinal()))


def _rewrite_local_game_date(row: dict[str, Any], key: tuple[int, int, int], nearest: date) -> None:
    from draft_oracle.ingest.odds import _game_key

    row["game_date"] = nearest.isoformat()
    row["game_key"] = _game_key(key[0], nearest, key[2], key[1])


def load_local_game_dates(
    archive_dir: Path = Path("data/raw/nhl-archive"),
) -> dict[tuple[int, int, int], tuple[date, ...]]:
    """Index NHL-archive local game dates by ``(season_end_year, home_id, away_id)``."""
    accumulator: dict[tuple[int, int, int], set[date]] = {}
    for path in sorted(archive_dir.glob("team-games-*.csv.gz")):
        _accumulate_local_dates(pd.read_csv(path), accumulator)
    return {key: tuple(sorted(values)) for key, values in accumulator.items()}


def _accumulate_local_dates(
    frame: pd.DataFrame, accumulator: dict[tuple[int, int, int], set[date]]
) -> None:
    required = {"gameId", "seasonId", "teamId", "homeRoad", "gameDate"}
    if frame.empty or not required.issubset(frame.columns):
        return
    home = frame.loc[frame["homeRoad"] == "H", ["gameId", "seasonId", "teamId", "gameDate"]]
    away = frame.loc[frame["homeRoad"] == "R", ["gameId", "teamId"]]
    merged = home.merge(away, on="gameId", suffixes=("_home", "_away"))
    seasons = merged["seasonId"].astype(int).tolist()
    homes = merged["teamId_home"].astype(int).tolist()
    aways = merged["teamId_away"].astype(int).tolist()
    dates = merged["gameDate"].astype(str).tolist()
    for season, home_id, away_id, raw_date in zip(seasons, homes, aways, dates, strict=True):
        local = _parse_date_str(str(raw_date)[:10])
        if local is None:
            continue
        accumulator.setdefault((int(season) % 10000, int(home_id), int(away_id)), set()).add(local)


def load_archive_game_types(
    archive_dir: Path = Path("data/raw/nhl-archive"),
) -> dict[tuple[int, int, int], dict[date, int]]:
    """Index NHL-archive ``gameTypeId`` by ``(season_end_year, home_id, away_id)``."""
    accumulator: dict[tuple[int, int, int], dict[date, int]] = {}
    for path in sorted(archive_dir.glob("team-games-*.csv.gz")):
        _accumulate_game_types(pd.read_csv(path), accumulator)
    return accumulator


def _accumulate_game_types(
    frame: pd.DataFrame, accumulator: dict[tuple[int, int, int], dict[date, int]]
) -> None:
    required = {"gameId", "seasonId", "teamId", "homeRoad", "gameDate", "gameTypeId"}
    if frame.empty or not required.issubset(frame.columns):
        return
    home = frame.loc[
        frame["homeRoad"] == "H",
        ["gameId", "seasonId", "teamId", "gameDate", "gameTypeId"],
    ]
    away = frame.loc[frame["homeRoad"] == "R", ["gameId", "teamId"]]
    merged = home.merge(away, on="gameId", suffixes=("_home", "_away"))
    seasons = merged["seasonId"].astype(int).tolist()
    homes = merged["teamId_home"].astype(int).tolist()
    aways = merged["teamId_away"].astype(int).tolist()
    dates = merged["gameDate"].astype(str).tolist()
    types = merged["gameTypeId"].astype(int).tolist()
    for season, home_id, away_id, raw_date, type_id in zip(
        seasons, homes, aways, dates, types, strict=True
    ):
        local = _parse_date_str(str(raw_date)[:10])
        if local is None:
            continue
        season_end = int(season) % 10000
        accumulator.setdefault((season_end, int(home_id), int(away_id)), {})[local] = int(type_id)
        accumulator.setdefault((season_end, int(away_id), int(home_id)), {})[local] = int(type_id)


def _lookup_game_type(
    game_types: Mapping[tuple[int, int, int], Mapping[date, int]],
    lookup: _GameTypeLookup | int,
    *legacy: int | date,
) -> int | None:
    """Archive ``gameTypeId`` for a matchup on ``game_date`` (exact, else ±1 day)."""
    lookup = _coerce_game_type_lookup(lookup, legacy)
    by_date = game_types.get((lookup.season_end_year, lookup.home_id, lookup.away_id))
    if not by_date:
        return None
    exact = by_date.get(lookup.game_date)
    if exact is not None:
        return exact
    near = sorted(
        (d for d in by_date if abs((d - lookup.game_date).days) <= 1),
        key=lambda d: (abs((d - lookup.game_date).days), d.toordinal()),
    )
    return by_date[near[0]] if near else None


def _coerce_game_type_lookup(
    lookup: _GameTypeLookup | int, legacy: tuple[int | date, ...]
) -> _GameTypeLookup:
    if isinstance(lookup, _GameTypeLookup):
        return lookup
    if len(legacy) != 3:
        raise TypeError("_lookup_game_type requires season, home, away, and game date")
    return _GameTypeLookup(
        season_end_year=lookup,
        home_id=int(cast("int", legacy[0])),
        away_id=int(cast("int", legacy[1])),
        game_date=cast("date", legacy[2]),
    )


def _label_playoff_from_archive(
    row: dict[str, Any],
    game_types: Mapping[tuple[int, int, int], Mapping[date, int]] | None,
) -> bool:
    """Set ``is_playoff`` from archive ``gameTypeId``; return True if unmatched."""
    if not game_types:
        return False
    home_id = row.get("home_team_id")
    away_id = row.get("away_team_id")
    if home_id is None or away_id is None:
        return False
    if pd.isna(home_id) or pd.isna(away_id):
        return False
    game_date = _parse_date_str(str(row["game_date"]))
    if game_date is None:
        return False
    type_id = _lookup_game_type(
        game_types,
        _GameTypeLookup(int(row["season_end_year"]), int(home_id), int(away_id), game_date),
    )
    if type_id is None:
        row["is_playoff"] = None
        return True

    from draft_oracle.ingest.odds import PLAYOFF_GAME_TYPE

    row["is_playoff"] = type_id == PLAYOFF_GAME_TYPE
    return False
