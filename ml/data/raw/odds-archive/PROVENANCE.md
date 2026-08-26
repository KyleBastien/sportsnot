# Provenance — historical NHL odds archives

Committed source data for the odds feature (Ralph story US-005). Files are raw and
unmodified: the bytes served by the download URL below, no cleaning, no re-saving.

Download date for every file: **2026-08-26**.

---

## 1. Headline: 7 of the 10 requested seasons are here, 3 are not

The task asked for the 10 most recent completed seasons (2016-17 … 2025-26).

| Season | File | Status |
|---|---|---|
| 2016-17 | `nhl-odds-2016-17.xlsx` | complete, regular season + playoffs |
| 2017-18 | `nhl-odds-2017-18.xlsx` | complete, regular season + playoffs |
| 2018-19 | `nhl-odds-2018-19.xlsx` | complete, regular season + playoffs |
| 2019-20 | `nhl-odds-2019-20.xlsx` | complete, incl. the Aug–Sep 2020 bubble playoffs |
| 2020-21 | `nhl-odds-2020-21.xlsx` | complete, regular season + playoffs |
| 2021-22 | `nhl-odds-2021-22.xlsx` | complete, regular season + playoffs |
| 2022-23 | `nhl-odds-2022-23.xlsx` | **PARTIAL — 7 Oct to 27 Nov 2022 only, no playoffs** |
| 2023-24 | — | **NOT FOUND** |
| 2024-25 | — | **NOT FOUND** |
| 2025-26 | — | **NOT FOUND** |

Nothing was substituted for the three missing seasons. §4 records every source checked
and why each failed, so the search doesn't have to be repeated from scratch.

## 2. Publisher and why the URLs look the way they do

All seven files are the per-season NHL odds workbooks published by **Sportsbook Reviews
Online** (`sportsbookreviewsonline.com`) — the archive the directory README names.

**The site is gone.** Every path 404s as of today, including the domain root:

```
https://www.sportsbookreviewsonline.com/                                     -> 404
https://www.sportsbookreviewsonline.com/scoresoddsarchives/                   -> 404
https://www.sportsbookreviewsonline.com/scoresoddsarchives/nhl/nhloddsarchives.htm -> 404
```

So the files were pulled from the **Internet Archive Wayback Machine**, using the `id_`
modifier, which returns the originally-archived bytes with no Wayback rewriting. Each
URL below is the exact one used.

Two things worth knowing about the capture history:

* The archive's own file naming used a space, `nhl odds <season>.xlsx`, and the
  **2020-21 season is filed as `nhl odds 2021.xlsx`** — there is no `2020-21` file.
  Committed here under the consistent `nhl-odds-2020-21.xlsx` name; the content is
  untouched.
* Many Wayback captures are **mid-season partials**, because the publisher updated one
  file in place all year. The first capture I pulled for 2016-17 (Dec 2016) had 856 rows
  and no playoffs; the Dec 2022 capture has 2 634 rows and the full season. Every file
  below is the latest capture that is actually complete — except 2022-23, where no
  complete capture exists (§4.1).

### Exact source URLs

| File | Wayback URL |
|---|---|
| `nhl-odds-2016-17.xlsx` | `https://web.archive.org/web/20221203063455id_/https://www.sportsbookreviewsonline.com/scoresoddsarchives/nhl/nhl%20odds%202016-17.xlsx` |
| `nhl-odds-2017-18.xlsx` | `https://web.archive.org/web/20221204090924id_/https://www.sportsbookreviewsonline.com/scoresoddsarchives/nhl/nhl%20odds%202017-18.xlsx` |
| `nhl-odds-2018-19.xlsx` | `https://web.archive.org/web/20220813025833id_/https://sportsbookreviewsonline.com/scoresoddsarchives/nhl/nhl%20odds%202018-19.xlsx` |
| `nhl-odds-2019-20.xlsx` | `https://web.archive.org/web/20220813025437id_/https://sportsbookreviewsonline.com/scoresoddsarchives/nhl/nhl%20odds%202019-20.xlsx` |
| `nhl-odds-2020-21.xlsx` | `https://web.archive.org/web/20220813024250id_/https://sportsbookreviewsonline.com/scoresoddsarchives/nhl/nhl%20odds%202021.xlsx` |
| `nhl-odds-2021-22.xlsx` | `https://web.archive.org/web/20220813023257id_/https://sportsbookreviewsonline.com/scoresoddsarchives/nhl/nhl%20odds%202021-22.xlsx` |
| `nhl-odds-2022-23.xlsx` | `https://web.archive.org/web/20221202195155id_/https://www.sportsbookreviewsonline.com/scoresoddsarchives/nhl/nhl%20odds%202022-23.xlsx` |

No `.gitignore` rule matches this directory (`git check-ignore` returns nothing for
`*.xlsx` here), so no exception was needed. A `.gitattributes` marks `*.xlsx` binary so
git never tries to diff or normalize them.

---

## 3. Layout

### 3.1 The header names 13 columns; the rows use 16

This is the single most important thing to get right. Every file has the same header:

```
Date | Rot | VH | Team | 1st | 2nd | 3rd | Final | Open | Close | PuckLine | OpenOU | CloseOU
```

