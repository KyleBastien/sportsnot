#!/usr/bin/env python3
"""Fetch per-game NHL skater TOI, power-play, and goalie summary reports."""

import argparse
import csv
import datetime as dt
import gzip
import io
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

REST = "https://api.nhle.com/stats/rest/en"
SEASONS = [(year, year + 1) for year in range(2007, 2026)]
GAME_TYPES = (2, 3)
DELAY = 1.0
ATTEMPTS = 4
CAP = 10000

SKATER_ID_COLUMNS = [
    "seasonId",
    "gameTypeId",
    "gameId",
    "gameDate",
    "playerId",
    "skaterFullName",
    "positionCode",
    "shootsCatches",
    "teamAbbrev",
    "opponentTeamAbbrev",
    "homeRoad",
]
SKATER_TOI_COLUMNS = [
    *SKATER_ID_COLUMNS,
    "evTimeOnIce",
    "ppTimeOnIce",
    "shTimeOnIce",
    "otTimeOnIce",
    "shifts",
    "timeOnIce",
]
SKATER_PP_COLUMNS = [
    *SKATER_ID_COLUMNS,
    "ppGoals",
    "ppAssists",
    "ppPoints",
    "ppShots",
    "ppTimeOnIce",
    "ppIndividualSatFor",
]
GOALIE_COLUMNS = [
    "seasonId",
    "gameTypeId",
    "gameId",
    "gameDate",
    "playerId",
    "goalieFullName",
    "teamAbbrev",
    "opponentTeamAbbrev",
    "homeRoad",
    "gamesStarted",
    "timeOnIce",
    "shotsAgainst",
    "goalsAgainst",
    "saves",
    "savePct",
    "shutouts",
    "decision",
    "wins",
    "losses",
    "otLosses",
]
REPORTS = {
    "skater-toi": ("skater/timeonice", SKATER_TOI_COLUMNS, True),
    "skater-pp": ("skater/powerplay", SKATER_PP_COLUMNS, True),
    "goalie-games": ("goalie/summary", GOALIE_COLUMNS, False),
}


class FetchError(RuntimeError):
    pass


@dataclass(frozen=True)
class ReportContext:
    path: str
    season: str
    game_type: int
    counters: dict


@dataclass
class ArchiveState:
    counters: dict
    seasons: dict


def log(message):
    print(message, flush=True)


def get(url, params, counters):
    """Curl GET with 1 req/s politeness and four exponential-backoff attempts."""
    command = ["curl", "-sS", "--max-time", "180", "-G", url]
    for key, value in params.items():
        command += ["--data-urlencode", f"{key}={value}"]
    for attempt in range(ATTEMPTS):
        time.sleep(DELAY)
        counters["requests"] += 1
        process = subprocess.run(command, capture_output=True)
        if process.returncode == 0 and process.stdout:
            try:
                return json.loads(process.stdout)
            except json.JSONDecodeError:
                pass
        if attempt + 1 == ATTEMPTS:
            break
        counters["retries"] += 1
        backoff = DELAY * (2**attempt)
        log(f"    retry {attempt + 1}/{ATTEMPTS} in {backoff:.0f}s :: {url} {params}")
        time.sleep(backoff)
    counters["failures"] += 1
    raise FetchError(f"request failed after {ATTEMPTS} attempts: {url} {params}")


def report(path, cayenne, counters):
    payload = get(
        f"{REST}/{path}",
        {
            "isGame": "true",
            "limit": "-1",
            "start": "0",
            "cayenneExp": cayenne,
        },
        counters,
    )
    rows = payload.get("data", [])
    return rows, payload.get("total")


def season_label(start_year):
    return f"{start_year}-{str(start_year + 1)[-2:]}"


def season_id(start_year):
    return f"{start_year}{start_year + 1}"


def month_bounds(year_month, half=None):
    year, month = int(year_month[:4]), int(year_month[5:7])
    last = (dt.date(year + (month == 12), month % 12 + 1, 1) - dt.timedelta(days=1)).day
    if half == 1:
        return f"{year_month}-01", f"{year_month}-15"
    if half == 2:
        return f"{year_month}-16", f"{year_month}-{last:02d}"
    return f"{year_month}-01", f"{year_month}-{last:02d}"


def read_game_times(outdir, label):
    path = outdir / f"game-times-{label}.csv.gz"
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def game_type_months(game_times, game_type):
    return sorted(
        {
            row["gameDate"][:7]
            for row in game_times
            if row["gameTypeId"] == str(game_type) and row["gameDate"]
        }
    )


