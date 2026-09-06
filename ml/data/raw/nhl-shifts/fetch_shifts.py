#!/usr/bin/env python3
"""Fetch NHL shift charts into resumable raw caches and compact season CSVs."""

import argparse
import csv
import gzip
import hashlib
import io
import json
import os
import subprocess
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from shift_html import (
    FetchError,
    parse_html_report,
    read_game_players,
    seconds,
    shift_interval_parts,
)

REST_URL = "https://api.nhle.com/stats/rest/en/shiftcharts"
HTML_BASE = "https://www.nhl.com/scores/htmlreports"
PROBE_STARTS = (2007, 2008, 2009, 2010, 2023)
DELAY = 1.0
ATTEMPTS = 4
CAP = 10000
SHIFT_COLUMNS = [
    "gameId",
    "teamAbbrev",
    "playerId",
    "firstName",
    "lastName",
    "period",
    "startSeconds",
    "endSeconds",
    "durationSeconds",
    "shiftNumber",
    "typeCode",
    "eventDescription",
]
MANIFEST_COLUMNS = ["gameId", "bytes", "sha256"]
HTML_MANIFEST_COLUMNS = ["gameId", "side", "bytes", "sha256"]
@dataclass
class FetchContext:
    root: Path
    archive: Path
    label: str
    season: str
    counters: dict
    player_map: dict | None = None


@dataclass
class GamePayload:
    game_id: str
    raw: bytes | None
    rows: list
    source: str
    html_manifest: list


@dataclass
class SeasonAccumulator:
    manifest: list = field(default_factory=list)
    html_manifest: list = field(default_factory=list)
    row_count: int = 0
    goal_markers: int = 0
    sources: Counter = field(default_factory=Counter)

    def add(self, payload):
        self.row_count += len(payload.rows)
        self.goal_markers += sum(row["typeCode"] == "505" for row in payload.rows)
        self.sources[payload.source] += 1
        self.html_manifest.extend(payload.html_manifest)
        if payload.raw is not None:
            self.manifest.append(raw_manifest_row(payload.game_id, payload.raw))
        else:
            self.manifest.extend(html_raw_manifest_rows(payload.html_manifest))


def log(message):
    print(message, flush=True)


def season_label(start_year):
    return f"{start_year}-{str(start_year + 1)[-2:]}"


def season_id(start_year):
    return f"{start_year}{start_year + 1}"


def gzip_bytes(content):
    output = io.BytesIO()
    with gzip.GzipFile(fileobj=output, mode="wb", filename="", mtime=0) as compressed:
        compressed.write(content)
    return output.getvalue()