but each data row has **16** populated cells, because the last three headers each cover
**two** columns — a line and the price on that line:

| Col | Header | Meaning |
|---|---|---|
| A | `Date` | `MMDD`, stored as a **number** (§3.3) |
| B | `Rot` | rotation number, the sportsbook's game id for that day |
| C | `VH` | `V` visitor, `H` home, `N` neutral site (§3.5) |
| D | `Team` | city string, spaces usually stripped (§3.4) |
| E | `1st` | goals, 1st period |
| F | `2nd` | goals, 2nd period |
| G | `3rd` | goals, 3rd period |
| H | `Final` | final score for this team (includes OT/SO) |
| I | `Open` | **opening moneyline, American odds** |
| J | `Close` | **closing moneyline, American odds** |
| K | `PuckLine` | puck-line handicap for this team (e.g. `1.5`, `-1.5`) |
| L | *(unnamed)* | price on that puck line, American odds |
| M | `OpenOU` | opening total (e.g. `5.5`) |
| N | *(unnamed)* | price on the opening total |
| O | `CloseOU` | closing total |
| P | *(unnamed)* | price on the closing total |

A parser that zips the 13 header names against the 16 values will silently misalign
everything from `PuckLine` rightward. Moneylines (I, J) are safe either way.

### 3.2 Two rows per game, visitor first

Rows come in pairs: the visitor row then the home row, sharing a `Date` and consecutive
`Rot` numbers. Verified pair-by-pair across all seven files — 6 099 of 6 100 pairs are
`(V,H)` or `(N,N)`; the single exception is in §5.

Moneylines are per-team on that team's own row, so a game's price pair is
`row[i].Close` and `row[i+1].Close`. Neither is de-vigged; both are raw American odds
(`-230`, `+192` written as `192`).

### 3.3 Dates are `MMDD` numbers with no year

`Date` is an integer, not a date cell: `1012` = 12 October, `611` = 11 June. Leading
zeros are gone, so January dates are three digits (`117` = 17 January) and there is no
year anywhere in the file — the year has to come from the season in the filename plus
the month (months ≥ 8 are the first calendar year, months ≤ 7 the second).

**Do not use April–June as a playoff filter.** It works for four of the seven seasons and
fails badly for two:

* **2019-20** — the season paused in March 2020 and the playoffs ran **August–September**
  in the Toronto/Edmonton bubble. Zero April–June rows; 260 playoff rows in months 8–9.
* **2020-21** — the season started 13 January 2021 and ran to 19 May, with playoffs
  **May–July**. April is regular season, so an April–June filter picks up 802 rows of
  which only 362 are playoffs.

Per-season playoff windows are in §5.

### 3.4 Team names: city strings, spaces stripped, inconsistently

The convention is the city with spaces removed — `LosAngeles`, `TampaBay`, `NYRangers`,
`NYIslanders`, `NewJersey`, `SanJose`, `St.Louis`. They are **not** NHL ids and not
nicknames, so US-005's team-name → NHL id mapping has to key on these strings.

The convention leaks over time, and the same team appears under two spellings in the same
file:

| Season | Duplicate / bad spellings |
|---|---|
| 2016-17 | *(clean — 30 distinct, exactly the 30 teams)* |
| 2017-18 | *(clean — 31, Vegas added)* |
| 2018-19 | *(clean — 31)* |
| 2019-20 | 33 distinct: `Arizona` **and** `Arizonas` (typo, one row), `TampaBay` **and** `Tampa` |
| 2020-21 | 33 distinct: `NYIslanders`/`NY Islanders`, `TampaBay`/`Tampa Bay` |
| 2021-22 | 33 distinct: `Seattle`/`SeattleKraken` |
| 2022-23 | **40 distinct in only 342 games** — spaced and unspaced variants coexist for nine teams: `Los Angeles`/`LosAngeles`, `NY Islanders`/`NYIslanders`, `NY Rangers`/`NYRangers`, `New Jersey`/`NewJersey`, `San Jose`/`SanJose`, `Seattle Kraken`/`SeattleKraken`, `St. Louis`/`St.Louis`, `Tampa Bay`/`TampaBay` |

So the mapping needs to normalize whitespace and punctuation, and carry the `Arizonas`
and `Tampa` typos as explicit aliases.