def date_cayenne(season, game_type, low, high):
    return (
        f'seasonId={season} and gameTypeId={game_type} and gameDate>="{low}" and gameDate<="{high}"'
    )


def assert_below_cap(rows, total, context):
    declared = -1 if total is None else int(total)
    if declared >= CAP or len(rows) >= CAP:
        raise FetchError(
            f"{context} reached report cap: declared total={total!r}, rows={len(rows)}"
        )


def below_cap(rows, total):
    declared_below = total is None or int(total) < CAP
    return declared_below and len(rows) < CAP


def fetch_window(context, low, high):
    rows, total = report(
        context.path,
        date_cayenne(context.season, context.game_type, low, high),
        context.counters,
    )
    return rows, total


def fetch_month(context, year_month):
    low, high = month_bounds(year_month)
    rows, total = fetch_window(context, low, high)
    if below_cap(rows, total):
        context.counters["monthly_partitions"] += 1
        context.counters["largest_partition_rows"] = max(
            context.counters["largest_partition_rows"], len(rows)
        )
        return rows

    context.counters["cap_hits"] += 1
    log(f"      {year_month} hit {CAP} cap -> split into halves")
    combined = []
    for half in (1, 2):
        half_low, half_high = month_bounds(year_month, half)
        half_rows, half_total = fetch_window(context, half_low, half_high)
        assert_below_cap(
            half_rows,
            half_total,
            f"{context.path} {half_low}..{half_high}",
        )
        context.counters["half_month_partitions"] += 1
        context.counters["largest_partition_rows"] = max(
            context.counters["largest_partition_rows"], len(half_rows)
        )
        combined.extend(half_rows)
    return combined


def fetch_monthly_report(context, months):
    rows = []
    for year_month in months:
        fetched = fetch_month(context, year_month)
        rows.extend(fetched)
        log(f"    {context.path} {context.game_type} {year_month}: {len(fetched)}")
    return rows


def fetch_goalies(context, months):
    rows, total = report(
        context.path,
        f"seasonId={context.season} and gameTypeId={context.game_type}",
        context.counters,
    )
    if below_cap(rows, total):
        context.counters["season_partitions"] += 1
        context.counters["largest_partition_rows"] = max(
            context.counters["largest_partition_rows"], len(rows)
        )
        return rows
    context.counters["cap_hits"] += 1
    log(f"    {context.path} {context.game_type} hit {CAP} cap -> split by month")
    return fetch_monthly_report(context, months)


def stamp(rows, season, game_type):
    for row in rows:
        row["seasonId"] = season
        row["gameTypeId"] = game_type
    return rows


def add_goalie_decisions(rows):
    for row in rows:
        if str(row.get("wins", "")) == "1":
            row["decision"] = "W"
        elif str(row.get("losses", "")) == "1":
            row["decision"] = "L"
        elif str(row.get("otLosses", "")) == "1":
            row["decision"] = "OTL"
        else:
            row["decision"] = ""
    return rows


def gzip_csv_bytes(columns, rows):
    text = io.StringIO(newline="")
    writer = csv.DictWriter(text, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {column: "" if row.get(column) is None else row.get(column) for column in columns}
        )
    output = io.BytesIO()
    with gzip.GzipFile(fileobj=output, mode="wb", filename="", mtime=0) as compressed:
        compressed.write(text.getvalue().encode("utf-8"))
    return output.getvalue()


def write_atomic(path, content):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(content)
    os.replace(temporary, path)


def sort_rows(rows):
    return sorted(
        rows,
        key=lambda row: (
            int(row.get("gameId", 0) or 0),
            str(row.get("teamAbbrev", "")),
            int(row.get("playerId", 0) or 0),
        ),
    )


def selected_starts(values):
    if not values:
        return [season[0] for season in SEASONS]
    starts = []
    for value in values:
        start = int(value[:4])
        if start not in range(2007, 2026):
            raise SystemExit(f"season outside 2007-08..2025-26: {value}")
        starts.append(start)
    return sorted(set(starts))


def completed(outdir, label):
    return all((outdir / f"{name}-{label}.csv.gz").exists() for name in REPORTS)


def repair_existing_goalie_decisions(outdir, label):
    path = outdir / f"goalie-games-{label}.csv.gz"
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    add_goalie_decisions(rows)
    write_atomic(path, gzip_csv_bytes(GOALIE_COLUMNS, sort_rows(rows)))


def fetch_report(context, months, monthly):
    if monthly:
        return fetch_monthly_report(context, months)
    rows = fetch_goalies(context, months)
    add_goalie_decisions(rows)
    log(f"    {context.path} {context.game_type}: {len(rows)}")
    return rows


