#!/usr/bin/env python3
"""Derive offline per-game NHL deployment tables from committed shift charts."""

import argparse
import csv
import gzip
import heapq
import io
import itertools
import json
import os
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

TOI_COLUMNS = [
    "gameId",
    "playerId",
    "teamAbbrev",
    "toi5v5",
    "toiPP",
    "toiPK",
    "toiAll",
    "shifts",
]
LINE_COLUMNS = ["gameId", "teamAbbrev", "unitType", "playerIds", "toi5v5"]
PP_COLUMNS = ["gameId", "teamAbbrev", "playerIds", "toiPP", "ppRank"]
DRESSED_COLUMNS = ["gameId", "teamAbbrev", "playerId", "position", "dressed", "toiAll"]
NORMAL_SHIFT_TYPE = "517"


@dataclass
class DeploymentTotals:
    positions: dict
    totals: defaultdict = field(
        default_factory=lambda: defaultdict(
            lambda: {"toi5v5": 0, "toiPP": 0, "toiPK": 0, "toiAll": 0}
        )
    )
    lines: Counter = field(default_factory=Counter)
    pp_units: Counter = field(default_factory=Counter)


def log(message):
    print(message, flush=True)


def read_csv_gz(path):
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def position_map(archive, label):
    rows = read_csv_gz(archive / f"skater-bios-{label}.csv.gz")
    return {row["playerId"]: row["positionCode"] for row in rows}


def tier1_map(archive, label):
    rows = read_csv_gz(archive / f"skater-toi-{label}.csv.gz")
    return {
        (row["gameId"], row["playerId"]): (
            float(row["timeOnIce"]),
            float(row["ppTimeOnIce"]),
        )
        for row in rows
    }


def expected_game_teams(archive, label):
    rows = read_csv_gz(archive / f"game-times-{label}.csv.gz")
    return {row["gameId"]: (row["awayAbbrev"], row["homeAbbrev"]) for row in rows}


def integer(row, column):
    value = row.get(column, "")
    return int(float(value)) if value not in ("", None) else 0


def normal_interval(row, positions):
    player_id = row["playerId"]
    duration = integer(row, "durationSeconds")
    if row["typeCode"] != NORMAL_SHIFT_TYPE:
        return None
    if player_id not in positions:
        return None
    if duration <= 0:
        return None
    start = integer(row, "startSeconds")
    reported_end = integer(row, "endSeconds")
    end = (
        reported_end
        if reported_end >= start and reported_end - start == duration
        else start + duration
    )
    return integer(row, "period"), start, end, row["teamAbbrev"], player_id


def normal_intervals(rows, positions):
    intervals = [normal_interval(row, positions) for row in rows]
    intervals = [interval for interval in intervals if interval is not None]
    shift_keys = {
        (row["teamAbbrev"], row["playerId"], row["shiftNumber"])
        for row in rows
        if normal_interval(row, positions) is not None
    }
    shift_counts = Counter((team, player_id) for team, player_id, _ in shift_keys)
    return intervals, shift_counts


def strength(team_count, opponent_count):
    matchup = team_count, opponent_count
    if matchup == (5, 5):
        return "5v5"
    if matchup in {(4, 3), (5, 3), (5, 4), (6, 3), (6, 4)}:
        return "PP"
    if matchup in {(3, 4), (3, 5), (3, 6), (4, 5), (4, 6)}:
        return "PK"
    return "other"


def add_player_totals(duration, team_players, situation, totals):
    team, players = team_players
    situation_column = {"5v5": "toi5v5", "PP": "toiPP", "PK": "toiPK"}.get(situation)
    for player_id in players:
        totals[(team, player_id)]["toiAll"] += duration
        if situation_column is not None:
            totals[(team, player_id)][situation_column] += duration


def add_5v5_units(duration, team, players, state):
    forwards = tuple(sorted(player for player in players if state.positions[player] != "D"))
    defense = tuple(sorted(player for player in players if state.positions[player] == "D"))
    if len(forwards) == 3:
        state.lines[(team, "F3", forwards)] += duration
    if len(defense) == 2:
        state.lines[(team, "D2", defense)] += duration


