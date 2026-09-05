# Provenance — MoneyPuck raw archive

Fetched **2026-09-04** from the public MoneyPuck download page
`https://moneypuck.com/data.htm`.

MoneyPuck's own attribution request on that page:

> The data below is free to use for non-commercial purposes and by journalists
> for ad-hoc use. Please clearly credit MoneyPuck.com in all cases where you
> are showing anything using our data as an input.

Politeness used for every fetch: **1 request/second, 4 attempts with exponential
backoff**. No retries were needed on the successful run documented here.

MoneyPuck redirected curl's default User-Agent to `data_license.htm` from both
the local host and a GitHub-hosted runner. The successful season-summary run
therefore used a transparent, non-browser project identifier:
`SportsNot/1.0 (+https://github.com/KyleBastien/sportsnot)`. Shot archives and
dictionaries were fetched earlier with curl's default User-Agent. This exception
is recorded explicitly rather than misrepresenting the requests.

Committed contents:

- raw season summaries under `season-summary/`
- raw shot archives and the two data dictionaries under `shots/`
- deterministic derived per-game aggregates under `game-aggregates/`
- the derivation script `aggregate_shots.py`

Byte totals added under `ml/data/raw/moneypuck/`:

- raw shots + dictionaries: **340,689,591** bytes
- season summaries: **41,290,742** bytes
- derived aggregates: **21,564,059** bytes
- **total:** **403,544,392** bytes

No individual shot archive exceeded the task's **45 MB** cap, so **no file was
split** and no `REASSEMBLE.md` was needed.

---

## 1. Exact URLs used

### 1.1 Season summaries

All **144** season-summary files used the direct CSV URL shape:

```text
https://moneypuck.com/moneypuck/playerData/seasonSummary/<startYear>/<type>/<table>.csv
```

The exact Cartesian expansion used was:

- `<startYear>`: every integer `2008` through `2025`, inclusive
- `<type>`: `regular`, `playoffs`
- `<table>`: `skaters`, `goalies`, `teams`, `lines`

Each response's effective URL was required to equal its requested URL and its
content type was required to start with `text/csv`. Files were streamed
unchanged into no-name gzip members; rows, headers, delimiters, line endings,
column order, and situation rows were not altered. The relative path below
`season-summary/` mirrors the final three URL components exactly. SHA256 for
every committed gzip is recorded in `season-summary/SHA256SUMS`.

### 1.2 Shot archives and dictionaries

Exact shot and dictionary URLs used:

