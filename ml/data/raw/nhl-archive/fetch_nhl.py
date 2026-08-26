#!/usr/bin/env python3
"""Snapshot NHL per-game skater/team rows, bios and playoff brackets, 2015-16..2025-26.

Uses the stats-rest bulk per-game reports (isGame=true) rather than per-player calls.

Two API facts this script is built around:
  * limit=-1 returns the whole result set in one request, but the API hard-caps any
    single query at 10,000 rows AND clamps the reported `total` to 10000 as well, so a
    full regular season of skater-games (~47k rows) silently truncates. Queries are
    therefore partitioned by month, with an assert + automatic half-month split if a
    partition ever reaches the cap.
  * limit values between 101 and 10000 are ignored (always 100 rows), so pagination by
    `start` would need ~470 requests per season. Month partitions need ~9.

Politeness: 1 req/s, 4 attempts with exponential backoff.

Note: refactored after the 2026-08-26 archive run to satisfy CodeScene code-health
gates (functions extracted, no module-level control flow); behavior is identical.
The byte-exact script used for the run is the previous version in git history.
"""
import csv
import datetime as dt
import gzip
import json
import os
import subprocess
import sys
import time

REST = "https://api.nhle.com/stats/rest/en"
WEB = "https://api-web.nhle.com/v1"
SEASONS = [(y, y + 1) for y in range(2015, 2026)]   # 20152016 .. 20252026
GAME_TYPES = [2, 3]
DELAY = 1.0
CAP = 10000

SKATER_COLS = ["seasonId","gameTypeId","gameId","gameDate","playerId","skaterFullName",
               "positionCode","shootsCatches","teamAbbrev","opponentTeamAbbrev","homeRoad",
               "goals","assists","points","shots","timeOnIcePerGame","ppGoals","ppPoints",
               "shGoals","shPoints","evGoals","evPoints","plusMinus","penaltyMinutes",
               "gameWinningGoals","otGoals","shootingPct","faceoffWinPct"]
TEAM_COLS = ["seasonId","gameTypeId","gameId","gameDate","teamId","teamFullName",
             "opponentTeamAbbrev","homeRoad","goalsFor","goalsAgainst","wins","losses",
             "otLosses","ties","regulationAndOtWins","winsInRegulation","winsInShootout",
             "points","pointPct","shotsForPerGame","shotsAgainstPerGame","faceoffWinPct",
             "powerPlayPct","powerPlayNetPct","penaltyKillPct","penaltyKillNetPct",
             "teamShutouts"]
BIO_COLS = ["seasonId","playerId","skaterFullName","lastName","birthDate","positionCode",
            "shootsCatches","height","weight","birthCity","birthStateProvinceCode",
            "birthCountryCode","nationalityCode","draftYear","draftRound","draftOverall",
            "firstSeasonForGameType","currentTeamAbbrev"]


def log(msg):
    print(msg, flush=True)


def get(url, params=None, attempts=4):
    """GET JSON with 1 req/s politeness and exponential backoff. None on give-up."""
    cmd = ["curl", "-sS", "--max-time", "180", "-G", url]
    for k, v in (params or {}).items():
        cmd += ["--data-urlencode", f"{k}={v}"]
    for i in range(attempts):
        time.sleep(DELAY)
        p = subprocess.run(cmd, capture_output=True)
        if p.returncode == 0 and p.stdout:
            try:
                return json.loads(p.stdout)
            except json.JSONDecodeError:
                pass
        back = DELAY * (2 ** i)
        log(f"    retry {i+1}/{attempts} in {back:.0f}s :: {url} {params}")
        time.sleep(back)
    return None


def report(path, cayenne):
    """One stats-rest per-game report query. Returns (rows, reported_total)."""
    d = get(f"{REST}/{path}", {"isGame": "true", "limit": "-1", "start": "0",
                               "cayenneExp": cayenne})
    if d is None:
        return None, None
    return d.get("data", []), d.get("total")


def months(dates):
    """Distinct YYYY-MM present in an iterable of YYYY-MM-DD strings, sorted."""
    return sorted({s[:7] for s in dates if s})


def month_bounds(ym, half=None):
    y, m = int(ym[:4]), int(ym[5:7])
    last = (dt.date(y + (m == 12), m % 12 + 1, 1) - dt.timedelta(days=1)).day
    if half == 1:
        return f"{ym}-01", f"{ym}-15"
    if half == 2:
        return f"{ym}-16", f"{ym}-{last:02d}"
    return f"{ym}-01", f"{ym}-{last:02d}"


def skater_window(season, gt, lo, hi):
    """Skater-game rows for one date window. Returns (rows|None, total, note|None)."""
    ce = (f'seasonId={season} and gameTypeId={gt} '
          f'and gameDate>="{lo}" and gameDate<="{hi}"')
    rows, total = report("skater/summary", ce)
    if rows is None:
        return None, None, {"season": season, "gameTypeId": gt, "window": f"{lo}..{hi}",
                            "issue": "request failed after retries"}
    return rows, total, None


