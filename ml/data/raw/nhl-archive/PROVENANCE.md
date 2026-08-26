# Provenance — NHL API historical archive

Snapshot fetched **2026-08-26** from the public NHL APIs (no auth). Seasons **2015-16
through 2025-26**, regular season and playoffs (`gameTypeId` 2 and 3).

Contents: 11 × 3 gzipped CSVs, 11 playoff brackets, the fetch script (`fetch_nhl.py`)
and the verification script (`verify_nhl.py`). 47 files, 12 MB. No `.gitignore` rule
matches this directory, so no exception was needed.

**No gaps. No imputation.** Every request succeeded, `_gaps.json` came back empty, and
every field written is a field the API returned. The only reconciliation discrepancy in
the whole archive is six games, fully explained below.

---

## 1. Endpoints and exact parameters

### Skater rows — `skater-games-<season>.csv.gz`

```
GET https://api.nhle.com/stats/rest/en/skater/summary
    ?isGame=true
    &limit=-1
    &start=0
    &cayenneExp=seasonId=<yyyyYYYY> and gameTypeId=<2|3>
                and gameDate>="<YYYY-MM-01>" and gameDate<="<YYYY-MM-DD>"
```

### Team rows — `team-games-<season>.csv.gz`

```
GET https://api.nhle.com/stats/rest/en/team/summary
    ?isGame=true&limit=-1&start=0
    &cayenneExp=seasonId=<yyyyYYYY> and gameTypeId=<2|3>
```

### Bios — `skater-bios-<season>.csv.gz`

```
GET https://api.nhle.com/stats/rest/en/skater/bios
    ?isGame=false&limit=-1&start=0
    &cayenneExp=seasonId=<yyyyYYYY> and gameTypeId=<2|3>
```

Run for both game types and merged on `playerId`, first occurrence wins, so
playoff-only players are not dropped.

### Brackets — `bracket-<year>.json`

```
GET https://api-web.nhle.com/v1/playoff-bracket/<year>
```