| File | Rows | Size (bytes) | SHA256 | URL |
|---|---:|---:|---|---|
| `MoneyPuck_Shot_Data_Dictionary.csv` | -- | 15,680 | `ddf249e9e81372c45738fbb8f6d0e16f61ef78d81cd18dda4e4bb499dc7272de` | `https://peter-tanner.com/moneypuck/downloads/MoneyPuck_Shot_Data_Dictionary.csv` |
| `MoneyPuckDataDictionaryForPlayers.csv` | -- | 15,040 | `74c5a09f5eb5e12c03838c9efea0a84d9b33024193a1a29b9c67d998f5324a91` | `https://peter-tanner.com/moneypuck/downloads/MoneyPuckDataDictionaryForPlayers.csv` |
| `shots_2007.zip` | 106,243 | 17,326,497 | `609a4a7f0c0c5a959c7905a149ce001ab71fffff3f5925d692264612e4e021eb` | `https://peter-tanner.com/moneypuck/downloads/shots_2007.zip` |
| `shots_2008.zip` | 110,023 | 17,894,002 | `644fecc0eda9cad81302d805c6f9f4e90187aeb310ef2be5a2c0174e2019d1f2` | `https://peter-tanner.com/moneypuck/downloads/shots_2008.zip` |
| `shots_2009.zip` | 110,895 | 18,031,452 | `ecc304bbde48555911ca2238d855107d0e441420bf63a04f693375e0b792fb55` | `https://peter-tanner.com/moneypuck/downloads/shots_2009.zip` |
| `shots_2010.zip` | 111,405 | 18,152,357 | `ac349386948009dd8371de01b15ff60f5804d0788d4928d36d96e0bc3c8fb4c2` | `https://peter-tanner.com/moneypuck/downloads/shots_2010.zip` |
| `shots_2011.zip` | 108,753 | 17,728,382 | `0a2e806e689cf75f99744ae7c46c5966c3f4d8117b75202bfc18b3ba8665d703` | `https://peter-tanner.com/moneypuck/downloads/shots_2011.zip` |
| `shots_2012.zip` | 66,087 | 10,762,053 | `82b4c4fef37e3c90226e60fc01bb510e49a6033317a540965b3a9165f26a28fc` | `https://peter-tanner.com/moneypuck/downloads/shots_2012.zip` |
| `shots_2013.zip` | 110,682 | 18,019,104 | `b62b27d5773deb32020feac0760a72ac969fa845cf403f453ce3e0ed6b1b88f5` | `https://peter-tanner.com/moneypuck/downloads/shots_2013.zip` |
| `shots_2014.zip` | 109,627 | 17,821,400 | `ef8ecb85a012488f2f75a1508c0b9d9d6c3dceb9b6ea2c13eec1cd9824f0dd14` | `https://peter-tanner.com/moneypuck/downloads/shots_2014.zip` |
| `shots_2015.zip` | 109,461 | 17,805,570 | `718721085d5db9fb38c8527021081e6697be1399ce9fcb6237cf7c6075a86b37` | `https://peter-tanner.com/moneypuck/downloads/shots_2015.zip` |
| `shots_2016.zip` | 110,953 | 18,026,570 | `9348de6eccf42468879709e260fc6c81d1db2c6b4aec0249180a14e0554adddf` | `https://peter-tanner.com/moneypuck/downloads/shots_2016.zip` |
| `shots_2017.zip` | 119,715 | 19,406,466 | `ab44335541aa73889426533bd996172311c7742318a14caa908e1aab8db8257d` | `https://peter-tanner.com/moneypuck/downloads/shots_2017.zip` |
| `shots_2018.zip` | 117,622 | 18,915,571 | `017aec02cfdf2a7452ea94585cae79e81d09f02235dc9ea08532288c7ec2a333` | `https://peter-tanner.com/moneypuck/downloads/shots_2018.zip` |
| `shots_2019.zip` | 104,172 | 16,900,190 | `0ca5cbbd79b12e23f5080d37404ddae2e7766537556d6065b57a89a60dbef63e` | `https://peter-tanner.com/moneypuck/downloads/shots_2019.zip` |
| `shots_2020.zip` | 78,611 | 12,944,304 | `0208d43bd85e1eda547349dce4559988568e4445709d78621d1b90754e7d99e3` | `https://peter-tanner.com/moneypuck/downloads/shots_2020.zip` |
| `shots_2021.zip` | 121,471 | 19,917,589 | `f18506f384041d5c1ee8e2e0ec78c21cbdd5ac51e586cc115850b68605dd8b2d` | `https://peter-tanner.com/moneypuck/downloads/shots_2021.zip` |
| `shots_2022.zip` | 122,026 | 20,257,751 | `3eed5f66978468724a22c03ee3aeefdc0a9858cb673808b7b3aaa5b63e6fe017` | `https://peter-tanner.com/moneypuck/downloads/shots_2022.zip` |
| `shots_2023.zip` | 122,472 | 20,383,594 | `f28710f668baaa65756edd49e832ef96c835c2335ee6b955c18649403d6e6367` | `https://peter-tanner.com/moneypuck/downloads/shots_2023.zip` |
| `shots_2024.zip` | 119,870 | 20,138,716 | `0b0a1de7eec3ac62130ebb6da85020ef11a70be6307fafcb6b7b8963d3eb32be` | `https://peter-tanner.com/moneypuck/downloads/shots_2024.zip` |
| `shots_2025.zip` | 119,271 | 20,227,303 | `7863a4fc86ae226809d3272f40d1793946050759b862aa957b8459f6157b0f19` | `https://peter-tanner.com/moneypuck/downloads/shots_2025.zip` |

---

## 2. What was and was not available on the site

- This task's season-summary range starts at **2008-09**. MoneyPuck's browsable
  archive also contains a `2007/` directory, but it is outside the requested
  summary range.
- Every requested direct file for `2008-09..2025-26`, both types, and all four
  tables was available: **144 / 144**.
- Missing requested season-summary files on the site: **none**.

Season-summary row counts committed here:

| Season | Regular skaters | Regular goalies | Regular teams | Regular lines | Playoff skaters | Playoff goalies | Playoff teams | Playoff lines |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2008-09 | 4425 | 445 | 150 | 12778 | 1665 | 125 | 80 | 1867 |
| 2009-10 | 4395 | 415 | 150 | 13063 | 1710 | 135 | 80 | 2027 |
| 2010-11 | 4455 | 435 | 150 | 13209 | 1695 | 125 | 80 | 2023 |
| 2011-12 | 4470 | 445 | 150 | 13297 | 1740 | 115 | 80 | 1999 |
| 2012-13 | 4195 | 410 | 150 | 10132 | 1745 | 115 | 80 | 2002 |
| 2013-14 | 4430 | 485 | 150 | 12576 | 1720 | 140 | 80 | 2003 |
| 2014-15 | 4410 | 460 | 150 | 12095 | 1695 | 130 | 80 | 1837 |
| 2015-16 | 4490 | 460 | 150 | 12503 | 1700 | 140 | 80 | 1958 |
| 2016-17 | 4435 | 475 | 150 | 12371 | 1720 | 115 | 80 | 2082 |
| 2017-18 | 4450 | 475 | 155 | 12802 | 1665 | 145 | 80 | 1785 |
| 2018-19 | 4530 | 465 | 155 | 13443 | 1665 | 110 | 80 | 1912 |
| 2019-20 | 4415 | 425 | 155 | 2553 | 2580 | 210 | 120 | 457 |
| 2020-21 | 4565 | 490 | 155 | 2371 | 1685 | 120 | 80 | 290 |
| 2021-22 | 5015 | 595 | 160 | 3178 | 1675 | 150 | 80 | 302 |
| 2022-23 | 4755 | 535 | 160 | 2980 | 1670 | 140 | 80 | 311 |
| 2023-24 | 4620 | 490 | 160 | 2948 | 1695 | 135 | 80 | 306 |
| 2024-25 | 4600 | 515 | 160 | 3056 | 1660 | 135 | 80 | 287 |
| 2025-26 | 4700 | 490 | 160 | 3006 | 1735 | 125 | 80 | 285 |

Skater, goalie, and team summaries contain MoneyPuck's five situation rows:
`all`, `5on5`, `4on5`, `5on4`, and `other`. Line summaries contain `5on5`, as
served. Note the sharp drop in historical **regular** line-summary row counts from
`2019-20` onward (`2553`, `2371`, `3178`, `2980`, `2948`, `3056`). That is the
row count in MoneyPuck's direct files, not a processing bug introduced here.

---

## 3. ID conventions and aggregation rules

### 3.1 Game IDs

The shot archives do **not** carry the 10-digit NHL `gameId` directly. They carry
a **5-digit `game_id` suffix** such as `20001` or `30111`.

The committed `aggregate_shots.py` reconstructs the full NHL game id as:

```text
<seasonStartYear>0<game_id>
```

Examples:

- season `2023`, `game_id=20001` -> `2023020001`
- season `2023`, `game_id=30111` -> `2023030111`

That reconstruction covered **24,536 / 24,542** NHL-archive games
(`99.9756%`). The six archive games with no MoneyPuck shot rows are listed in
§6.

### 3.2 Team codes

MoneyPuck team codes are **not always the NHL archive abbreviations**:

- `L.A` instead of `LAK`
- `S.J` instead of `SJS`
- `T.B` instead of `TBL`
- `N.J` instead of `NJD`

Validation joins therefore use reconstructed `gameId` plus the home/road side,
not the MoneyPuck team code.

### 3.3 Situation and danger buckets

`aggregate_shots.py` follows MoneyPuck's own dictionaries:

- `5on5` = `homeSkatersOnIce == 5`, `awaySkatersOnIce == 5`, and neither
  `homeEmptyNet` nor `awayEmptyNet` is set (from the dictionaries' `situation`
  and skaters-on-ice definitions)
- **high-danger shot** = `xGoal > 0.20`
  - low danger `< 0.08`
  - medium danger `0.08..0.20`
  - high danger `> 0.20`

The aggregate files write **all-situations** and **5-on-5** metrics.

### 3.4 Empty nets, rebounds, rushes, penalty shots, and on-ice ids

- **shots** = rows where `shotWasOnGoal == 1`
- **unblocked shots** = every row in the shot file (the page states blocked shots
  are not included)
- **rebound shots** = `shotRebound == 1`
- **rush shots** = `shotRush == 1`
- **empty-net shots** are identified by `shotOnEmptyNet == 1`
  - kept in team and skater aggregates
  - excluded from goalie aggregates because the shot dictionary says empty-net
    rows have a blank goalie id/name
