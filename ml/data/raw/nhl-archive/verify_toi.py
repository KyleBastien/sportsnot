#!/usr/bin/env python3
"""Validate committed NHL per-game TOI, power-play, and goalie reports."""

import csv
import gzip
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path


def read_rows(path):
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def number(row, key):
    value = row.get(key, "")
    if value in ("", None):
        return None
    return float(value)


def row_key(row):
    return row["gameId"], row["playerId"]


def compare_time_on_ice(summary_rows, toi_rows):
    summary = {row_key(row): number(row, "timeOnIcePerGame") for row in summary_rows}
    compared = 0
    within_one = 0
    missing = []
    worst = []
    for row in toi_rows:
        key = row_key(row)
        left = summary.get(key)
        right = number(row, "timeOnIce")
        if left is None or right is None:
            missing.append({"gameId": key[0], "playerId": key[1]})
            continue
        difference = abs(left - right)
        compared += 1
        within_one += difference <= 1.0
        worst.append((difference, key[0], key[1], left, right))
    worst.sort(reverse=True)
    return {
        "compared": compared,
        "within_1_second": within_one,
        "share_within_1_second": within_one / compared if compared else None,
        "missing_comparisons": len(missing),
        "worst_20": [
            {
                "difference_seconds": difference,
                "gameId": game_id,
                "playerId": player_id,
                "summary_timeOnIcePerGame": left,
                "timeonice_timeOnIce": right,
            }
            for difference, game_id, player_id, left, right in worst[:20]
        ],
    }


def strength_sum_check(toi_rows):
    compared = 0
    within_two = 0
    missing = 0
    worst = []
    for row in toi_rows:
        total = number(row, "timeOnIce")
        components = [number(row, key) for key in ("evTimeOnIce", "ppTimeOnIce", "shTimeOnIce")]
        if total is None or any(value is None for value in components):
            missing += 1
            continue
        component_sum = sum(components)
        difference = abs(total - component_sum)
        compared += 1
        within_two += difference <= 2.0
        worst.append((difference, row["gameId"], row["playerId"], total, component_sum))
    worst.sort(reverse=True)
    return {
        "compared": compared,
        "within_2_seconds": within_two,
        "share_within_2_seconds": within_two / compared if compared else None,
        "missing_components": missing,
        "definition": "evTimeOnIce includes OT; total = ev + pp + sh",
        "worst_20": [
            {
                "difference_seconds": difference,
                "gameId": game_id,
                "playerId": player_id,
                "timeOnIce": total,
                "component_sum": component_sum,
            }
            for difference, game_id, player_id, total, component_sum in worst[:20]
        ],
    }


def goalie_starter_check(goalie_rows):
    by_game_team = defaultdict(float)
    for row in goalie_rows:
        started = number(row, "gamesStarted")
        if started is not None:
            by_game_team[(row["gameId"], row["teamAbbrev"])] += started
    exceptions = [
        {"gameId": game_id, "teamAbbrev": team, "gamesStartedSum": total}
        for (game_id, team), total in sorted(by_game_team.items())
        if not math.isclose(total, 1.0)
    ]
    return {
        "game_teams": len(by_game_team),
        "exactly_one": len(by_game_team) - len(exceptions),
        "exceptions": exceptions,
    }


def verify_season(root, label):
    summary = read_rows(root / f"skater-games-{label}.csv.gz")
    toi = read_rows(root / f"skater-toi-{label}.csv.gz")
    powerplay = read_rows(root / f"skater-pp-{label}.csv.gz")
    goalies = read_rows(root / f"goalie-games-{label}.csv.gz")
    return {
        "season": label,
        "rows": {
            "skater_games": len(summary),
            "skater_toi": len(toi),
            "skater_toi_diff": len(toi) - len(summary),
            "skater_pp": len(powerplay),
            "skater_pp_diff": len(powerplay) - len(summary),
            "goalie_games": len(goalies),
        },
        "time_on_ice": compare_time_on_ice(summary, toi),
        "strength_sum": strength_sum_check(toi),
        "goalie_starters": goalie_starter_check(goalies),
    }


def aggregate(seasons):
    totals = Counter()
    starter_exceptions = []
    for season in seasons:
        rows = season["rows"]
        for key, value in rows.items():
            totals[key] += value
        for key in ("time_on_ice", "strength_sum"):
            for metric in ("compared", "within_1_second", "within_2_seconds"):
                if metric in season[key]:
                    totals[f"{key}_{metric}"] += season[key][metric]
        starter_exceptions.extend(
            {"season": season["season"], **row}
            for row in season["goalie_starters"]["exceptions"]
        )
        totals["goalie_game_teams"] += season["goalie_starters"]["game_teams"]
    toi_compared = totals["time_on_ice_compared"]
    strength_compared = totals["strength_sum_compared"]
    return {
        "rows": dict(totals),
        "time_on_ice_share_within_1_second": (
            totals["time_on_ice_within_1_second"] / toi_compared if toi_compared else None
        ),
        "strength_sum_share_within_2_seconds": (
            totals["strength_sum_within_2_seconds"] / strength_compared
            if strength_compared
            else None
        ),
        "goalie_starter_exception_count": len(starter_exceptions),
        "goalie_starter_exceptions": starter_exceptions,
    }


def main(root):
    labels = [path.name[len("skater-toi-") : -len(".csv.gz")] for path in sorted(root.glob("skater-toi-*.csv.gz"))]
    seasons = [verify_season(root, label) for label in labels]
    result = {"aggregate": aggregate(seasons), "seasons": seasons}
    (root / "_toi_verify.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(result["aggregate"], indent=1))
    return 0


if __name__ == "__main__":
    directory = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parent
    sys.exit(main(directory))