def add_strength_unit(duration, team_players, situation, state):
    team, players = team_players
    if situation == "5v5":
        add_5v5_units(duration, team, players, state)
    elif situation == "PP" and len(players) == 5:
        state.pp_units[(team, tuple(sorted(players)))] += duration


def add_head_to_head_segment(duration, active, state):
    teams = sorted(active)
    for team in teams:
        opponent = teams[1] if team == teams[0] else teams[0]
        players = active[team]
        situation = strength(len(players), len(active[opponent]))
        team_players = team, players
        add_player_totals(duration, team_players, situation, state.totals)
        add_strength_unit(duration, team_players, situation, state)


def add_unmatched_segment(duration, active, state):
    for team, players in active.items():
        add_player_totals(duration, (team, players), "other", state.totals)


def add_segment(duration, active, state):
    if len(active) == 2:
        add_head_to_head_segment(duration, active, state)
        return
    add_unmatched_segment(duration, active, state)


def shift_events(intervals):
    events = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    for period, start, end, team, player_id in intervals:
        events[period][start][(team, player_id)] += 1
        events[period][end][(team, player_id)] -= 1
    return events


def update_active_counts(active_counts, deltas):
    for key, delta in deltas.items():
        active_counts[key] += delta
        if active_counts[key] <= 0:
            del active_counts[key]


def active_teams(active_counts):
    active = defaultdict(set)
    for (team, player_id), count in active_counts.items():
        if count > 0:
            active[team].add(player_id)
    return active


def sweep_period(timed_events, state):
    active_counts = Counter()
    times = sorted(timed_events)
    for current, following in itertools.pairwise(times):
        update_active_counts(active_counts, timed_events[current])
        duration = following - current
        if duration > 0:
            add_segment(duration, active_teams(active_counts), state)


def sweep_game(rows, positions):
    intervals, shift_counts = normal_intervals(rows, positions)
    events = shift_events(intervals)
    state = DeploymentTotals(positions)
    for period in sorted(events):
        sweep_period(events[period], state)
    return state.totals, state.lines, state.pp_units, shift_counts


def toi_rows(game_id, totals, shift_counts):
    rows = []
    for team, player_id in sorted(totals, key=lambda key: (key[0], int(key[1]))):
        values = totals[(team, player_id)]
        rows.append(
            {
                "gameId": game_id,
                "playerId": player_id,
                "teamAbbrev": team,
                **values,
                "shifts": shift_counts[(team, player_id)],
            }
        )
    return rows


def line_rows(game_id, line_totals):
    rows = []
    for (team, unit_type, players), seconds in sorted(
        line_totals.items(), key=lambda item: (item[0][0], item[0][1], item[0][2])
    ):
        if seconds < 60:
            continue
        rows.append(
            {
                "gameId": game_id,
                "teamAbbrev": team,
                "unitType": unit_type,
                "playerIds": "-".join(players),
                "toi5v5": seconds,
            }
        )
    return rows


def pp_rows(game_id, pp_totals):
    by_team = defaultdict(list)
    for (team, players), seconds in pp_totals.items():
        by_team[team].append((seconds, players))
    rows = []
    for team in sorted(by_team):
        ranked = sorted(by_team[team], key=lambda item: (-item[0], item[1]))
        for rank, (seconds, players) in enumerate(ranked, start=1):
            rows.append(
                {
                    "gameId": game_id,
                    "teamAbbrev": team,
                    "playerIds": "-".join(players),
                    "toiPP": seconds,
                    "ppRank": rank,
                }
            )
    return rows


def dressed_rows(game_id, rows, positions):
    return [
        {
            "gameId": game_id,
            "teamAbbrev": row["teamAbbrev"],
            "playerId": row["playerId"],
            "position": positions[row["playerId"]],
            "dressed": 1,
            "toiAll": row["toiAll"],
        }
        for row in rows
    ]


