# Provenance — NHL API historical archive

Initial snapshot fetched **2026-08-26** from the public NHL APIs (no auth). It covered
seasons **2015-16 through 2025-26**, regular season and playoffs (`gameTypeId` 2 and
3). A **2026-09-04** extension (see §7) backfilled **2007-08 through 2014-15** and
added `game-times-<season>.csv.gz` for **2007-08 through 2025-26**.

Current committed contents: 19 seasons of `team-games`, `skater-games`, and
`skater-bios`; 19 seasons of `game-times`; 19 playoff brackets; the fetch scripts
(`fetch_nhl.py`, `fetch_game_times.py`) and the verification script
(`verify_nhl.py`). `fetch_nhl.py` was refactored after the original run (functions
extracted, behavior identical) to satisfy the repo's CodeScene gate; the byte-exact run
version is in git history at the commit that added the first archive snapshot.

**No gaps. No imputation.** Every request succeeded, `_gaps.json` came back empty, and
every field written is a field the API returned. The only reconciliation discrepancies
in the whole archive are nine goalie-scored-goal games, documented in §4 and §7.3.

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

## 7. 2026-09 extension: 2007-08..2014-15 + game times

Extension fetched **2026-09-04** into a scratch directory outside the repo, then copied
into `ml/data/raw/nhl-archive/`. Existing `2015-16..2025-26` team/skater/bios files
were left byte-identical in git; only the eight older seasons, eight older brackets,
and the new `game-times-<season>.csv.gz` files were added.

### 7.1 Requests and scripts

#### `fetch_nhl.py`

- `SEASONS` widened from `range(2015, 2026)` to `range(2007, 2026)`; no other behavior
  change.
- Run against scratch output only.
- **279 HTTP requests total** across all 19 seasons.
  - **116** served the eight newly committed seasons (`2007-08..2014-15`).
  - **163** re-fetched the unchanged `2015-16..2025-26` baseline into scratch.
- **0 retries, 0 failures, 0 gaps, 0 10,000-row cap hits, 0 half-month re-splits.**
  The month partitioning described in §1 still kept every skater query under the cap.

#### `fetch_game_times.py`

New script: `ml/data/raw/nhl-archive/fetch_game_times.py`.

- Primary source:

  ```
  GET https://api-web.nhle.com/v1/club-schedule-season/<TEAM>/<seasonId>
  ```

- One request per active team-season, where the active team abbreviations are derived
  from paired `team-games` rows: each row's own abbreviation is the *other* row's
  `opponentTeamAbbrev`, because `team-games` exposes the row team as `teamId` +
  `teamFullName` but not as an abbreviation.
- Keep only `gameTypeId` 2 and 3, dedupe on `gameId`, and write:
  `gameId,seasonId,gameTypeId,gameDate,startTimeUTC,venue,venueCity,homeAbbrev,awayAbbrev,neutralSite`.
- The schedule payload does **not** include `venueLocation`, so for neutral-site games
  the script fills `venueCity` from:

  ```
  GET https://api-web.nhle.com/v1/gamecenter/<gameId>/landing
  ```

- **584** logical schedule requests + **216** neutral-site landing lookups =
  **800 HTTP requests total**.
- **0 retries, 0 failures.**

### 7.2 Per-season counts

`verify_nhl.py` on the scratch output wrote `_verify.json`. `fetch_game_times.py` wrote
`_game_times_manifest.json`. Counts below are the committed archive after the extension:

| Season | Reg games | PO games | Team rows | Skater rows | Bios | Game-times |
|---|---:|---:|---:|---:|---:|---:|
| 2007-08 | 1 230 | 85 | 2 630 | 47 326 | 854 | 1 315 |
| 2008-09 | 1 230 | 87 | 2 634 | 47 390 | 888 | 1 317 |
| 2009-10 | 1 230 | 89 | 2 638 | 47 475 | 880 | 1 319 |
| 2010-11 | 1 230 | 89 | 2 638 | 47 466 | 892 | 1 319 |
| 2011-12 | 1 230 | 86 | 2 632 | 47 371 | 897 | 1 316 |
| 2012-13 | 720 | 86 | 1 612 | 29 014 | 843 | 806 |
| 2013-14 | 1 230 | 93 | 2 646 | 47 624 | 888 | 1 323 |
| 2014-15 | 1 230 | 89 | 2 638 | 47 478 | 883 | 1 319 |
| 2015-16 | 1 230 | 91 | 2 642 | 47 553 | 900 | 1 321 |
| 2016-17 | 1 230 | 87 | 2 634 | 47 406 | 891 | 1 317 |
| 2017-18 | 1 271 | 84 | 2 710 | 48 780 | 890 | 1 355 |
| 2018-19 | 1 271 | 87 | 2 716 | 48 887 | 910 | 1 358 |
| 2019-20 | 1 082 | 130 | 2 424 | 43 630 | 890 | 1 212 |
| 2020-21 | 868 | 84 | 1 904 | 34 250 | 917 | 952 |
| 2021-22 | 1 312 | 89 | 2 802 | 50 412 | 1 006 | 1 401 |
| 2022-23 | 1 312 | 88 | 2 800 | 50 376 | 953 | 1 400 |
| 2023-24 | 1 312 | 88 | 2 800 | 50 389 | 925 | 1 400 |
| 2024-25 | 1 312 | 86 | 2 796 | 50 320 | 924 | 1 398 |
| 2025-26 | 1 312 | 82 | 2 788 | 50 182 | 940 | 1 394 |
| **total** | **22 842** | **1 700** | **49 084** | **883 329** | **17 171** | **24 542** |