Years 2016–2026 (the season's ending year), stored verbatim.

Politeness: **1 request/second, 4 attempts with exponential backoff.** Total ≈ 260
requests. **0 retries fired and 0 requests failed.**

### Two API behaviours the script is built around

**`limit=-1` returns the whole result set in one request — but every query is hard-capped
at 10,000 rows, and the reported `total` is clamped to 10000 as well.** A full regular
season of skater-games is ~47,500 rows, so a naive `limit=-1` season query returns
exactly 10,000 rows and *reports* `total: 10000`, i.e. it truncates 79% of the season
while looking complete. `start=10000` then returns zero rows, so `start`-paging past the
cap does not work either.

Verified directly: `seasonId=20242025 and gameTypeId=2` reports `total: 10000` and yields
10,000 rows; the same query for `gameTypeId=3` reports `total: 3096` and yields 3,096
(honest, because it is under the cap).

**`limit` values between 101 and 10000 are silently ignored** — the response is always
100 rows. So `start`-paging would need ~475 requests per season-gameType.

The script therefore partitions each skater query **by calendar month**, which keeps
every partition well under the cap (largest observed: 8,421 rows, 2021-03) and needs
only ~9 requests per season-gameType. Months are derived from the game dates actually
present in that season's team rows, so no month is guessed and none is missed. As a
belt-and-braces check the script asserts `total < 10000` per partition and automatically
re-splits into half-months if a partition ever reaches the cap; **that path never
triggered in this run.**

## 2. Which report supplies which column

**One report supplies everything needed: `skater/summary` with `isGame=true`.** The
README allows for pulling the `timeonice` and `powerplay` reports separately if
per-game TOI/PP are absent from the summary report — **they are not absent**, so those
extra reports were not fetched and no column here is stitched together from more than
one endpoint.

| Column | Report | API field | Notes |
|---|---|---|---|
| `timeOnIcePerGame` | `skater/summary` | same | **seconds**, float (e.g. `1299.0` = 21:39). Despite the "PerGame" name, with `isGame=true` this is that single game's TOI |
| `ppGoals`, `ppPoints` | `skater/summary` | same | power play |
| `shGoals`, `shPoints` | `skater/summary` | same | short-handed |
| `evGoals`, `evPoints` | `skater/summary` | same | even strength |
| `goals`, `assists`, `points`, `shots`, `plusMinus`, `penaltyMinutes` | `skater/summary` | same | |
| `gameWinningGoals`, `otGoals`, `shootingPct`, `faceoffWinPct` | `skater/summary` | same | `faceoffWinPct` is null for most non-centres |
| `positionCode`, `shootsCatches`, `skaterFullName`, `playerId` | `skater/summary` | same | |
| `teamAbbrev`, `opponentTeamAbbrev`, `homeRoad` | `skater/summary` | same | `homeRoad` is `H`/`R` |
| `seasonId`, `gameTypeId` | *added by the script* | — | from the query parameters; the API does not echo them on per-game rows |

Mapping notes for the other two tables:

* **`team-games`** identifies the row's team by `teamId` + `teamFullName`, but the
  opponent by **abbreviation** (`opponentTeamAbbrev`). That asymmetry is the API's, not
  a transformation — a team-id ↔ abbreviation map is needed to join the two tables,
  since `skater-games` uses abbreviations on both sides. `teamFullName` carries
  diacritics (`Montréal Canadiens`).
* **There is no explicit OT/SO flag.** It is derivable per row from
  `wins`/`losses`/`otLosses`/`winsInRegulation`/`winsInShootout`: a win with
  `winsInShootout=1` is a shootout win; a win with `winsInRegulation=0` and
  `winsInShootout=0` is an OT win; `otLosses=1` is an OT-or-SO loss. `ties` is present
  but always empty in this era.
* **`skater-bios`** supplies `birthDate` for the age feature, plus draft and physical
  fields. **`birthDate` is populated for all 10,146 bio rows across all 11 seasons —
  zero missing.**

## 3. Counts against the README verification bar

| Season | Reg games | PO games | Team rows | Skater rows | Bios | Goals reconcile | Mismatch |
|---|---|---|---|---|---|---|---|
| 2015-16 | 1 230 | 91 | 2 642 | 47 553 | 900 | 1 321/1 321 | 0 |
| 2016-17 | 1 230 | 87 | 2 634 | 47 406 | 891 | 1 317/1 317 | 0 |
| 2017-18 | 1 271 | 84 | 2 710 | 48 780 | 890 | 1 355/1 355 | 0 |
| 2018-19 | 1 271 | 87 | 2 716 | 48 887 | 910 | 1 358/1 358 | 0 |
| 2019-20 | 1 082 | 130 | 2 424 | 43 630 | 890 | 1 211/1 212 | 1 |
| 2020-21 | 868 | 84 | 1 904 | 34 250 | 917 | 952/952 | 0 |
| 2021-22 | 1 312 | 89 | 2 802 | 50 412 | 1 006 | 1 401/1 401 | 0 |
| 2022-23 | 1 312 | 88 | 2 800 | 50 376 | 953 | 1 399/1 400 | 1 |
| 2023-24 | 1 312 | 88 | 2 800 | 50 389 | 925 | 1 399/1 400 | 1 |
| 2024-25 | 1 312 | 86 | 2 796 | 50 320 | 924 | 1 395/1 398 | 3 |
| 2025-26 | 1 312 | 82 | 2 788 | 50 182 | 940 | 1 394/1 394 | 0 |
| **total** | **13 512** | **996** | **29 016** | **522 185** | **10 146** | **14 502/14 508** | **6** |

Team rows are exactly `2 × games` in every season. Skater rows cover every game — zero
games have team rows but no skater rows, in any season.

### Where the README's bar is wrong, and why the data is right

The README sets the regular-season bar at "~1,271–1,353 games". **2015-16 and 2016-17
land at 1,230, below that floor, and that is correct, not missing data** — the NHL had
**30 teams** then, so 30 × 82 / 2 = 1,230. Vegas made it 31 teams in 2017-18
(31 × 82 / 2 = 1,271) and Seattle made it 32 in 2021-22 (32 × 82 / 2 = 1,312). Every
season in the table matches its league size exactly. The bar's floor should be 1,230 for
30-team seasons.

The two irregular seasons behave as the README anticipated, and were checked against the
brackets rather than a fixed number:

* **2019-20** — 1,082 regular-season games (COVID cut the season short in March 2020)
  and **130 playoff games, above the 87–105 bar**. `bracket-2020.json` explains it: it
  carries **23 series, including 8 at `playoffRound: 0`** — the bubble qualifying round —
  against 15 series in every other year. So the extra games are the play-in round, which
  the API classifies as `gameTypeId=3`. Correct, not duplicated.
* **2020-21** — 868 regular-season games, which is the 56-game season across 31 teams
  (31 × 56 / 2 = 868). 84 playoff games, within the bar.

Playoff counts land inside the 87–105 bar for 2015-16, 2016-17, 2018-19 and 2021-22, and
slightly **below** it for 2017-18 (84), 2020-21 (84), 2022-23 (88), 2023-24 (88),
2024-25 (86) and 2025-26 (82). The bar's floor of 87 is simply tighter than reality: a
playoff can be as short as 60 games, and each of these is consistent with its bracket's
series lengths.

**Cross-source check on 2025-26:** this archive has **82 playoff games**, and the
independently-fetched ESPN odds archive (`../odds-archive/espn-2025-26-completion/`,
`season.type=3`) also has **82**. Two different APIs agree.

## 4. Goals reconciliation — six mismatches, all explained

Summing skater goals per game against the sum of team `goalsFor` for the same game:
**14,502 of 14,508 games reconcile exactly.** All six exceptions are `+1` in the same
direction (team goals one higher than skater goals), and every one has the same cause:

| Season | gameId | Date | Score | Missing scorer |
|---|---|---|---|---|
| 2019-20 | 2019020684 | 2020-01-09 | NSH 5 @ CHI 2 | **Pekka Rinne** (empty-net) |
| 2022-23 | 2022020939 | 2023-02-25 | BOS 3 @ VAN 1 | **Linus Ullmark** (empty-net) |
| 2023-24 | 2023020345 | 2023-11-30 | PIT 4 @ TBL 2 | **Tristan Jarry** (empty-net) |
| 2024-25 | 2024020052 | 2024-10-15 | MIN 4 @ STL 1 | **Filip Gustavsson** (empty-net) |
| 2024-25 | 2024020720 | 2025-01-17 | PIT 5 @ BUF 2 | **Alex Nedeljkovic** (empty-net) |
| 2024-25 | 2024020949 | 2025-03-01 | NSH 4 @ NYI 7 | **Ilya Sorokin** (own-goal-empty-net) |

**Every one is a goal credited to a goaltender**, and `skater/summary` excludes
goaltenders by construction. This is a definitional boundary of the report, not a data
gap: the goals are real, they are in the team totals, and they are absent from the
skater table because no skater scored them.

Confirmed per game by cross-checking each game's scoring summary at
`https://api-web.nhle.com/v1/gamecenter/<gameId>/landing` and diffing the listed scorer
`playerId`s against the skater rows — in each case exactly one scorer was absent, and it
was the goalie named above.

If goalie scoring ever matters, `goalie/summary` with `isGame=true` is the companion
report; it was not fetched here because the archive's contract is skater and team rows.

## 5. Playoff brackets

All 11 present and parsed. Finals, read from each bracket's `playoffRound: 4` series:

| File | Series | Final |
|---|---|---|
| `bracket-2016.json` | 15 | PIT 4-2 SJS |
| `bracket-2017.json` | 15 | PIT 4-2 NSH |
| `bracket-2018.json` | 15 | WSH 4-1 VGK |
| `bracket-2019.json` | 15 | STL 4-3 BOS |
| `bracket-2020.json` | **23** | TBL 4-2 DAL |
| `bracket-2021.json` | 15 | TBL 4-1 MTL |
| `bracket-2022.json` | 15 | COL 4-2 TBL |
| `bracket-2023.json` | 15 | VGK 4-1 FLA |
| `bracket-2024.json` | 15 | FLA 4-3 EDM |
| `bracket-2025.json` | 15 | FLA 4-2 EDM |
| `bracket-2026.json` | 15 | **CAR 4-2 VGK** |

**The 2026 requirement is met: `bracket-2026.json` records the Stanley Cup Final as
Carolina 4 – Vegas 2, `winningTeamId: 12` (Carolina) — Carolina winning in six.** This
matches the app's own scoring and the ESPN odds archive independently
(`../odds-archive/PROVENANCE.md` §9 lists all six Final games, Carolina taking games 2,
4, 5 and 6).

2020's 23 series is the qualifying round, per §3.

## 6. Reproducing

`fetch_nhl.py <outdir>` re-fetches everything; `verify_nhl.py <outdir>` re-runs every
check in §3 and §4 and writes `_verify.json`. The fetch writes `_manifest.json` (per
season counts) and `_gaps.json` (empty in this run) alongside the data; those two are
working files and are not committed.