def gzip_csv_bytes(columns, rows):
    text = io.StringIO(newline="")
    writer = csv.DictWriter(text, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    output = io.BytesIO()
    with gzip.GzipFile(fileobj=output, mode="wb", filename="", mtime=0) as compressed:
        compressed.write(text.getvalue().encode("utf-8"))
    return output.getvalue()


def write_atomic(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(content)
    os.replace(temporary, path)


def comparison_values(season, row, official):
    official_all, official_pp = official
    all_difference = abs(row["toiAll"] - official_all)
    pp_difference = abs(row["toiPP"] - official_pp)
    worst = (
        max(all_difference, pp_difference),
        all_difference,
        pp_difference,
        season,
        row["gameId"],
        row["playerId"],
        row["toiAll"],
        official_all,
        row["toiPP"],
        official_pp,
    )
    return all_difference, pp_difference, worst


def record_comparison(validation, values):
    all_difference, pp_difference, worst = values
    validation["compared"] += 1
    validation["all_within_5"] += all_difference <= 5
    validation["pp_within_5"] += pp_difference <= 5
    heapq.heappush(validation["worst"], worst)
    if len(validation["worst"]) > 20:
        heapq.heappop(validation["worst"])


def update_crosscheck(validation, season, rows, tier1):
    for row in rows:
        official = tier1.get((row["gameId"], row["playerId"]))
        if official is None:
            validation["missing_tier1"] += 1
        else:
            record_comparison(validation, comparison_values(season, row, official))


def new_validation():
    return {
        "compared": 0,
        "all_within_5": 0,
        "pp_within_5": 0,
        "missing_tier1": 0,
        "dressed_distribution": Counter(),
        "dressed_exceptions": [],
        "worst": [],
    }


def difference_row(values):
    (
        all_difference,
        pp_difference,
        season,
        game_id,
        player_id,
        derived_all,
        official_all,
        derived_pp,
        official_pp,
    ) = values[1:]
    return {
        "season": season,
        "gameId": game_id,
        "playerId": player_id,
        "toiAllDifference": all_difference,
        "derivedToiAll": derived_all,
        "officialToiAll": official_all,
        "toiPPDifference": pp_difference,
        "derivedToiPP": derived_pp,
        "officialToiPP": official_pp,
    }


def ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def finish_validation(validation):
    compared = validation["compared"]
    return {
        "compared": compared,
        "toiAll_within_5_seconds": validation["all_within_5"],
        "toiAll_share_within_5_seconds": ratio(validation["all_within_5"], compared),
        "toiPP_within_5_seconds": validation["pp_within_5"],
        "toiPP_share_within_5_seconds": ratio(validation["pp_within_5"], compared),
        "missing_tier1": validation["missing_tier1"],
        "dressed_distribution": dict(
            sorted((str(key), value) for key, value in validation["dressed_distribution"].items())
        ),
        "dressed_exception_count": len(validation["dressed_exceptions"]),
        "dressed_exceptions": validation["dressed_exceptions"],
        "worst_20": [difference_row(row) for row in sorted(validation["worst"], reverse=True)],
    }


def iter_games(path):
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for game_id, rows in itertools.groupby(reader, key=lambda row: row["gameId"]):
            yield game_id, list(rows)


def record_dressed_validation(validation, game_id, game_dressed, expected_teams):
    counts = Counter(row["teamAbbrev"] for row in game_dressed)
    for team in sorted(expected_teams):
        count = counts[team]
        validation["dressed_distribution"][count] += 1
        if count != 18:
            validation["dressed_exceptions"].append(
                {"gameId": game_id, "teamAbbrev": team, "dressedSkaters": count}
            )


def derive_game(game_id, shifts, positions):
    totals, line_totals, pp_totals, shift_counts = sweep_game(shifts, positions)
    game_toi = toi_rows(game_id, totals, shift_counts)
    return {
        "skater-game-toi.csv.gz": game_toi,
        "lines.csv.gz": line_rows(game_id, line_totals),
        "pp-units.csv.gz": pp_rows(game_id, pp_totals),
        "dressed.csv.gz": dressed_rows(game_id, game_toi, positions),
    }


def empty_outputs():
    return {
        "skater-game-toi.csv.gz": [],
        "lines.csv.gz": [],
        "pp-units.csv.gz": [],
        "dressed.csv.gz": [],
    }


def extend_outputs(outputs, game_outputs):
    for filename in outputs:
        outputs[filename].extend(game_outputs[filename])


def write_derived_outputs(output, rows):
    definitions = {
        "skater-game-toi.csv.gz": TOI_COLUMNS,
        "lines.csv.gz": LINE_COLUMNS,
        "pp-units.csv.gz": PP_COLUMNS,
        "dressed.csv.gz": DRESSED_COLUMNS,
    }
    for filename, columns in definitions.items():
        write_atomic(output / filename, gzip_csv_bytes(columns, rows[filename]))


def row_counts(outputs):
    return {
        "skater_game_toi": len(outputs["skater-game-toi.csv.gz"]),
        "lines": len(outputs["lines.csv.gz"]),
        "pp_units": len(outputs["pp-units.csv.gz"]),
        "dressed": len(outputs["dressed.csv.gz"]),
    }


def process_season(root, archive, label):
    positions = position_map(archive, label)
    tier1 = tier1_map(archive, label)
    game_teams = expected_game_teams(archive, label)
    outputs = empty_outputs()
    validation = new_validation()
    games = 0
    observed_games = set()
    for game_id, shifts in iter_games(root / f"shifts-{label}.csv.gz"):
        game_outputs = derive_game(game_id, shifts, positions)
        game_toi = game_outputs["skater-game-toi.csv.gz"]
        update_crosscheck(validation, label, game_toi, tier1)
        record_dressed_validation(
            validation,
            game_id,
            game_outputs["dressed.csv.gz"],
            game_teams[game_id],
        )
        extend_outputs(outputs, game_outputs)
        observed_games.add(game_id)
        games += 1

    missing_games = sorted(set(game_teams) - observed_games, key=int)
    for game_id in missing_games:
        record_dressed_validation(validation, game_id, [], game_teams[game_id])

    counts = row_counts(outputs)
    write_derived_outputs(root / "derived" / label, outputs)
    log(
        f"{label}: games={games} skaters={counts['skater_game_toi']} "
        f"lines={counts['lines']} pp_units={counts['pp_units']}"
    )
    return {
        "season": label,
        "games": games,
        "expected_games": len(game_teams),
        "missing_shift_games": missing_games,
        "rows": counts,
        "validation": finish_validation(validation),
    }


def worst_tuple(row):
    return (
        max(row["toiAllDifference"], row["toiPPDifference"]),
        row["toiAllDifference"],
        row["toiPPDifference"],
        row["season"],
        row["gameId"],
        row["playerId"],
        row["derivedToiAll"],
        row["officialToiAll"],
        row["derivedToiPP"],
        row["officialToiPP"],
    )


def merge_worst(target, rows):
    for row in rows:
        heapq.heappush(target, worst_tuple(row))
        if len(target) > 20:
            heapq.heappop(target)


def merge_validation(target, season):
    validation = season["validation"]
    target["compared"] += validation["compared"]
    target["all_within_5"] += validation["toiAll_within_5_seconds"]
    target["pp_within_5"] += validation["toiPP_within_5_seconds"]
    target["missing_tier1"] += validation["missing_tier1"]
    target["dressed_distribution"].update(
        {int(key): value for key, value in validation["dressed_distribution"].items()}
    )
    target["dressed_exceptions"].extend(
        {"season": season["season"], **row} for row in validation["dressed_exceptions"]
    )
    merge_worst(target["worst"], validation["worst_20"])


def aggregate(seasons):
    validation = new_validation()
    rows = Counter()
    for season in seasons:
        rows.update(season["rows"])
        merge_validation(validation, season)
    return {
        "games": sum(season["games"] for season in seasons),
        "expected_games": sum(season["expected_games"] for season in seasons),
        "missing_shift_games": [
            {"season": season["season"], "gameId": game_id}
            for season in seasons
            for game_id in season["missing_shift_games"]
        ],
        "rows": dict(rows),
        "validation": finish_validation(validation),
    }


def selected_labels(root, values):
    labels = [
        path.name[len("shifts-") : -len(".csv.gz")] for path in sorted(root.glob("shifts-*.csv.gz"))
    ]
    if not values:
        return labels
    starts = {value[:4] for value in values}
    return [label for label in labels if label[:4] in starts]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", action="append")
    parser.add_argument(
        "--archive",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "nhl-archive",
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    seasons = [
        process_season(root, args.archive.resolve(), label)
        for label in selected_labels(root, args.season)
    ]
    manifest = {"aggregate": aggregate(seasons), "seasons": seasons}
    (root / "_deployment_manifest.json").write_text(
        json.dumps(manifest, indent=1) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest["aggregate"], indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