### 7.3 Verification outcomes

- `verify_nhl.py` reconciled **24,533 / 24,542** games exactly. The only nine misses are
  goalie-scored goals excluded by `skater/summary`: the six already documented in §4,
  plus three new ones from the older seasons.
- Every game in every `team-games-<season>.csv.gz` file appears **exactly once** in the
  matching `game-times-<season>.csv.gz` file.
- Game-times validation found **0 missing gameIds, 0 extra gameIds, 0 blank
  `startTimeUTC` values, 0 duplicate disagreements, and 0 neutral-site rows missing a
  `venueCity` fill** across all 19 seasons.
- All 19 brackets parsed successfully. No year needed derivation from team-games rows.

New reconciliation exceptions added by the 2007-08..2014-15 backfill:

| Season | gameId | Date | Score | Missing scorer |
|---|---|---|---|---|
| 2011-12 | 2011020522 | 2011-12-26 | New Jersey Devils 2 @ Carolina Hurricanes 4 | **Cam Ward** (empty-net) |
| 2012-13 | 2012020446 | 2013-03-21 | New Jersey Devils 4 @ Carolina Hurricanes 1 | **Martin Brodeur** (empty-net) |
| 2013-14 | 2013020120 | 2013-10-19 | Detroit Red Wings 2 @ Phoenix Coyotes 5 | **Mike Smith** (empty-net) |

### 7.4 Bracket provenance

Older brackets all came straight from the API endpoint; none were hand-derived:

| Year | Source | Series | Final |
|---|---|---:|---|
| 2008 | `/v1/playoff-bracket/2008` | 15 | DET 4-2 PIT |
| 2009 | `/v1/playoff-bracket/2009` | 15 | DET 3-4 PIT |
| 2010 | `/v1/playoff-bracket/2010` | 15 | CHI 4-2 PHI |
| 2011 | `/v1/playoff-bracket/2011` | 15 | VAN 3-4 BOS |
| 2012 | `/v1/playoff-bracket/2012` | 15 | NJD 2-4 LAK |
| 2013 | `/v1/playoff-bracket/2013` | 15 | CHI 4-2 BOS |
| 2014 | `/v1/playoff-bracket/2014` | 15 | LAK 4-1 NYR |
| 2015 | `/v1/playoff-bracket/2015` | 15 | TBL 2-4 CHI |

### 7.5 New team abbreviations and anomalies

- Team abbreviations present in the new seasons but not in the committed `2015+`
  archive files: **ATL**, **PHX**.
- **2012-13** is the lockout-shortened season: **720** regular-season games and **806**
  total game-times rows. Verified, not a gap.
- **2019-20** bubble check passed: the API reports `neutralSite=true` for **all 130
  playoff games**. That season has **136** neutral-site games total because six
  regular-season games were neutral-site as well.

## 8. 2026-09 deployment extension: TOI, power play, and goalie games

Fetched **2026-09-05** from the public NHL stats REST API with the committed
`fetch_toi.py`. Coverage is every regular-season and playoff game in the existing
2007-08 through 2025-26 archive. No authentication was used.

After the fetch, `fetch_toi.py` and `verify_toi.py` were refactored into smaller
helpers to satisfy the CodeScene code-health gate. A full cache/output resume changed
**0 of 57 gzip files**, and the verifier reproduced the same aggregate results below.

### 8.1 Exact endpoints and partitioning

Skater time on ice:

```text
GET https://api.nhle.com/stats/rest/en/skater/timeonice
    ?isGame=true
    &limit=-1
    &start=0
    &cayenneExp=seasonId=<yyyyYYYY> and gameTypeId=<2|3>
                and gameDate>="<YYYY-MM-01>" and gameDate<="<YYYY-MM-DD>"
```

Skater power play:

```text
GET https://api.nhle.com/stats/rest/en/skater/powerplay
    ?isGame=true
    &limit=-1
    &start=0
    &cayenneExp=seasonId=<yyyyYYYY> and gameTypeId=<2|3>
                and gameDate>="<YYYY-MM-01>" and gameDate<="<YYYY-MM-DD>"
```

Goalie games:

```text
GET https://api.nhle.com/stats/rest/en/goalie/summary
    ?isGame=true
    &limit=-1
    &start=0
    &cayenneExp=seasonId=<yyyyYYYY> and gameTypeId=<2|3>
```

Skater reports use the same calendar-month partitioning as `fetch_nhl.py`. Months come
from committed `game-times-<season>.csv.gz` rows for each game type. Both the declared
`total` and returned `data` length are checked against the 10,000-row cap; a capped
month automatically splits into days 1-15 and 16-end-of-month, and each half is checked
again. Goalie reports fit below the cap at season/game-type granularity; the script
falls back to the same month partitioning if either cap check fires.