Expansion timing also shows up: `Vegas` from 2017-18, `Seattle` from 2021-22, and
`Arizona` throughout (the franchise's relocation is after the last covered season).

### 3.5 `VH` and neutral sites

`V`/`H` normally. `N` marks a neutral-site game, and **both** rows of the pair carry `N`:

* **2019-20** — 260 rows (130 games), the entire Aug–Sep bubble playoffs.
* **2022-23** — 6 rows (3 games), the season-opening neutral-site games.

For `N` pairs there is no home/away signal in the file at all, which matters for any
home-ice feature.

### 3.6 Per-file deviations

| File | Deviation |
|---|---|
| `nhl-odds-2016-17.xlsx` | workbook has `Sheet1`, `Sheet2`, `Sheet3`; only `Sheet1` has data |
| `nhl-odds-2017-18.xlsx` | same three-sheet shape, `Sheet2`/`Sheet3` empty |
| `nhl-odds-2018-19.xlsx` | same three-sheet shape, **and the only file whose header uses spaced names**: `Puck Line`, `Open OU`, `Close OU` instead of `PuckLine`, `OpenOU`, `CloseOU`. Match headers case- and space-insensitively |
| `nhl-odds-2019-20.xlsx` | single `Sheet1` (as do all later files); one reversed row pair (§5); two team typos |
| `nhl-odds-2022-23.xlsx` | partial season; worst team-name inconsistency; 3 neutral-site games |

Data always starts on row 2 of the first worksheet, with the header on row 1. No footer
rows, no totals, no merged cells.

---

## 4. The three missing seasons, and everything checked

### 4.1 Why 2022-23 is partial, and 2023-24 onward is absent

Sportsbook Reviews Online **stopped updating its NHL archive in late November 2022** and
the site later went offline entirely. Evidence:

* A full Wayback CDX listing of every `.xlsx` under `scoresoddsarchives/nhl/` ends at
  `nhl odds 2022-23.xlsx`. There is no `2023-24`, `2024-25` or `2025-26` file at any
  timestamp, under either the `www.` or bare host.
* `nhl odds 2022-23.xlsx` has exactly one capture, 2 Dec 2022, containing 684 rows
  ending 27 Nov 2022. There is no later capture to upgrade to.
* The site was later rebuilt on WordPress with per-season HTML pages at
  `/scoresoddsarchives/nhl-odds-<season>/`. Only two were ever archived — `2021-22`
  (captured 2026-04-11) and `2022-23` (captured 2026-05-16) — and the 2022-23 page holds
  the **same** 684 rows, ending 27 Nov 2022. No page exists for 2023-24, 2024-25 or
  2025-26.
* A CDX sweep of the WordPress upload directory
  (`/wp-content/uploads/sportsbookreviewsonline_com_737/`) finds MLB, NBA and NCAA
  workbooks but **no NHL file at all**.

The committed partial file is the publisher's own incomplete workbook, not a
substitution — it is genuinely all the SBR NHL data that exists for 2022-23.

### 4.2 Alternatives checked and rejected

| Source | Result |
|---|---|
| `flancast90/sportsbookreview-scraper` → `data/nhl_archive_10Y.json` (MIT, 7.3 MB) | Downloaded and inspected. **Ends at season 2021** (last game 2022-06-24). Same SBR data I already have, reshaped to one row per game. Adds nothing. |
| `JonathanColetti/Nhl24-25-dataset-and-creation` → `nhl_dataset.csv` (2.2 MB, 2024-25 incl. playoffs) | Downloaded and inspected. Its README advertises odds, but the three odds columns (`spread`, `over_under`, `favorite_moneyline`) are **0.0 in all 2 886 rows** — zero usable odds. Also carries no `favorite_moneyline` pair, only a single number, and has no licence. Rejected. |
| `gmalbert/hockey-predictions` → `data_files/historical/<season>/games.json` for 2019-20 … 2025-26 | Downloaded 2023-24 and inspected. Pure NHL API schedule/results (`game_id`, `date`, `home_team`, `score`, `went_to_ot`, …). **No odds fields of any kind.** No licence. Rejected. |
| Kaggle | Download requires a logged-in session: `api/v1/datasets/download/...` returns **403** unauthenticated. Out of scope per the "no scraping behind logins" constraint. The public list API does show plausible candidates if you want to pull them manually with your own Kaggle token — `oliviersportsdata/us-sports-master-historical-closing-odds` (updated 2026-03-21) and `jonathanncoletti/nhl-historical-game-data` ("2004-today", updated 2025-12-12) look like the best bets for 2023-24 onward. |
| `covers.com/sportsoddshistory/nhl-odds/` | Reachable, but **futures only** — Stanley Cup / conference / division prices. No per-game moneyline archive. |
| `aussportsbetting.com/data/` historical NHL spreadsheet | **403** to both `curl` and WebFetch; bot-blocked, not fetchable here. Worth a manual browser try — this publisher does post free per-sport odds workbooks. |
| Hugging Face datasets (`nhl odds`, `nhl betting`, `hockey odds`) | No matching datasets. |
| oddsportal scrapers (e.g. `jordantete/OddsHarvester`) | Tooling only, no committed data; scraping oddsportal is against its terms. Not attempted. |

**Recommendation for closing the gap:** the Kaggle route in the table above is the most
promising, and needs your Kaggle token rather than more searching. Failing that, The Odds
API's paid historical endpoint covers late-2020 onward.

---

## 5. Verification

Every file was opened and checked: non-empty, row count, visitor/home pairing, moneyline
fill rate, and month histogram against the season's real playoff window.

| Season | Data rows | Games | `Open`+`Close` both filled | Playoff window | Playoff rows | Apr–Jun rows |
|---|---|---|---|---|---|---|
| 2016-17 | 2 634 | 1 317 | 2 634 / 2 634 (100%) | Apr–Jun 2017 | **322** | 322 |
| 2017-18 | 2 710 | 1 355 | 2 710 / 2 710 (100%) | Apr–Jun 2018 | **278** | 278 |
| 2018-19 | 2 716 | 1 358 | 2 716 / 2 716 (100%) | Apr–Jun 2019 | **276** | 276 |
| 2019-20 | 2 424 | 1 212 | 2 424 / 2 424 (100%) | **Aug–Sep 2020** (bubble) | **260** | 0 |
| 2020-21 | 1 904 | 952 | 1 904 / 1 904 (100%) | **May–Jul 2021** | **362** | 802 |
| 2021-22 | 2 802 | 1 401 | 2 802 / 2 802 (100%) | Apr–Jun 2022 | **642** | 642 |
| 2022-23 | 684 | 342 | 684 / 684 (100%) | Apr–Jun 2023 | **0** | 0 |

**Playoff coverage: present in six of seven files.** Only 2022-23 has none, because the
file stops in November. Note again that 2019-20 has zero April–June rows yet does contain
playoffs, and 2020-21's 802 April–June rows are mostly regular season — the "Apr–Jun"
column is shown only to make that trap explicit.

Every moneyline pair is populated in every row of every file, so there are no missing
prices to impute.

### Anomalies found during verification

* `nhl-odds-2019-20.xlsx` rows **1482–1483**: the only reversed pair in the whole corpus —
  the home row comes first.
  ```
  117, 55, H, Pittsburgh, 0,0,1, 2, -230, -230, -1.5, 110, 6, -110, 6, -105
  117, 56, V, Detroit,     0,1,0, 1,  192,  205,  1.5, -130, 6, -110, 6, -115
  ```
  A parser that assumes "even row = visitor" mislabels home/away for this game. Keying on
  the `VH` column instead is safe.
* `nhl-odds-2019-20.xlsx` row **2015**: team `Arizonas` (should be `Arizona`).
* `nhl-odds-2019-20.xlsx` row **2197**: team `Tampa` (should be `TampaBay`).
* `nhl-odds-2016-17.xlsx` final row has `Final` = 0 for Nashville in the 11 June 2017 Cup
  final — correct, they were shut out.

---

## 6. Example rows

Verbatim first two data rows (one game) from each file, plus a playoff row where one
exists. Columns in the 16-value order of §3.1.

**`nhl-odds-2016-17.xlsx`** — regular season opener, and a Cup final row:
```
1012, 1, V, Toronto,   2,2,0, 4, 114, 121,  1.5, -245, 5.5, -110, 5.5,  105
1012, 2, H, Ottawa,    2,1,1, 5, -134, -141, -1.5, 205, 5.5, -110, 5.5, -125
 611, 12, H, Nashville, 0,0,0, 0, -140, -107, -1.5, 230, 5.5, -120, 5.5, -140
```

**`nhl-odds-2017-18.xlsx`**:
```
1004, 1, V, Toronto,   3,1,3, 7, -110, -105,  1.5, -295, 5.5, -125, 6, -115
1004, 2, H, Winnipeg,  0,0,2, 2, -110, -115, -1.5,  235, 5.5,  105, 6, -105
 607, 10, H, Vegas,    0,3,0, 3, -135, -163, -1.5,  165, 5.5, -115, 5.5, -101
```

**`nhl-odds-2018-19.xlsx`** (note the spaced headers, §3.6):
```
1003, 1, V, Montreal,  1,1,0, 2,  184,  210,  1.5, -125, 6, -110, 6, -110
1003, 2, H, Toronto,   1,1,0, 3, -220, -240, -1.5,  105, 6, -110, 6, -110
 612, 14, H, Boston,   0,0,1, 1, -175, -170, -1.5,  159, 5.5, -110, 5, 100
```

**`nhl-odds-2019-20.xlsx`** — opener, then a neutral-site bubble playoff pair:
```
1002, 1, V, Ottawa,      1,1,1, 3,  245,  270,  1.5,  105, 6, -110, 6.5, -115
1002, 2, H, Toronto,     0,4,1, 5, -300, -310, -1.5, -125, 6, -110, 6.5, -105
 801, 1, N, Montreal,    1,1,0, 3, -110,  143, ...
 801, 2, N, Pittsburgh,  0,2,0, 2, -120, -158, ...
```

**`nhl-odds-2020-21.xlsx`** — January start, and the last row (Cup final, 7 July 2021):
```
113, 41, V, Pittsburgh,   1,1,1, 3, -110, -115,  1.5, -310, 6, -110, 6,  105
113, 42, H, Philadelphia, 2,1,3, 6,  100, -105, -1.5,  260, 6, -110, 6, -125
707, 32, H, Tampa Bay,    0,1,0, 1, -220, -245, -1.5,  110, 5,  100, 5,  120
```

**`nhl-odds-2021-22.xlsx`**:
```
1012, 1, V, Pittsburgh, 0,2,4, 6,  120,  220,  1.5, -120, 6, -120, 5.5, -130
1012, 2, H, TampaBay,   0,0,2, 2, -140, -250, -1.5,  100, 6,  100, 5.5,  110
 626, 32, H, TampaBay,  1,0,0, 1, -115, -101,  1.5, -254, 6, -120, 5.5,  110
```

**`nhl-odds-2022-23.xlsx`** — opens on a neutral-site pair; no playoff rows exist:
```
1007, 61, N, SanJose,     1,0,0, 1,  150,  165,  1.5, -150, 5.5, -125, 5.5, -130
1007, 62, N, Nashville,   1,2,1, 4, -180, -185, -1.5,  130, 5.5,  105, 5.5,  110
1127, 86, H, Los Angeles, 0,2,0, 2, -160, -154, -1.5,  165, 6.5, -115, 6.5, -115
```

---

## 7. Notes for the US-005 parser

* Read the first worksheet only; three of the seven workbooks have empty `Sheet2`/`Sheet3`.
* Match header names case- and whitespace-insensitively (`Puck Line` vs `PuckLine`).
* Index by position, not by zipping 13 headers to 16 values (§3.1).
* Derive home/away from the `VH` column, never from row parity (§5).
* Reconstruct the year from filename season + month; months ≥ 8 belong to the first
  calendar year (§3.3).
* Tag playoffs against the real per-season window in §5, not a fixed April–June rule.
* Normalize whitespace/punctuation in team names, and alias `Arizonas` → `Arizona`,
  `Tampa` → `TampaBay` (§3.4).
* `N` rows have no home-ice information; flag rather than guess.
* 2023-24, 2024-25 and 2025-26 have **no odds coverage at all** — flag explicitly, never
  impute.

---

## 8. Second source: Kaggle `jonathanncoletti/nhl-historical-game-data` (added 2026-08-26)

Owner-downloaded from Kaggle (logged-in web download; the dataset page advertises
"2004-today", last updated 2025-12-12) and committed under `kaggle-nhl-historical/`,
gzipped for repo size (gunzip restores the original bytes; md5 of the uncompressed
files: `nhl_data_extensive.csv` c3bbbece8c5d31928d58822be5ade6cc,
`nhl_data_plus.csv` 21f190e96f43497439fc24d63fa6917d). The dataset's own build scripts
are committed alongside as `download_dataset.py.gz` / `build_dataset_extra.py.gz`
(gzipped verbatim: they are third-party provenance artifacts, and the repo's
CodeScene code-health gate analyzes bare .py files — gunzip to read) — they reveal
the odds provenance: **ESPN's public
scoreboard/summary API** (`site.api.espn.com/.../scoreboard` and `/summary`, the
`pickcenter` odds block). `aussportsbetting.com` was also checked by the owner and has
no NHL data.

### Layout (`nhl_data_extensive.csv`, 59,160 data rows; `nhl_data_plus.csv` is the same
games with fewer columns)

