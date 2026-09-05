"""Build deterministic validation tables from plaintext snapshot responses."""

from __future__ import annotations

import csv
import gzip
import io
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from odds_history_matching import blank_index_row, index_row, line_rows, match_event
from odds_history_models import INDEX_COLUMNS, LINES_COLUMNS, SEASONS, RequestPlan


@dataclass
class SeasonRows:
    indexes: list[dict[str, Any]]
    lines: list[dict[str, Any]]
    stats: dict[str, int]


def load_historical_payload(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(gzip.decompress(path.read_bytes()))
    except (OSError, json.JSONDecodeError):
        raise RuntimeError(f"invalid historical response file: {path}") from None
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise RuntimeError(f"unexpected historical response shape: {path}")
    if not isinstance(payload.get("timestamp"), str):
        raise RuntimeError(f"missing snapshot timestamp: {path}")
    return payload


def _write_csv_gz(path: Path, columns: tuple[str, ...], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with (
        path.open("wb") as raw,
        gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as compressed,
        io.TextIOWrapper(compressed, encoding="utf-8", newline="") as text,
    ):
        writer = csv.DictWriter(text, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _empty_stats() -> dict[str, dict[str, int]]:
    return {
        season: {"games": 0, "matched": 0, "unmatched": 0, "line_rows": 0} for season in SEASONS
    }


def _add_game_rows(
    plan: RequestPlan,
    payload: dict[str, Any],
    rows: SeasonRows,
) -> None:
    events = payload["data"]
    for game in plan.games:
        rows.stats["games"] += 1
        match = match_event(events, game)
        if match.event is None or match.delta_seconds is None:
            rows.indexes.append(
                blank_index_row(plan, game, match.status, str(payload["timestamp"]))
            )
            rows.stats["unmatched"] += 1
            continue
        rows.indexes.append(index_row(plan, game, payload, match))
        extracted = line_rows(plan, game, payload, match.event)
        rows.lines.extend(extracted)
        rows.stats["matched"] += 1
        rows.stats["line_rows"] += len(extracted)


def _index_sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return row["gameDate"], row["gameId"]


def _line_sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row["gameDate"],
        row["gameId"],
        row["bookmakerKey"],
        row["marketKey"],
        row["outcomeName"],
        str(row["point"]),
    )


def _write_season(
    scratch: Path,
    season: str,
    indexes: list[dict[str, Any]],
    lines: list[dict[str, Any]],
) -> None:
    indexes.sort(key=_index_sort_key)
    lines.sort(key=_line_sort_key)
    season_dir = scratch / season
    _write_csv_gz(season_dir / "index.csv.gz", INDEX_COLUMNS, indexes)
    _write_csv_gz(season_dir / "lines.csv.gz", LINES_COLUMNS, lines)


def build_plaintext_tables(scratch: Path, plans: list[RequestPlan]) -> dict[str, dict[str, int]]:
    indexes: dict[str, list[dict[str, Any]]] = defaultdict(list)
    lines: dict[str, list[dict[str, Any]]] = defaultdict(list)
    stats = _empty_stats()
    for plan in plans:
        payload = load_historical_payload(scratch / plan.season / plan.raw_relative_path)
        rows = SeasonRows(indexes[plan.season], lines[plan.season], stats[plan.season])
        _add_game_rows(plan, payload, rows)
    for season in SEASONS:
        _write_season(scratch, season, indexes[season], lines[season])
    return stats