def fetch_skaters(season, gt, ym):
    """Skater-game rows for one month; splits in half if the 10k cap is hit."""
    rows, total, note = skater_window(season, gt, *month_bounds(ym))
    if note:
        return [], [note]
    if total is None or total < CAP:
        return rows, []
    log(f"      {ym} hit the {CAP} cap -> splitting into halves")
    out, notes = [], []
    for half in (1, 2):
        lo, hi = month_bounds(ym, half)
        r2, t2, note2 = skater_window(season, gt, lo, hi)
        if note2:
            notes.append(note2)
            continue
        if t2 is not None and t2 >= CAP:
            notes.append({"season": season, "gameTypeId": gt, "window": f"{lo}..{hi}",
                          "issue": f"half-month still at the {CAP} cap - TRUNCATED"})
        out += r2
    return out, notes


def write_csv_gz(path, cols, rows):
    with gzip.open(path, "wt", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({c: ("" if r.get(c) is None else r.get(c)) for c in cols})


def stamp(rows, season, gt):
    for r in rows:
        r["seasonId"], r["gameTypeId"] = season, gt
    return rows


def fetch_game_type(season, label, gt, gaps):
    """Team + skater rows for one season/gameType. Returns (team_rows, skater_rows, stats)."""
    trows, ttotal = report("team/summary", f"seasonId={season} and gameTypeId={gt}")
    if trows is None:
        gaps.append({"season": label, "gameTypeId": gt,
                     "issue": "team/summary request failed after retries"})
        return [], [], None
    if ttotal is not None and ttotal >= CAP:
        gaps.append({"season": label, "gameTypeId": gt,
                     "issue": f"team/summary at the {CAP} cap - TRUNCATED"})
    stamp(trows, season, gt)
    gids = {r["gameId"] for r in trows}
    log(f"  gameType {gt}: team-rows {len(trows)} games {len(gids)}")

    srows = []
    for ym in months(r["gameDate"] for r in trows):
        got, notes = fetch_skaters(season, gt, ym)
        gaps += notes
        srows += got
        log(f"    skaters {ym}: {len(got)}")
    stamp(srows, season, gt)
    stats = {"team_rows": len(trows), "games": len(gids), "skater_rows": len(srows),
             "skater_games": len({r["gameId"] for r in srows})}
    return trows, srows, stats


def fetch_bios(season, label, gaps):
    """Season bios, merged across game types, first occurrence per player wins."""
    bios, seen = [], set()
    for gt in GAME_TYPES:
        d = get(f"{REST}/skater/bios", {"isGame": "false", "limit": "-1", "start": "0",
                                        "cayenneExp": f"seasonId={season} and gameTypeId={gt}"})
        if d is None:
            gaps.append({"season": label, "gameTypeId": gt,
                         "issue": "skater/bios request failed after retries"})
            continue
        if d.get("total", 0) >= CAP:
            gaps.append({"season": label, "gameTypeId": gt,
                         "issue": f"skater/bios at the {CAP} cap - TRUNCATED"})
        for r in d.get("data", []):
            if r["playerId"] in seen:
                continue
            seen.add(r["playerId"])
            r["seasonId"] = season
            bios.append(r)
    return bios


def fetch_bracket(out, y1, label, gaps):
    br = get(f"{WEB}/playoff-bracket/{y1}")
    if br is None:
        gaps.append({"season": label, "issue": f"playoff-bracket/{y1} failed after retries"})
        return False
    with open(f"{out}/bracket-{y1}.json", "w") as fh:
        json.dump(br, fh, indent=1)
    return True


def process_season(out, y0, y1, gaps):
    season, label = f"{y0}{y1}", f"{y0}-{str(y1)[2:]}"
    log(f"=== season {label} ({season})")
    team_rows, skater_rows, per_gt = [], [], {}
    for gt in GAME_TYPES:
        trows, srows, stats = fetch_game_type(season, label, gt, gaps)
        team_rows += trows
        skater_rows += srows
        if stats is not None:
            per_gt[gt] = stats

    write_csv_gz(f"{out}/team-games-{label}.csv.gz", TEAM_COLS, team_rows)
    write_csv_gz(f"{out}/skater-games-{label}.csv.gz", SKATER_COLS, skater_rows)

    bios = fetch_bios(season, label, gaps)
    write_csv_gz(f"{out}/skater-bios-{label}.csv.gz", BIO_COLS, bios)
    no_bd = sum(1 for b in bios if not b.get("birthDate"))
    log(f"  bios {len(bios)} (missing birthDate: {no_bd})")

    got_bracket = fetch_bracket(out, y1, label, gaps)
    log(f"  wrote {label}: team {len(team_rows)} skater {len(skater_rows)} bios {len(bios)}")
    return {"season": label, "seasonId": season, "per_gameType": per_gt,
            "bios": len(bios), "bios_missing_birthdate": no_bd, "bracket": got_bracket}


def main(out):
    os.makedirs(out, exist_ok=True)
    manifest, gaps = [], []
    for y0, y1 in SEASONS:
        manifest.append(process_season(out, y0, y1, gaps))
    json.dump(manifest, open(f"{out}/_manifest.json", "w"), indent=1)
    json.dump(gaps, open(f"{out}/_gaps.json", "w"), indent=1)
    log(f"DONE seasons={len(manifest)} gaps={len(gaps)}")


if __name__ == "__main__":
    main(sys.argv[1])