def write_atomic(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(content)
    os.replace(temporary, path)


def read_cache(path):
    with gzip.open(path, "rb") as handle:
        return handle.read()


def valid_process_response(process, require_json):
    if process.returncode != 0 or not process.stdout:
        return False
    if not require_json:
        return True
    try:
        json.loads(process.stdout)
        return True
    except json.JSONDecodeError:
        return False


def curl_get(url, params, counters, require_json=False):
    command = ["curl", "-sS", "--max-time", "180", "-G", url]
    for key, value in params.items():
        command += ["--data-urlencode", f"{key}={value}"]
    for attempt in range(ATTEMPTS):
        time.sleep(DELAY)
        counters["requests"] += 1
        process = subprocess.run(command, capture_output=True)
        if valid_process_response(process, require_json):
            return process.stdout
        if attempt + 1 == ATTEMPTS:
            break
        counters["retries"] += 1
        backoff = DELAY * (2**attempt)
        log(f"    retry {attempt + 1}/{ATTEMPTS} in {backoff:.0f}s :: {url} {params}")
        time.sleep(backoff)
    counters["failures"] += 1
    raise FetchError(f"request failed after {ATTEMPTS} attempts: {url} {params}")


def json_cache_path(root, label, game_id):
    return root / "cache" / label / f"{game_id}.json.gz"


def html_cache_path(root, label, game_id, side):
    return root / "cache" / label / f"{game_id}-{side}.html.gz"


def fetch_json(context, game_id):
    path = json_cache_path(context.root, context.label, game_id)
    if path.exists():
        context.counters["cache_hits"] += 1
        raw = read_cache(path)
    else:
        raw = curl_get(
            REST_URL,
            {"cayenneExp": f"gameId={game_id}"},
            context.counters,
            require_json=True,
        )
        write_atomic(path, gzip_bytes(raw))
        context.counters["cache_writes"] += 1
    payload = json.loads(raw)
    rows = payload.get("data", [])
    total = payload.get("total")
    declared = -1 if total is None else int(total)
    if declared >= CAP or len(rows) >= CAP:
        raise FetchError(
            f"shift chart cap reached for {game_id}: total={total!r}, rows={len(rows)}"
        )
    return raw, rows, total


def fetch_html(context, game_id, side):
    path = html_cache_path(context.root, context.label, game_id, side)
    if path.exists():
        context.counters["html_cache_hits"] += 1
        return read_cache(path)
    report_id = game_id[-6:]
    raw = curl_get(
        f"{HTML_BASE}/{context.season}/{side}{report_id}.HTM",
        {},
        context.counters,
    )
    write_atomic(path, gzip_bytes(raw))
    context.counters["html_cache_writes"] += 1
    return raw


def string_value(row, key):
    return str(row.get(key) or "")


def json_output_row(row, interval):
    period, start, end, duration = interval
    return {
        "gameId": string_value(row, "gameId"),
        "teamAbbrev": string_value(row, "teamAbbrev"),
        "playerId": string_value(row, "playerId"),
        "firstName": string_value(row, "firstName"),
        "lastName": string_value(row, "lastName"),
        "period": str(period),
        "startSeconds": str(start),
        "endSeconds": str(end),
        "durationSeconds": str(duration),
        "shiftNumber": string_value(row, "shiftNumber"),
        "typeCode": string_value(row, "typeCode"),
        "eventDescription": string_value(row, "eventDescription"),
    }


def normalized_json_rows(row):
    game_id = string_value(row, "gameId")
    period = int(string_value(row, "period") or 0)
    start = seconds(row.get("startTime"))
    end = seconds(row.get("endTime"))
    if string_value(row, "typeCode") != "517":
        duration = seconds(row.get("duration"))
        return [json_output_row(row, (period, start, end, duration))]
    duration = seconds(row.get("duration"))
    return [
        json_output_row(row, (part_period, part_start, part_end, part_end - part_start))
        for part_period, part_start, part_end in shift_interval_parts(
            game_id, (period, start, end, duration)
        )
    ]


def sort_integer(row, key):
    return int(row[key] or 0)


def row_sort_key(row):
    return (
        sort_integer(row, "gameId"),
        row["teamAbbrev"],
        sort_integer(row, "playerId"),
        sort_integer(row, "period"),
        sort_integer(row, "startSeconds"),
        sort_integer(row, "endSeconds"),
        sort_integer(row, "shiftNumber"),
        sort_integer(row, "typeCode"),
    )


def read_game_times(archive, label):
    path = archive / f"game-times-{label}.csv.gz"
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        return sorted(csv.DictReader(handle), key=lambda row: int(row["gameId"]))


def rest_unavailable(root, label):
    path = root / "_probe_results.json"
    if not path.exists():
        return False
    rows = [
        row
        for row in json.loads(path.read_text(encoding="utf-8"))["results"]
        if row["season"] == label
    ]
    return len(rows) == 2 and not any(row["served"] for row in rows)


def ensure_player_map(context):
    if context.player_map is None:
        context.player_map = read_game_players(context.archive, context.label)


def raw_manifest_row(game_id, raw):
    return {
        "gameId": game_id,
        "bytes": str(len(raw)),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def html_raw_manifest_rows(records):
    return [
        {
            "gameId": record["gameId"],
            "bytes": record["bytes"],
            "sha256": record["sha256"],
        }
        for record in records
    ]


def fallback_rows(context, game):
    ensure_player_map(context)
    rows = []
    manifest = []
    for side, team_key in (("TH", "homeAbbrev"), ("TV", "awayAbbrev")):
        raw = fetch_html(context, game["gameId"], side)
        parsed = parse_html_report(
            raw,
            game["gameId"],
            game[team_key],
            context.player_map,
        )
        rows.extend(parsed)
        manifest.append({"side": side, **raw_manifest_row(game["gameId"], raw)})
    return rows, manifest


def game_payload(context, game, html_only):
    raw, source_rows = None, []
    if not html_only:
        raw, source_rows, total = fetch_json(context, game["gameId"])
        del total
    if any(string_value(row, "typeCode") == "517" for row in source_rows):
        rows = [normalized for row in source_rows for normalized in normalized_json_rows(row)]
        return GamePayload(game["gameId"], raw, rows, "rest", [])
    rows, html_manifest = fallback_rows(context, game)
    source = "html" if rows else "unavailable"
    return GamePayload(game["gameId"], raw, rows, source, html_manifest)


def gzip_csv_writer(path, columns):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    binary = temporary.open("wb")
    compressed = gzip.GzipFile(fileobj=binary, mode="wb", filename="", mtime=0)
    text = io.TextIOWrapper(compressed, encoding="utf-8", newline="")
    writer = csv.DictWriter(text, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    return temporary, binary, compressed, text, writer


def finish_gzip_writer(path, resources):
    temporary, binary, compressed, text = resources[:4]
    text.flush()
    text.detach()
    compressed.close()
    binary.close()
    os.replace(temporary, path)


def abort_gzip_writer(resources):
    binary, compressed, text = resources[1:4]
    text.close()
    compressed.close()
    binary.close()


def manifest_bytes(rows, columns=MANIFEST_COLUMNS):
    text = io.StringIO(newline="")
    writer = csv.DictWriter(text, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return gzip_bytes(text.getvalue().encode("utf-8"))


def progress(context, accumulator, index, game_count):
    log(
        f"  {context.label}: {index}/{game_count} games, "
        f"{accumulator.row_count} rows, "
        f"cache={context.counters['cache_hits']} "
        f"requests={context.counters['requests']}"
    )


def process_games(context, games, html_only, writer):
    accumulator = SeasonAccumulator()
    for index, game in enumerate(games, start=1):
        payload = game_payload(context, game, html_only)
        payload.rows.sort(key=row_sort_key)
        writer.writerows(payload.rows)
        accumulator.add(payload)
        if index % 100 == 0 or index == len(games):
            progress(context, accumulator, index, len(games))
    return accumulator


def write_season_manifests(root, label, accumulator):
    write_atomic(
        root / f"cache-manifest-{label}.csv.gz",
        manifest_bytes(accumulator.manifest),
    )
    html_manifest_path = root / f"html-cache-manifest-{label}.csv.gz"
    if accumulator.html_manifest:
        write_atomic(
            html_manifest_path,
            manifest_bytes(accumulator.html_manifest, HTML_MANIFEST_COLUMNS),
        )


def season_summary(context, games, accumulator, output_path):
    return {
        "season": context.label,
        "games": len(games),
        "rows": accumulator.row_count,
        "goal_markers": accumulator.goal_markers,
        "sources": dict(accumulator.sources),
        "output_bytes": output_path.stat().st_size,
    }


def process_season(root, archive, start_year, counters):
    label = season_label(start_year)
    context = FetchContext(root, archive, label, season_id(start_year), counters)
    games = read_game_times(archive, label)
    output_path = root / f"shifts-{label}.csv.gz"
    resources = gzip_csv_writer(output_path, SHIFT_COLUMNS)
    html_only = rest_unavailable(root, label)
    if html_only:
        ensure_player_map(context)
        log(f"  {label}: probe marked REST unavailable; using TH/TV HTML")
    try:
        accumulator = process_games(context, games, html_only, resources[-1])
    except BaseException:
        abort_gzip_writer(resources)
        raise
    finish_gzip_writer(output_path, resources)
    write_season_manifests(root, label, accumulator)
    return season_summary(context, games, accumulator, output_path)


def probe_result(context, game_type, game):
    raw, rows, total = fetch_json(context, game["gameId"])
    return {
        "season": context.label,
        "gameTypeId": game_type,
        "gameId": game["gameId"],
        "rows": len(rows),
        "reported_total": total,
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "served": bool(rows),
    }


def probe(root, archive, counters):
    results = []
    for start_year in PROBE_STARTS:
        label = season_label(start_year)
        context = FetchContext(root, archive, label, season_id(start_year), counters)
        games = read_game_times(archive, label)
        for game_type in ("2", "3"):
            game = next(row for row in games if row["gameTypeId"] == game_type)
            result = probe_result(context, game_type, game)
            results.append(result)
            log(f"PROBE {label} type={game_type} game={game['gameId']} rows={result['rows']}")
    write_atomic(
        root / "_probe_results.json",
        (json.dumps({"request_counts": counters, "results": results}, indent=1) + "\n").encode(
            "utf-8"
        ),
    )
    return all(row["served"] for row in results)


def html_probe_result(root, archive, counters, probe_row):
    label = probe_row["season"]
    games = read_game_times(archive, label)
    game = next(row for row in games if row["gameId"] == probe_row["gameId"])
    context = FetchContext(
        root,
        archive,
        label,
        season_id(int(label[:4])),
        counters,
        read_game_players(archive, label),
    )
    rows = fallback_rows(context, game)[0]
    log(f"HTML PROBE {label} type={game['gameTypeId']} game={game['gameId']} rows={len(rows)}")
    return {
        "season": label,
        "gameTypeId": probe_row["gameTypeId"],
        "gameId": game["gameId"],
        "rows": len(rows),
        "served": bool(rows),
    }


def probe_html(root, archive, counters):
    probe_path = root / "_probe_results.json"
    probe_results = json.loads(probe_path.read_text(encoding="utf-8"))["results"]
    results = [
        html_probe_result(root, archive, counters, row)
        for row in probe_results
        if not row["served"]
    ]
    write_atomic(
        root / "_html_probe_results.json",
        (json.dumps({"request_counts": counters, "results": results}, indent=1) + "\n").encode(
            "utf-8"
        ),
    )
    return all(row["served"] for row in results)


def selected_starts(values):
    if not values:
        return list(range(2007, 2026))
    starts = sorted({int(value[:4]) for value in values})
    if any(start not in range(2007, 2026) for start in starts):
        raise SystemExit("season outside 2007-08..2025-26")
    return starts


def counters():
    return {
        "requests": 0,
        "retries": 0,
        "failures": 0,
        "cache_hits": 0,
        "cache_writes": 0,
        "html_cache_hits": 0,
        "html_cache_writes": 0,
    }


def merge_error_counts(root, counts):
    path = root / "_fetch_error.json"
    if not path.exists():
        return
    error_counts = json.loads(path.read_text(encoding="utf-8")).get("request_counts", {})
    for key in ("retries", "failures"):
        counts[key] = max(counts[key], error_counts.get(key, 0))


def reconcile_request_counts(root, counts):
    json_files = list((root / "cache").glob("*/*.json.gz"))
    html_files = list((root / "cache").glob("*/*.html.gz"))
    merge_error_counts(root, counts)
    counts["cache_writes"] = len(json_files)
    counts["html_cache_writes"] = len(html_files)
    counts["requests"] = len(json_files) + len(html_files)
    counts["requests"] += counts["retries"] + counts["failures"]
    return counts


def load_fetch_state(root):
    path = root / "_fetch_manifest.json"
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        counts = counters() | payload.get("request_counts", {})
        seasons = {row["season"]: row for row in payload.get("seasons", [])}
        return reconcile_request_counts(root, counts), seasons
    return reconcile_request_counts(root, counters()), {}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--probe-html", action="store_true")
    parser.add_argument("--season", action="append")
    parser.add_argument(
        "--archive",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "nhl-archive",
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    counts = counters()
    try:
        if args.probe:
            return 0 if probe(root, args.archive.resolve(), counts) else 2
        if args.probe_html:
            return 0 if probe_html(root, args.archive.resolve(), counts) else 2
        counts, by_season = load_fetch_state(root)
        for start_year in selected_starts(args.season):
            result = process_season(root, args.archive.resolve(), start_year, counts)
            by_season[result["season"]] = result
            (root / "_fetch_manifest.json").write_text(
                json.dumps(
                    {"request_counts": counts, "seasons": list(by_season.values())},
                    indent=1,
                )
                + "\n",
                encoding="utf-8",
            )
        log(f"DONE seasons={len(by_season)} requests={counts['requests']} failures=0")
        return 0
    except FetchError as error:
        (root / "_fetch_error.json").write_text(
            json.dumps({"error": str(error), "request_counts": counts}, indent=1) + "\n",
            encoding="utf-8",
        )
        log(f"STOP: {error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
