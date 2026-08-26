#!/usr/bin/env python3
"""Fetch 2025-26 NHL games + DraftKings pickcenter odds from ESPN's public API.

Politeness: one request per second, 3 attempts with exponential backoff.
ESPN 403s browser-like User-Agents, so we send curl's default.

Note: refactored after the 2026-08-26 fetch to satisfy CodeScene code-health gates
(functions extracted, no module-level control flow); behavior is identical. The
byte-exact script used for the run is the previous version in git history.
"""
import datetime as dt
import gzip
import json
import os
import subprocess
import sys
import time

START, END = "20251212", "20260630"
CHUNK_DAYS = 7
SB = "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard"
SUM = "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/summary"
# 'plays' is 68% of a summary payload and is play-by-play, not odds; these are dropped.
DROP_KEYS = {"plays", "news", "article", "videos", "standings"}
DELAY = 1.0


def get(url, attempts=3):
    """GET url, return parsed JSON, or None after `attempts` failures."""
    for i in range(attempts):
        time.sleep(DELAY)
        p = subprocess.run(["curl", "-sS", "--max-time", "45", url],
                           capture_output=True)
        if p.returncode == 0 and p.stdout:
            try:
                return json.loads(p.stdout)
            except json.JSONDecodeError:
                pass
        back = DELAY * (2 ** i)
        print(f"    retry {i+1}/{attempts} in {back:.0f}s  {url}", flush=True)
        time.sleep(back)
    return None


def chunks():
    s = dt.datetime.strptime(START, "%Y%m%d")
    e = dt.datetime.strptime(END, "%Y%m%d")
    while s <= e:
        ce = min(s + dt.timedelta(days=CHUNK_DAYS - 1), e)
        yield f"{s:%Y%m%d}-{ce:%Y%m%d}"
        s = ce + dt.timedelta(days=1)


def write_gz(path, obj):
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        json.dump(obj, fh, separators=(",", ":"))


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def event_index(ev):
    """Flatten one scoreboard event into the fields the summary pass needs."""
    comp = (ev.get("competitions") or [{}])[0]
    return {
        "id": ev["id"],
        "date": ev.get("date"),
        "name": ev.get("name"),
        "state": comp.get("status", {}).get("type", {}).get("state"),
        "seasontype": (ev.get("season") or {}).get("type"),
        "note": (comp.get("notes") or [{}])[0].get("headline"),
    }


def fetch_events(raw_sb):
    """Scoreboard pass: enumerate events in CHUNK_DAYS windows, keep raw responses."""
    events = []
    for rng in chunks():
        d = get(f"{SB}?dates={rng}")
        if d is None:
            print(f"SCOREBOARD FAIL {rng}", flush=True)
            continue
        write_gz(os.path.join(raw_sb, f"{rng}.json.gz"), d)
        got = d.get("events", []) or []
        events.extend(event_index(ev) for ev in got)
        print(f"scoreboard {rng}: {len(got)} events (running {len(events)})", flush=True)
    return events


def extract_odds(summary):
    """(provider, spread, over_under, favorite_moneyline) from pickcenter[0]."""
    pc = summary.get("pickcenter") or []
    if not pc:
        return None, None, None, None, "pickcenter absent"
    p = pc[0]
    provider = (p.get("provider") or {}).get("name")
    ho, ao = p.get("homeTeamOdds") or {}, p.get("awayTeamOdds") or {}
    fav_ml = ho.get("moneyLine") if ho.get("favorite") else ao.get("moneyLine")
    reason = None if fav_ml is not None else "pickcenter present but no favorite moneyLine"
    return provider, p.get("spread"), p.get("overUnder"), fav_ml, reason


def game_rows(ev, summary, odds):
    """Two per-team rows for one game, mirroring the Kaggle file's odds semantics."""
    provider, spread, over_under, fav_ml, _ = odds
    comp = (summary.get("header", {}).get("competitions") or [{}])[0]
    season = (summary.get("header", {}).get("season") or {}).get("year")
    cs = comp.get("competitors") or []
    scores = {c.get("homeAway"): c.get("score") for c in cs}
    rows = []
    for c in cs:
        ha = c.get("homeAway")
        opp = "away" if ha == "home" else "home"
        rows.append({
            "game_id": ev["id"],
            "date": comp.get("date"),
            "season": season,
            "team_name": (c.get("team") or {}).get("displayName"),
            "is_home": 1 if ha == "home" else 0,
            "won": 1 if c.get("winner") else 0,
            "goals_for": num(scores.get(ha)),
            "goals_against": num(scores.get(opp)),
            "spread": spread,
            "over_under": over_under,
            "favorite_moneyline": fav_ml,
            "_provider": provider,
            "_seasontype": ev.get("seasontype"),
            "_note": ev.get("note"),
            "_state": ev.get("state"),
        })
    return rows


def fetch_summaries(events, raw_sum):
    """Summary pass: raw payloads (minus DROP_KEYS), odds rows, missing-odds log."""
    rows, missing = [], []
    for n, ev in enumerate(events, 1):
        gid = ev["id"]
        d = get(f"{SUM}?event={gid}")
        if d is None:
            missing.append({"game_id": gid, "reason": "summary fetch failed", **ev})
            print(f"[{n}/{len(events)}] {gid} SUMMARY FAIL", flush=True)
            continue
        write_gz(os.path.join(raw_sum, f"{gid}.json.gz"),
                 {k: v for k, v in d.items() if k not in DROP_KEYS})
        odds = extract_odds(d)
        if odds[3] is None:
            comp = (d.get("header", {}).get("competitions") or [{}])[0]
            missing.append({"game_id": gid, "date": comp.get("date"), "reason": odds[4],
                            "name": ev.get("name"), "note": ev.get("note"),
                            "state": ev.get("state")})
        rows += game_rows(ev, d, odds)
        if n % 25 == 0 or n == len(events):
            print(f"[{n}/{len(events)}] rows={len(rows)} missing_odds={len(missing)}",
                  flush=True)
    return rows, missing


def main(out):
    raw_sum = os.path.join(out, "raw", "summary")
    raw_sb = os.path.join(out, "raw", "scoreboard")
    os.makedirs(raw_sum, exist_ok=True)
    os.makedirs(raw_sb, exist_ok=True)

    events = fetch_events(raw_sb)
    with open(os.path.join(out, "events.json"), "w") as fh:
        json.dump(events, fh, indent=1)
    print(f"TOTAL EVENTS {len(events)}", flush=True)

    rows, missing = fetch_summaries(events, raw_sum)
    with open(os.path.join(out, "rows.json"), "w") as fh:
        json.dump(rows, fh)
    with open(os.path.join(out, "missing_odds.json"), "w") as fh:
        json.dump(missing, fh, indent=1)
    print(f"DONE rows={len(rows)} games={len(rows)//2} missing_odds_games={len(missing)}",
          flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