Run totals:

- **406** requests: 368 skater month partitions + 38 goalie season/game-type reports
- **0** retries, **0** failures, **0** gaps
- **0** cap hits and **0** half-month splits
- largest partition: **8,712 rows** (2025-26 regular season, March 2026)
- politeness: curl-based GET, **1 request/second**, four attempts with exponential
  backoff

### 8.2 Output columns and source behavior

`skater-toi-<season>.csv.gz` keeps identifiers, game date, team/opponent/home-road,
position, handedness, `evTimeOnIce`, `ppTimeOnIce`, `shTimeOnIce`, `otTimeOnIce`,
`shifts`, and `timeOnIce`.

`skater-pp-<season>.csv.gz` keeps the same identifiers plus `ppGoals`, `ppAssists`,
`ppPoints`, `ppShots`, `ppTimeOnIce`, and `ppIndividualSatFor`.

`goalie-games-<season>.csv.gz` keeps identifiers, game date, team/opponent/home-road,
`gamesStarted`, `timeOnIce`, `shotsAgainst`, `goalsAgainst`, `saves`, `savePct`,
`shutouts`, and the one-game win/loss fields. The endpoint does not return a `decision`
field. `fetch_toi.py` deterministically derives it as `W`, `L`, or `OTL` from the
served `wins`, `losses`, and `otLosses`; goalies with no decision remain blank.

The API's `evTimeOnIce` already includes `otTimeOnIce`. Therefore the exhaustive sum is
`evTimeOnIce + ppTimeOnIce + shTimeOnIce = timeOnIce`; adding `otTimeOnIce` again would
double-count overtime. `otTimeOnIce` is retained as the useful subset the API serves.

All CSVs use LF line endings, stable `(gameId, teamAbbrev, playerId)` ordering, and gzip
members with `mtime=0`. Total compressed size for the 57 files is **33,046,794 bytes**.

### 8.3 Per-season counts

| Season | Skater TOI | Skater PP | Goalie rows | TOI diff | PP diff |
|---|---:|---:|---:|---:|---:|
| 2007-08 | 47,326 | 47,326 | 2,847 | 0 | 0 |
| 2008-09 | 47,390 | 47,390 | 2,834 | 0 | 0 |
| 2009-10 | 47,475 | 47,475 | 2,851 | 0 | 0 |
| 2010-11 | 47,466 | 47,466 | 2,854 | 0 | 0 |
| 2011-12 | 47,371 | 47,371 | 2,829 | 0 | 0 |
| 2012-13 | 29,014 | 29,014 | 1,747 | 0 | 0 |
| 2013-14 | 47,624 | 47,624 | 2,850 | 0 | 0 |
| 2014-15 | 47,478 | 47,478 | 2,835 | 0 | 0 |
| 2015-16 | 47,553 | 47,553 | 2,843 | 0 | 0 |
| 2016-17 | 47,406 | 47,406 | 2,842 | 0 | 0 |
| 2017-18 | 48,780 | 48,780 | 2,945 | 0 | 0 |
| 2018-19 | 48,887 | 48,887 | 2,901 | 0 | 0 |
| 2019-20 | 43,630 | 43,630 | 2,583 | 0 | 0 |
| 2020-21 | 34,250 | 34,250 | 2,026 | 0 | 0 |
| 2021-22 | 50,412 | 50,412 | 3,014 | 0 | 0 |
| 2022-23 | 50,376 | 50,376 | 2,983 | 0 | 0 |
| 2023-24 | 50,389 | 50,389 | 2,979 | 0 | 0 |
| 2024-25 | 50,320 | 50,320 | 2,953 | 0 | 0 |
| 2025-26 | 50,182 | 50,182 | 2,942 | 0 | 0 |
| **total** | **883,329** | **883,329** | **52,658** | **0** | **0** |

`TOI diff` and `PP diff` compare each new skater report with the matching committed
`skater-games` season row count.

### 8.4 Validation

`verify_toi.py` produced these full-archive checks:

- skater TOI rows versus `skater-games`: **883,329 / 883,329**, difference **0**
- skater PP rows versus `skater-games`: **883,329 / 883,329**, difference **0**
- `timeOnIce` versus `skater-games.timeOnIcePerGame` within one second:
  **883,329 / 883,329 (100.000%)**
- `ev + pp + sh` versus `timeOnIce` within two seconds:
  **883,329 / 883,329 (100.000%)**
- goalie game-team groups: **49,084** (two for every one of 24,542 games)
- groups whose `gamesStarted` sum is exactly one: **49,084 / 49,084 (100.000%)**
- goalie starter exceptions: **0**

No values were imputed. Reproduce with:

```text
cd ml
.venv/Scripts/python.exe data/raw/nhl-archive/fetch_toi.py data/raw/nhl-archive
.venv/Scripts/python.exe data/raw/nhl-archive/verify_toi.py data/raw/nhl-archive
```