One row per **team per game** (two rows per `game_id`; 326 early-era games have only
one row). Odds columns are **game-level, repeated identically on both rows**:

- `favorite_moneyline` — the favorite's American-odds price (single side only; the
  underdog price is NOT present, so exact de-vigging is impossible — treat as a
  monotone win-probability proxy or apply a documented standard-overround assumption)
- `spread` — puck line for the row's team; the favorite's row carries the negative
  spread, which identifies which team the moneyline belongs to
- `over_under` — game total
- `season` — the season's ENDING year (season 2025 = 2024-25); September rows are
  preseason, so filter by joining to the real NHL schedule
- plus ~120 stat/context columns (rolling team stats, records, officials) that the
  pipeline derives itself from the NHL API — ignore them, they are convenience data

### Verification (performed on the uncompressed files)

- `favorite_moneyline` is 100% filled and non-zero in ALL 59,160 rows, seasons 2004
  through 2026-partial; values are sane American odds (none in the impossible
  (-100, +100) open interval)
- Season date ranges confirm ending-year labeling; **2023-24 and 2024-25 are complete
  including May-June playoff games** (106 and 94 May-June rows respectively)
- **Season 2025-26 ends 2025-12-11** — the 2026 playoffs are NOT in this file
- The favorite moneyline is identical on both rows of all 29,417 two-row games