- the shot files do **not** expose on-ice skater id columns, so no on-ice xG
  skater aggregates are emitted
- the shot dictionary exposes **no dedicated penalty-shot flag**, so no
  penalty-shot-specific metric is derived; rows are aggregated exactly as served

### 3.5 Duplicate source events

MoneyPuck's raw archives contain **1,541 duplicated game-event keys** whose
rows are identical in every aggregation field but have distinct `shotID`
values:

- 2007-08: 1,297 keys across 22 games
- 2008-09: 242 keys across 3 games
- 2012-13: 1 key
- 2018-19: 1 key

The script identifies an event by the shot dictionary's game-local event number,
`(season, game_id, id)`, verifies every duplicated key has identical aggregation
values, and keeps one row. It fails rather than guessing if duplicate values
conflict. Without this guard, one example (`2007020001`) doubled every shot and
goal; the corrected MoneyPuck totals are ANA 1 and L.A 4.

### 3.5 Determinism

`aggregate_shots.py`:

- reads only the committed `shots_*.zip` files (or future split parts, if ever
  needed)
- sorts output deterministically by `gameId`, `teamCode`, and player/goalie id
- writes LF CSVs inside gzip members with **`mtime=0`**

The full aggregate run was executed **twice** and the SHA256 of all
**57 output files** matched exactly across reruns.

---

## 4. Aggregate outputs

Command used:

```bash
cd ml
uv run python data/raw/moneypuck/aggregate_shots.py data/raw/moneypuck/shots data/raw/moneypuck/game-aggregates
```

Per-season aggregate rows and validation coverage:

| Season | Shot rows | Team agg rows | Skater agg rows | Goalie agg rows | Game coverage | Player coverage | Goal mismatches |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2007-08 | 106,243 | 2,630 | 38,353 | 2,782 | 1315/1315 (100.0000%) | 836/854 (97.8923%) | 39 |
| 2008-09 | 110,023 | 2,628 | 39,077 | 2,823 | 1314/1317 (99.7722%) | 861/888 (96.9595%) | 23 |
| 2009-10 | 110,895 | 2,636 | 39,303 | 2,847 | 1318/1319 (99.9242%) | 857/880 (97.3864%) | 16 |
| 2010-11 | 111,405 | 2,636 | 39,593 | 2,847 | 1318/1319 (99.9242%) | 875/892 (98.0942%) | 28 |
| 2011-12 | 108,753 | 2,632 | 39,400 | 2,823 | 1316/1316 (100.0000%) | 875/897 (97.5474%) | 27 |
| 2012-13 | 66,087 | 1,612 | 24,155 | 1,745 | 806/806 (100.0000%) | 820/843 (97.2716%) | 9 |
| 2013-14 | 110,682 | 2,646 | 39,713 | 2,852 | 1323/1323 (100.0000%) | 875/888 (98.5360%) | 21 |
| 2014-15 | 109,627 | 2,638 | 39,984 | 2,834 | 1319/1319 (100.0000%) | 862/883 (97.6217%) | 14 |
| 2015-16 | 109,461 | 2,642 | 39,982 | 2,840 | 1321/1321 (100.0000%) | 881/900 (97.8889%) | 17 |
| 2016-17 | 110,953 | 2,634 | 40,272 | 2,835 | 1317/1317 (100.0000%) | 876/891 (98.3165%) | 13 |
| 2017-18 | 119,715 | 2,710 | 42,048 | 2,941 | 1355/1355 (100.0000%) | 876/890 (98.4270%) | 20 |
| 2018-19 | 117,622 | 2,716 | 41,954 | 2,906 | 1358/1358 (100.0000%) | 896/910 (98.4615%) | 25 |
| 2019-20 | 104,172 | 2,424 | 37,376 | 2,617 | 1212/1212 (100.0000%) | 880/890 (98.8764%) | 21 |
| 2020-21 | 78,611 | 1,904 | 29,144 | 2,026 | 952/952 (100.0000%) | 896/917 (97.7099%) | 9 |
| 2021-22 | 121,471 | 2,800 | 42,956 | 3,009 | 1400/1401 (99.9286%) | 985/1006 (97.9125%) | 9 |
| 2022-23 | 122,026 | 2,800 | 43,027 | 2,980 | 1400/1400 (100.0000%) | 935/953 (98.1112%) | 17 |
| 2023-24 | 122,472 | 2,800 | 42,831 | 2,977 | 1400/1400 (100.0000%) | 902/925 (97.5135%) | 17 |
| 2024-25 | 119,870 | 2,796 | 42,711 | 2,962 | 1398/1398 (100.0000%) | 903/924 (97.7273%) | 7 |
| 2025-26 | 119,271 | 2,788 | 42,498 | 2,942 | 1394/1394 (100.0000%) | 926/940 (98.5106%) | 7 |

