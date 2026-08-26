#!/usr/bin/env python3
"""Verification bar from ml/data/raw/nhl-archive/README.md."""
import csv, glob, gzip, json, os, sys, collections
D = sys.argv[1]
out = {}
print(f"{'season':9s} {'reg games':>9s} {'reg rows':>8s} {'po games':>8s} {'po rows':>7s} "
      f"{'skater rows':>11s} {'bios':>5s} {'no birthdate':>12s}")
for f in sorted(glob.glob(f"{D}/team-games-*.csv.gz")):
    season = os.path.basename(f)[len("team-games-"):-len(".csv.gz")]
    trows = list(csv.DictReader(gzip.open(f, "rt")))
    srows = list(csv.DictReader(gzip.open(f"{D}/skater-games-{season}.csv.gz", "rt")))
    brows = list(csv.DictReader(gzip.open(f"{D}/skater-bios-{season}.csv.gz", "rt")))
    reg = [r for r in trows if r["gameTypeId"] == "2"]
    po  = [r for r in trows if r["gameTypeId"] == "3"]
    nb = sum(1 for b in brows if not b["birthDate"])
    out[season] = {
        "reg_games": len({r["gameId"] for r in reg}), "reg_rows": len(reg),
        "po_games": len({r["gameId"] for r in po}), "po_rows": len(po),
        "skater_rows": len(srows), "skater_games": len({r["gameId"] for r in srows}),
        "bios": len(brows), "bios_no_birthdate": nb,
    }
    o = out[season]
    print(f"{season:9s} {o['reg_games']:9d} {o['reg_rows']:8d} {o['po_games']:8d} "
          f"{o['po_rows']:7d} {o['skater_rows']:11d} {o['bios']:5d} {nb:12d}")

    # goals reconciliation: sum of skater goals per game vs team goalsFor per game
    tg = {(r["gameId"], r["teamFullName"]): int(r["goalsFor"]) for r in trows}
    # team rows key on teamFullName, skater rows on teamAbbrev -> reconcile per game total
    team_by_game = collections.defaultdict(int)
    for r in trows: team_by_game[r["gameId"]] += int(r["goalsFor"])
    sk_by_game = collections.defaultdict(int)
    for r in srows: sk_by_game[r["gameId"]] += int(r["goals"] or 0)
    common = set(team_by_game) & set(sk_by_game)
    diffs = {g: team_by_game[g] - sk_by_game[g] for g in common}
    mism = {g: v for g, v in diffs.items() if v != 0}
    o["games_compared"] = len(common)
    o["goal_mismatches"] = len(mism)
    o["mismatch_hist"] = dict(collections.Counter(mism.values()))
    o["games_missing_skaters"] = len(set(team_by_game) - set(sk_by_game))
    print(f"          goals reconcile: {len(common)-len(mism)}/{len(common)} games exact; "
          f"mismatches {len(mism)} {o['mismatch_hist'] or ''}; "
          f"games with no skater rows {o['games_missing_skaters']}")

print("\n=== brackets ===")
for f in sorted(glob.glob(f"{D}/bracket-*.json")):
    d = json.load(open(f))
    series = d.get("series", [])
    fin = [s for s in series if s.get("playoffRound") == 4]
    line = f"{os.path.basename(f)}: series {len(series)}"
    for s in fin:
        t, b = s.get("topSeedTeam", {}), s.get("bottomSeedTeam", {})
        line += (f" | FINAL {t.get('abbrev')} {s.get('topSeedWins')}-"
                 f"{s.get('bottomSeedWins')} {b.get('abbrev')}"
                 f" winner={s.get('winningTeamId')}")
    print(line)
json.dump(out, open(f"{D}/_verify.json", "w"), indent=1)