def collect_game_type(season, game_type, game_times, counters):
    months = game_type_months(game_times, game_type)
    rows_by_report = {}
    fields_by_report = {}
    row_counts = {"months": months}
    for name, definition in REPORTS.items():
        path = definition[0]
        monthly = definition[2]
        context = ReportContext(path, season, game_type, counters)
        rows = stamp(fetch_report(context, months, monthly), season, game_type)
        rows_by_report[name] = rows
        fields_by_report[name] = set().union(*(row.keys() for row in rows))
        row_counts[f"{name}_rows"] = len(rows)
    return row_counts, rows_by_report, fields_by_report


def merge_report_rows(target, incoming):
    for name in REPORTS:
        target[name].extend(incoming[name])


def merge_observed_fields(target, incoming):
    for name in REPORTS:
        target[name].update(incoming[name])


def write_season_outputs(outdir, label, output_rows):
    for name, definition in REPORTS.items():
        columns = definition[1]
        rows = sort_rows(output_rows[name])
        write_atomic(outdir / f"{name}-{label}.csv.gz", gzip_csv_bytes(columns, rows))
        log(f"  wrote {name}-{label}.csv.gz: {len(rows)} rows")


def collect_season_reports(season, game_times, counters):
    output_rows = {name: [] for name in REPORTS}
    observed_fields = {name: set() for name in REPORTS}
    per_type = {}
    for game_type in GAME_TYPES:
        counts, rows, fields = collect_game_type(season, game_type, game_times, counters)
        per_type[str(game_type)] = counts
        merge_report_rows(output_rows, rows)
        merge_observed_fields(observed_fields, fields)
    return output_rows, observed_fields, per_type


def season_result(label, season, collected):
    output_rows, observed_fields, per_type = collected
    return {
        "season": label,
        "seasonId": season,
        "per_gameType": per_type,
        "rows": {name: len(rows) for name, rows in output_rows.items()},
        "observed_fields": {name: sorted(fields) for name, fields in observed_fields.items()},
        "skipped": False,
    }


def process_season(outdir, start_year, counters):
    label = season_label(start_year)
    season = season_id(start_year)
    if completed(outdir, label):
        repair_existing_goalie_decisions(outdir, label)
        log(f"SKIP {label}: all three outputs exist")
        return {"season": label, "seasonId": season, "skipped": True}

    log(f"=== {label} ({season})")
    game_times = read_game_times(outdir, label)
    collected = collect_season_reports(season, game_times, counters)
    output_rows = collected[0]
    write_season_outputs(outdir, label, output_rows)
    return season_result(label, season, collected)


def empty_counters():
    return {
        "requests": 0,
        "retries": 0,
        "failures": 0,
        "monthly_partitions": 0,
        "half_month_partitions": 0,
        "season_partitions": 0,
        "cap_hits": 0,
        "largest_partition_rows": 0,
    }


def load_state(manifest_path):
    if not manifest_path.exists():
        return ArchiveState(empty_counters(), {})
    prior = json.loads(manifest_path.read_text(encoding="utf-8"))
    counters = empty_counters() | prior.get("request_counts", {})
    seasons = {row["season"]: row for row in prior.get("seasons", [])}
    return ArchiveState(counters, seasons)


def save_state(manifest_path, state):
    manifest_path.write_text(
        json.dumps(
            {
                "request_counts": state.counters,
                "seasons": list(state.seasons.values()),
            },
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )


def fetch_selected_seasons(outdir, starts, state, manifest_path):
    for start_year in starts:
        result = process_season(outdir, start_year, state.counters)
        if not result["skipped"] or result["season"] not in state.seasons:
            state.seasons[result["season"]] = result
        save_state(manifest_path, state)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("outdir", type=Path, nargs="?", default=Path(__file__).resolve().parent)
    parser.add_argument("--season", action="append")
    args = parser.parse_args()
    outdir = args.outdir.resolve()
    manifest_path = outdir / "_toi_manifest.json"
    state = load_state(manifest_path)
    try:
        fetch_selected_seasons(
            outdir,
            selected_starts(args.season),
            state,
            manifest_path,
        )
    except FetchError as error:
        (outdir / "_toi_gaps.json").write_text(
            json.dumps(
                {"error": str(error), "request_counts": state.counters},
                indent=1,
            )
            + "\n",
            encoding="utf-8",
        )
        log(f"STOP: {error}")
        return 1
    (outdir / "_toi_gaps.json").write_text("[]\n", encoding="utf-8")
    log(f"DONE seasons={len(state.seasons)} requests={state.counters['requests']} failures=0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