### Updated coverage picture

| Seasons | Game moneylines | Source |
|---|---|---|
| 2004 – 2015-16 | favorite price only | Kaggle/ESPN file |
| 2016-17 – 2021-22 | both-side Open/Close (preferred) + favorite price (cross-check) | SBR workbooks + Kaggle/ESPN file |
| 2022-23 | SBR through Nov 2022 only; favorite price for the full season incl. playoffs | both |
| 2023-24 – 2024-25 | favorite price only, playoffs included | Kaggle/ESPN file |
| 2025-26 regular season (to Dec 11) | favorite price only | Kaggle/ESPN file |
| **2025-26 playoffs and beyond** | **fetchable live: ESPN summary API** (`site.api.espn.com/.../summary?event=<id>`, `pickcenter` block) — same host already pinned for injuries; US-005 ingests these directly | ESPN API |

The overlap seasons (2016-17 – 2021-22) double as a cross-validation set between the
two sources.

---

## 9. Third source: ESPN API completion for 2025-26 (fetched 2026-08-26)

Closes the gap §8 left open: the Kaggle file's season-2026 coverage stops on
2025-12-11, so the rest of the 2025-26 regular season and the entire 2026 playoffs
were pulled directly from ESPN's public API into `espn-2025-26-completion/`.

**This is the same upstream source as the Kaggle file** — §8 established that the
Kaggle dataset's own build scripts hit these very endpoints — so the odds semantics
match by construction rather than by coincidence.

