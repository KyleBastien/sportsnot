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
SKATER_TOI_COLUMNS = SKATER_ID_COLUMNS + [
    "evTimeOnIce",
    "ppTimeOnIce",
    "shTimeOnIce",
    "otTimeOnIce",
    "shifts",
    "timeOnIce",
]
SKATER_PP_COLUMNS = SKATER_ID_COLUMNS + [
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
        f'seasonId={season} and gameTypeId={game_type} '
        f'and gameDate>="{low}" and gameDate<="{high}"'
    )


def assert_below_cap(rows, total, context):
    declared = -1 if total is None else int(total)
    if declared >= CAP or len(rows) >= CAP:
        raise FetchError(
            f"{context} reached report cap: declared total={total!r}, rows={len(rows)}"
        )


def fetch_window(path, season, game_type, low, high, counters):
    rows, total = report(path, date_cayenne(season, game_type, low, high), counters)
    return rows, total


def fetch_month(path, season, game_type, year_month, counters):
    low, high = month_bounds(year_month)
    rows, total = fetch_window(path, season, game_type, low, high, counters)
    if (total is None or int(total) < CAP) and len(rows) < CAP:
        counters["monthly_partitions"] += 1
        counters["largest_partition_rows"] = max(counters["largest_partition_rows"], len(rows))
        return rows

    counters["cap_hits"] += 1
    log(f"      {year_month} hit {CAP} cap -> split into halves")
    combined = []
    for half in (1, 2):
        half_low, half_high = month_bounds(year_month, half)
        half_rows, half_total = fetch_window(
            path, season, game_type, half_low, half_high, counters
        )
        assert_below_cap(half_rows, half_total, f"{path} {half_low}..{half_high}")
        counters["half_month_partitions"] += 1
        counters["largest_partition_rows"] = max(
            counters["largest_partition_rows"], len(half_rows)
        )
        combined.extend(half_rows)
    return combined


def fetch_monthly_report(path, season, game_type, months, counters):
    rows = []
    for year_month in months:
        fetched = fetch_month(path, season, game_type, year_month, counters)
        rows.extend(fetched)
        log(f"    {path} {game_type} {year_month}: {len(fetched)}")
    return rows


def fetch_goalies(path, season, game_type, months, counters):
    rows, total = report(path, f"seasonId={season} and gameTypeId={game_type}", counters)
    if (total is None or int(total) < CAP) and len(rows) < CAP:
        counters["season_partitions"] += 1
        counters["largest_partition_rows"] = max(counters["largest_partition_rows"], len(rows))
        return rows
    counters["cap_hits"] += 1
    log(f"    {path} {game_type} hit {CAP} cap -> split by month")
    return fetch_monthly_report(path, season, game_type, months, counters)


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
    writer = csv.DictWriter(
        text, fieldnames=columns, extrasaction="ignore", lineterminator="\n"
    )
    writer.writeheader()
    for row in rows:
        writer.writerow({column: "" if row.get(column) is None else row.get(column) for column in columns})
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
        return [start for start, _end in SEASONS]
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


def process_season(outdir, start_year, counters):
    label = season_label(start_year)
    season = season_id(start_year)
    if completed(outdir, label):
        repair_existing_goalie_decisions(outdir, label)
        log(f"SKIP {label}: all three outputs exist")
        return {"season": label, "seasonId": season, "skipped": True}

    game_times = read_game_times(outdir, label)
    output_rows = {name: [] for name in REPORTS}
    observed_fields = {name: set() for name in REPORTS}
    per_type = {}
    log(f"=== {label} ({season})")
    for game_type in GAME_TYPES:
        months = game_type_months(game_times, game_type)
        per_type[str(game_type)] = {"months": months}
        for name, (path, _columns, monthly) in REPORTS.items():
            if monthly:
                rows = fetch_monthly_report(path, season, game_type, months, counters)
            else:
                rows = fetch_goalies(path, season, game_type, months, counters)
                add_goalie_decisions(rows)
                log(f"    {path} {game_type}: {len(rows)}")
            stamp(rows, season, game_type)
            output_rows[name].extend(rows)
            for row in rows:
                observed_fields[name].update(row)
            per_type[str(game_type)][f"{name}_rows"] = len(rows)

    for name, (_path, columns, _monthly) in REPORTS.items():
        rows = sort_rows(output_rows[name])
        write_atomic(outdir / f"{name}-{label}.csv.gz", gzip_csv_bytes(columns, rows))
        log(f"  wrote {name}-{label}.csv.gz: {len(rows)} rows")

    return {
        "season": label,
        "seasonId": season,
        "per_gameType": per_type,
        "rows": {name: len(rows) for name, rows in output_rows.items()},
        "observed_fields": {name: sorted(fields) for name, fields in observed_fields.items()},
        "skipped": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("outdir", type=Path, nargs="?", default=Path(__file__).resolve().parent)
    parser.add_argument("--season", action="append")
    args = parser.parse_args()
    outdir = args.outdir.resolve()
    empty_counters = {
        "requests": 0,
        "retries": 0,
        "failures": 0,
        "monthly_partitions": 0,
        "half_month_partitions": 0,
        "season_partitions": 0,
        "cap_hits": 0,
        "largest_partition_rows": 0,
    }
    manifest_path = outdir / "_toi_manifest.json"
    if manifest_path.exists():
        prior = json.loads(manifest_path.read_text(encoding="utf-8"))
        counters = empty_counters | prior.get("request_counts", {})
        by_season = {row["season"]: row for row in prior.get("seasons", [])}
    else:
        counters = empty_counters
        by_season = {}
    try:
        for start_year in selected_starts(args.season):
            result = process_season(outdir, start_year, counters)
            if not result["skipped"] or result["season"] not in by_season:
                by_season[result["season"]] = result
            manifest_path.write_text(
                json.dumps(
                    {"request_counts": counters, "seasons": list(by_season.values())},
                    indent=1,
                )
                + "\n",
                encoding="utf-8",
            )
    except FetchError as error:
        (outdir / "_toi_gaps.json").write_text(
            json.dumps({"error": str(error), "request_counts": counters}, indent=1) + "\n",
            encoding="utf-8",
        )
        log(f"STOP: {error}")
        return 1
    (outdir / "_toi_gaps.json").write_text("[]\n", encoding="utf-8")
    log(f"DONE seasons={len(by_season)} requests={counters['requests']} failures=0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