Interpretation:

- **game coverage** is the fraction of NHL-archive game ids that appear in the
  team aggregates
- **player coverage** is the fraction of NHL-archive skater player ids that
  appear in the skater aggregates at least once
- skater coverage is **below 100% by design** because some archive skaters never
  record a shot event in the MoneyPuck shot file

---

## 5. Checksums re-run after writing the committed files

After the files were written into the repo tree, SHA256 was recomputed for every
committed shot archive and both committed dictionaries. Every recomputed value
matched the table in §1.2 exactly.

No shot archive was re-zipped, re-saved, or transformed in place.

---

## 6. Games in the NHL archive with no MoneyPuck shot rows

Six NHL-archive games were missing from the MoneyPuck shot coverage:

| Season | Game ID | Date | Road team | Home team | Score |
|---|---|---|---|---|---|
| 2008-09 | `2008020259` | 2008-11-17 | Boston Bruins | Toronto Maple Leafs | 3 @ 2 |
| 2008-09 | `2008020409` | 2008-12-10 | Calgary Flames | Detroit Red Wings | 3 @ 4 |
| 2008-09 | `2008021077` | 2009-03-21 | Vancouver Canucks | Phoenix Coyotes | 1 @ 5 |
| 2009-10 | `2009020081` | 2009-10-14 | Pittsburgh Penguins | Carolina Hurricanes | 2 @ 2 |
| 2010-11 | `2010030417` | 2011-06-15 | Boston Bruins | Vancouver Canucks | 4 @ 0 |
| 2021-22 | `2021021028` | 2022-03-25 | Washington Capitals | Buffalo Sabres | 3 @ 3 |

---

## 7. Goals reconciliation against the NHL archive

Compared metric: MoneyPuck `allGoalsFor` per team-game versus the committed NHL
archive's `goalsFor`.

Important caveat from the task prompt and MoneyPuck source behavior:

- **shootout goals are not shot events**, so shootout-final mismatches are
  expected
- the MoneyPuck shot files do **not** expose a reliable shootout flag for every
  season, so the "shootout-expected" classification below was derived from the
  NHL archive, not the MoneyPuck rows

Per-season mismatch counts are in the table in §4. Total mismatches:

- **339 / 49,072** joined team-game rows
- **26** mismatches are on NHL-archive shootout games; **313** are other source
  differences
- the largest cluster is **2007-08** (`39` mismatches)
- most later-season mismatches are **+1** versus the NHL archive

Representative mismatch examples (10 total):

| Season | Game ID | Date | Side | Team | Opponent | MoneyPuck goals | NHL archive goals | Difference | Shootout game |
|---|---|---|---|---|---|---:|---:|---:|---|
| 2007-08 | `2007020127` | 2007-10-24 | H | CAR | BUF | 3 | 6 | -3 | no |
| 2007-08 | `2007020141` | 2007-10-26 | H | CAR | MTL | 3 | 4 | -1 | no |
| 2007-08 | `2007020150` | 2007-10-27 | H | PIT | MTL | 2 | 3 | -1 | yes |
| 2007-08 | `2007020152` | 2007-10-27 | R | FLA | NSH | 2 | 3 | -1 | no |
| 2007-08 | `2007020160` | 2007-10-29 | R | T.B | NYR | 0 | 1 | -1 | no |
| 2007-08 | `2007020212` | 2007-11-06 | H | OTT | TOR | 4 | 5 | -1 | no |
| 2007-08 | `2007020371` | 2007-12-01 | R | NYR | OTT | 4 | 5 | -1 | no |
| 2007-08 | `2007020371` | 2007-12-01 | H | OTT | NYR | 1 | 2 | -1 | no |
| 2007-08 | `2007020433` | 2007-12-09 | R | STL | COL | 4 | 5 | -1 | no |
| 2007-08 | `2007020436` | 2007-12-10 | R | ANA | CBJ | 3 | 4 | -1 | no |

`Difference` is MoneyPuck minus NHL. Shootout-final discrepancies are expected
because shootout goals are not MoneyPuck shot events; other mismatches are
reported as source differences, not silently repaired.