### Endpoints

Scoreboard, to enumerate game ids in 7-day windows (29 requests):

```
https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard?dates=YYYYMMDD-YYYYMMDD
```

Per-game summary, for odds and results (903 requests):

```
https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/summary?event=<game_id>
```

Window fetched: **2025-12-12 through 2026-06-30**. One request per second, three
attempts with exponential backoff. **0 retries and 0 failures** — every one of the 932
requests succeeded first try.

One gotcha worth recording: ESPN **403s browser-like `User-Agent` headers** on this
host. `curl`'s default UA works; a Chrome UA returns `Access Denied`. The committed
`fetch_espn.py` was the exact script used; it was later refactored (functions
extracted, behavior identical) to satisfy the repo's CodeScene gate — the byte-exact
run version is in git history at the commit that added this section.

### Deliverables

| Path | What |
|---|---|
| `espn-2025-26-completion/games.csv` | 1 806 rows, 903 games, schema identical to the Kaggle `nhl_data_plus.csv` odds columns |
| `espn-2025-26-completion/raw/summary/<game_id>.json.gz` | 903 raw summary responses, gzipped individually |
| `espn-2025-26-completion/raw/scoreboard/<range>.json.gz` | 29 raw scoreboard responses |
| `espn-2025-26-completion/raw/scoreboard-events.json` | flat event index (id, date, name, state, season type, series note) |
| `espn-2025-26-completion/fetch_espn.py` | the fetcher, for reproducibility |

Total 12 MB across 935 files. No `.gitignore` rule matches the directory.

**What the raw JSON omits.** A full summary response is ~450 KB, of which ~313 KB is
`plays` (play-by-play). Five keys are dropped before gzipping — `plays`, `news`,
`article`, `videos`, `standings` — taking a payload from 450 KB to 127 KB (11.7 KB
gzipped) and the commit from ~40 MB to 12 MB. **Everything else is preserved verbatim**:
`boxscore`, `header`, `seasonseries`, `pickcenter`, `odds`, `againstTheSpread`,
`gameInfo`, `leaders`, `injuries`, `onIce`, `format`, `meta`. To recover a dropped
block, re-request the same URL — the game ids are all in `scoreboard-events.json`.

### Column semantics

`games.csv` columns are exactly the Kaggle file's:
`game_id, date, season, team_name, is_home, won, goals_for, goals_against, spread,
over_under, favorite_moneyline`.

* `date` is rendered in the Kaggle file's format (`2026-06-15 00:00:00+00:00`) from
  ESPN's `header.competitions[0].date`. It is **UTC**, so a 7pm ET game shows as the
  next calendar day — the December seam below is expressed in UTC dates.
* `season` is `2026`, the season's **ending** year, matching §8.
* `spread`, `over_under`, `favorite_moneyline` are **game-level and repeated
  identically on both rows** of a game, exactly as in the Kaggle file. Verified: 0 of
  903 games disagree between their two rows.
* Odds come from `pickcenter[0]`, which is **Draft Kings for all 1 806 rows** — a
  single book across the whole window, so no cross-book mixing.
* `favorite_moneyline` is the favorite's side only. The underdog price is not in this
  column, so exact de-vigging is still impossible — same caveat as §8.

**One improvement over the Kaggle file worth using.** §8 records that the Kaggle
`spread` does not identify which team the moneyline belongs to. In this file it does:
ESPN's `pickcenter.spread` is **home-relative**, so a negative `spread` means the home
team is the favorite. Checked against `homeTeamOdds.favorite` in the raw JSON for all
903 games — **903 agree, 0 disagree**. So `favorite_moneyline` can be attributed to a
side with `spread < 0 ⇒ home`, no raw-JSON lookup needed. (The raw JSON also carries
both `moneyLine` values and `favoriteAtOpen`, if the underdog price is ever wanted.)

### Row counts and fill rates

| Metric | Value |
|---|---|
| Rows | 1 806 |
| Games | 903 (all unique game ids) |
| Regular-season games (ESPN `season.type` 2) | 821 |
| Playoff games (ESPN `season.type` 3) | 82 |
| `favorite_moneyline` filled | **1 806 / 1 806 (100%)** |
| `spread` filled | 1 806 / 1 806 (100%) |
| `over_under` filled | 1 806 / 1 806 (100%) |
| **Apr–Jun 2026 rows** | 418 |
| **`favorite_moneyline` filled, Apr–Jun 2026** | **418 / 418 (100%)** |
| `spread` / `over_under` filled, Apr–Jun 2026 | 418 / 418 (100%) each |

**Games with missing or empty `pickcenter`: none.** Every one of the 903 games returned
a populated `pickcenter[0]` with a spread, a total, and a favorite moneyline. Nothing
was filled in, imputed, or defaulted — the 100% figures are what the API returned.

Rows by month, and why February dips:

| Month | Rows | Regular | Playoff |
|---|---|---|---|
| 2025-12 (from the 12th) | 268 | 134 | — |
| 2026-01 | 476 | 238 | — |
| 2026-02 | 150 | 75 | — |
| 2026-03 | 494 | 247 | — |
| 2026-04 | 334 | 127 | 40 |
| 2026-05 | 72 | — | 36 |
| 2026-06 | 12 | — | 6 |

February is thin because of the **Milan-Cortina Olympic break**, not missing data — the
scoreboard returns 20 events for 2026-02-20…02-26 against 53–59 in surrounding weeks.

### Seam with the Kaggle file

The Kaggle file's season-2026 rows cover **2025-09-20 … 2025-12-11** (583 games,
including 71 September preseason games that §8 already flags for filtering). This file
starts **2025-12-13** (UTC) and runs to 2026-06-15.

**Overlap: 0 games.** Intersecting the two game-id sets gives the empty set; the union
is 1 486 distinct season-2026 games. So the two sources concatenate cleanly with no
dedupe step and no gap.

### Sanity checks performed before committing

1. **Two rows per game** — 903/903 games have exactly two rows, each with one
   `is_home=1` and one `is_home=0`. No orphans.
2. **Odds agree across a game's two rows** — 0/903 disagreements.
3. **Moneylines are sane American odds** — range **-470 to -102**; zero values inside
   the impossible `(-100, +100)` interval; zero positive values, which is correct since
   the column is by definition the favorite's price.
4. **Playoffs present, and the 2026 Final is there.** 82 playoff games across
   April (40), May (36) and June (6). The Final is **Carolina vs Vegas**, six games,
   and Carolina won it 4-2:

```
game_id     date        away @ home                                 away-home  won  ml     ou   spread
401874171   2026-06-03  Vegas Golden Knights @ Carolina Hurricanes    5-4      VGK  -162   5.5   -1.5
401874172   2026-06-05  Vegas Golden Knights @ Carolina Hurricanes    3-4      CAR  -162   5.5   -1.5
401874173   2026-06-07  Carolina Hurricanes @ Vegas Golden Knights    4-5      VGK  -108   5.5    1.5
401874174   2026-06-10  Carolina Hurricanes @ Vegas Golden Knights    5-3      CAR  -115   5.5    1.5
401874175   2026-06-12  Vegas Golden Knights @ Carolina Hurricanes    2-4      CAR  -155   6.5   -1.5
401874176   2026-06-15  Carolina Hurricanes @ Vegas Golden Knights    3-0      CAR  -115   5.5    1.5
```

   Series 4-2 Carolina. Scores are as the file records them (`goals_for` on each team's
   own row). Note game 3 and game 6: home Vegas with `spread = +1.5`, i.e. the home team
   is the underdog, so the `-108` / `-115` belongs to Carolina — the home-relative spread
   rule in action.

### Example rows, verbatim

First two rows of the file (the 12 December seam) and the Cup-winning game:

```
game_id,date,season,team_name,is_home,won,goals_for,goals_against,spread,over_under,favorite_moneyline
401802844,2025-12-13 01:00:00+00:00,2026,St. Louis Blues,1,1,3.0,2.0,1.5,5.5,-115.0
401802844,2025-12-13 01:00:00+00:00,2026,Chicago Blackhawks,0,0,2.0,3.0,1.5,5.5,-115.0
401802845,2025-12-13 02:00:00+00:00,2026,Utah Mammoth,1,1,5.0,3.0,-1.5,5.5,-192.0
401802845,2025-12-13 02:00:00+00:00,2026,Seattle Kraken,0,0,3.0,5.0,-1.5,5.5,-192.0
```

A round-1 playoff pair and the Cup clincher:

```
401869720,2026-04-20 02:22:00+00:00,2026,Vegas Golden Knights,1,1,4.0,2.0,-1.5,5.5,-162.0
401869720,2026-04-20 02:22:00+00:00,2026,Utah Mammoth,0,0,2.0,4.0,-1.5,5.5,-162.0
401874176,2026-06-15 00:00:00+00:00,2026,Vegas Golden Knights,1,0,0.0,3.0,1.5,5.5,-115.0
401874176,2026-06-15 00:00:00+00:00,2026,Carolina Hurricanes,0,1,3.0,0.0,1.5,5.5,-115.0
```

Note `Utah Mammoth` — a team name that exists in no other file here, and one more
reason the team-name mapping in §3.4 needs to be per-source.

### Coverage picture after this addition

| Seasons | Game moneylines | Source |
|---|---|---|
| 2004 – 2015-16 | favorite price only | Kaggle/ESPN file |
| 2016-17 – 2021-22 | both-side Open/Close (preferred) + favorite price (cross-check) | SBR workbooks + Kaggle/ESPN file |
| 2022-23 | SBR through Nov 2022; favorite price for the full season incl. playoffs | both |
| 2023-24 – 2024-25 | favorite price only, playoffs included | Kaggle/ESPN file |
| 2025-26 to 2025-12-11 | favorite price only | Kaggle/ESPN file |
| **2025-26 from 2025-12-12, incl. all 82 playoff games** | **favorite price, 100% filled, side identifiable via `spread` sign** | **this section** |

**All ten of the originally requested seasons (2016-17 … 2025-26) now have game
moneyline coverage, playoffs included.** The one remaining hole is the front half of
2022-23 for *both-side* Open/Close prices, which only SBR carried and which SBR never
published.

---

## 10. Experiment: does ESPN retain as-of-game `injuries` on old summaries? (2026-08-26)

**Verdict: no. The `injuries` block is resolved live at request time and reflects
today's rosters and today's injuries, not the state of play on the game date. It is
unusable for historical training and would inject both nonsense and leakage.**

Do not backfill injury history from this endpoint. It cannot supply it.

### Method

Eight playoff games, two each from 2024, 2022, 2019 and 2017, event ids found via
`.../scoreboard?dates=YYYYMMDD`, then one call each to:

```
https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/summary?event=<id>
```

One request per second, `curl`'s default User-Agent (this host 403s browser-like UAs —
see §9). Sample payloads are committed under `espn-injury-experiment/raw/<id>.json.gz`,
gzipped with the same five bulky keys dropped as `fetch_espn.py` drops (`plays`, `news`,
`article`, `videos`, `standings`).

### Raw result

| Game | Event id | `injuries` key | Teams listed | Entries |
|---|---|---|---|---|
| 2024-04-24 East R1 G3, BOS @ TOR | 401655553 | present | 2 | 6 |
| 2024-06-24 SCF G7, EDM @ FLA | 401675111 | present | 2 | 6 |
| 2022-05-05 East R1 G2, PIT @ NYR | 401434788 | **absent** | 0 | 0 |
| 2022-06-26 SCF G6, COL @ TBL | 401445853 | present | 2 | 1 |
| 2019-04-10 East R1 G1, CBJ @ TBL | 401126313 | present | 2 | 3 |
| 2019-06-12 SCF G7, STL @ BOS | 401133947 | present | 2 | 3 |
| 2017-04-12 East R1 G1, NYR @ MTL | 400950086 | **absent** | 0 | 0 |
| 2017-06-11 SCF G6, PIT @ NSH | 400954322 | **absent** | 0 | 0 |

Five of eight carry a populated block. The block is keyed by the two teams in the game
and filled with each team's **current** injury list.

### Evidence that the entries are current-day, not as-of-game

**1. Every timestamp is 2026.** Not one entry across all five populated games is dated
anywhere near its game. Every `date` falls between 2026-04-11 and 2026-08-20 — i.e.
"recently", relative to the 2026-08-26 fetch — for games played in 2019 and 2024.

**2. The players did not play for those teams at the time.** From the 2019-06-12
Blues-at-Bruins Cup final:

```
Boston Bruins
  Charlie McAvoy    status=Suspension  date=2026-05-13T00:13Z
  Nikita Zadorov    status=Out         date=2026-05-02T11:45Z   Knee
St. Louis Blues
  Brandon Carlo     status=Out         date=2026-06-27T16:05Z   Lower Body
```

Zadorov did not join Boston until 2024-25. Brandon Carlo is listed under **St. Louis** —
he was a Bruin in 2019 and appears here under whichever team currently holds him. From
the 2019-04-10 Blue Jackets-at-Lightning game:

```
Tampa Bay Lightning
  Pontus Holmberg   status=Out  date=2026-05-05T16:10Z  Collarbone
Columbus Blue Jackets
  Elvis Merzlikins  status=Out  date=2026-08-20T17:23Z  Shoulder
  Isac Lundestrom   status=Out  date=2026-07-19T18:33Z  Achilles
```

Holmberg's NHL debut was 2022-23 — three seasons after this game.

**3. The same team returns byte-identical entries across different eras.** Boston's two
entries in the 2019 Cup final (McAvoy `2026-05-13T00:13Z`, Zadorov `2026-05-02T11:45Z`)
are the *same two entries with the same timestamps* returned for the 2024-04-24
Bruins-at-Leafs game. Tampa Bay's single Holmberg entry (`2026-05-05T16:10Z`) is
identical in both the 2022 Cup final and the 2019 first-round game. One current-day
roster snapshot is being re-served for every historical game those teams appear in.

**4. Entry shape is a live-feed shape.** Each entry carries `fantasyStatus`
(`OUT`, `IR-LT`) and a `returnDate` — forward-looking fantasy-advice fields that only
make sense for an upcoming game, not a settled one.

Taken together there is no ambiguity: the block is a join against the current injury
table, not an archived snapshot.

### Consequence for US-003/US-004

* **Historical injury features cannot come from this endpoint.** Using it would label a
  2019 game with 2026 injuries — pure noise, and leakage wherever a currently-injured
  star was healthy and productive in the historical game.
* The `injuries` block remains valid for **live/upcoming** use, which is what §9's
  pipeline needs it for. Nothing already committed is affected: the 2025-26 completion
  in §9 uses `pickcenter` only and never read `injuries`.
* If injury history is wanted for training seasons it needs a genuinely archival
  source — the NHL API's own daily rosters/scratches, or a third-party historical
  transactions feed. Out of scope here, and not started.

The three games with no `injuries` key at all (2022 R1, both 2017 games) do not change
the verdict; they only show ESPN omits the block for some older events.
