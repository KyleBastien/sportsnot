# Provenance — NHL shift charts and deployment

Snapshot fetched **2026-09-05 through 2026-09-06** from public NHL endpoints
without authentication. Coverage targets every regular-season and playoff game
in `../nhl-archive/game-times-<season>.csv.gz` for **2007-08 through
2025-26**. NaturalStatTrick was not contacted.

No shift is imputed. The fetch stops on an unparseable response, an ambiguous
HTML player match, or a response at the Stats REST 10,000-row cap.

## 1. Exact endpoints

Primary shift-chart request, one request per game:

```text
GET https://api.nhle.com/stats/rest/en/shiftcharts
    ?cayenneExp=gameId=<gameId>
```

The script checks both the returned `data` length and declared `total` against
10,000. A game response cannot be partitioned further, so either reaching the
cap stops the run. No fetched game reached the cap.

When a game's REST response has no ordinary (`typeCode=517`) shift rows, the
public home and visitor HTML time-on-ice reports are fetched:

```text
GET https://www.nhl.com/scores/htmlreports/<yyyyYYYY>/TH<gameId-last-6>.HTM
GET https://www.nhl.com/scores/htmlreports/<yyyyYYYY>/TV<gameId-last-6>.HTM
```

`TH` is the home report and `TV` is the visitor report. Both are required for a
complete fallback game.

Politeness matches the adjacent NHL archive: curl-based GET, **one request per
second**, **four attempts**, and exponential backoff between failed attempts.
Fetching is single-process and single-threaded.

## 2. Required probe

Before the archive run, one regular-season and one playoff game were probed for
each required season. `Rows` is the endpoint's returned row count.

| Season | Type | gameId | REST rows | HTML fallback rows | Selected source |
|---|---:|---:|---:|---:|---|
| 2007-08 | 2 | 2007020001 | 0 | 708 | HTML TH+TV |
| 2007-08 | 3 | 2007030111 | 0 | 711 | HTML TH+TV |
| 2008-09 | 2 | 2008020001 | 0 | 809 | HTML TH+TV |
| 2008-09 | 3 | 2008030111 | 0 | 751 | HTML TH+TV |
| 2009-10 | 2 | 2009020001 | 0 | 735 | HTML TH+TV |
| 2009-10 | 3 | 2009030111 | 0 | 918 | HTML TH+TV |
| 2010-11 | 2 | 2010020001 | 760 | not requested | Stats REST |
| 2010-11 | 3 | 2010030111 | 1,028 | not requested | Stats REST |
| 2023-24 | 2 | 2023020001 | 751 | not requested | Stats REST |
| 2023-24 | 3 | 2023030111 | 737 | not requested | Stats REST |

The probe used **10 REST requests** and **12 HTML requests**, with zero retries
and zero failures. Because both probes were empty in each of 2007-08, 2008-09,
and 2009-10, the full run routes those seasons directly to HTML instead of
making known-empty REST requests first. The six HTML probes all served shifts.

## 3. Raw cache and manifests

`fetch_shifts.py` writes every raw response to `cache/<season>/` before parsing.
REST responses use `<gameId>.json.gz`; fallback responses use
`<gameId>-TH.html.gz` and `<gameId>-TV.html.gz`. `cache/` is gitignored because
it is a resumable local working cache, not the compact committed snapshot.
Existing cache files are read and never downloaded again.

Every committed `cache-manifest-<season>.csv.gz` has
`gameId,bytes,sha256`, where bytes and SHA-256 describe the uncompressed raw
response. HTML seasons have two rows per game. Their additional
`html-cache-manifest-<season>.csv.gz` adds the `TH`/`TV` side so each duplicate
game ID resolves to its exact local cache file.

HTML names are joined only against same-game, same-team skater and goalie rows
in the NHL archive. An exact, season-unique `skater-bios` name is also accepted
when the Stats REST game table omits a player who appears in the HTML report.
Matching applies Unicode decomposition plus case and punctuation folding, then
tries exact full name, a unique exact surname, and a unique
first-initial/fuzzy-surname match with score at least 0.75 and a 0.15 margin.
This handles served historical forms such as `ROBERT BLAKE` versus `Rob Blake`.
Six-cell rows for periods 1–5 are shift rows; seven-cell period summary rows are
not. A uniquely identified opposing-team player embedded in the wrong side's
report is rejected as a source anomaly and reported. Any other ambiguous or
absent match stops the run; IDs are never guessed.

Some HTML rows span a period boundary. Those rows are split at the period end;
the served duration includes the intermission and is therefore not used. Normal
same-period durations are also recomputed from the served start/end clocks.
Split pieces retain one shift number and count as one physical shift during
derivation.

## 4. Committed shift schema

Each `shifts-<season>.csv.gz` contains:

```text
gameId,teamAbbrev,playerId,firstName,lastName,period,startSeconds,
endSeconds,durationSeconds,shiftNumber,typeCode,eventDescription
```

REST fields are normalized to integer seconds within the period. REST and HTML
shift rows spanning a period boundary are split at that boundary because the
served duration includes intermission time. HTML reports use NHL shift type code
`517` for ordinary shift rows. REST `typeCode=505` goal markers are retained
with their served event description; derivation excludes them from intervals.
Stats REST sometimes encodes a regular-season overtime shift ending at the
five-minute horn as `20:00`; that clock is normalized to `5:00`. A full overtime
shift encoded as `0:00` to `0:00` with duration `5:00` is normalized to the full
five-minute interval. Playoff overtime remains 20 minutes.

Rows sort deterministically by game ID, team, player, period, start, end, shift
number, and type code. CSVs use UTF-8, LF endings, and gzip modification time
zero. A cache-only rerun must emit byte-identical files.

## 5. Deterministic deployment derivation

`derive_deployment.py` reads only committed shift tables plus the adjacent NHL
archive. Player positions come from same-season `skater-bios`; IDs absent from
skater bios are goalies and are excluded from on-ice skater counts.

For each period, the script sweeps every shift start/end boundary and derives
strength from simultaneous skater counts for both teams. Five-on-five segments
feed forward trios (`F3`) and defence pairs (`D2`). A line/pair is retained when
its game TOI is at least 60 seconds. Man-advantage segments feed skater `toiPP`
and five-skater PP combinations; combinations rank by descending game TOI, then
sorted player IDs. Six-on-five empty-net play is not classified as a power play.

Outputs under `derived/<season>/` are:

- `skater-game-toi.csv.gz`: 5v5, PP, PK, all-situation TOI and shift count.
- `lines.csv.gz`: qualifying forward trios and defence pairs with 5v5 TOI.
- `pp-units.csv.gz`: five-skater PP combinations, PP TOI, and per-game rank.
- `dressed.csv.gz`: every skater with a normal shift, archive position, and TOI.

`toiAll` is the union of each skater's normal shift intervals, so overlapping
duplicate source rows do not double-count time. Cross-checks compare derived
`toiAll` and `toiPP` with `../nhl-archive/skater-toi-<season>.csv.gz`, report the
share within five seconds, preserve the worst 20 rows, and enumerate every
team-game whose dressed-skater count is not 18.

## 6. Fetch result and source exceptions

The completed snapshot made **28,615 requests**: **20,597 REST** responses and
**8,018 HTML** responses. There were **zero retries, zero failures, and zero
10,000-row cap hits**. The archive requested **24,542 games** (22,842 regular
season and 1,700 playoff), selected REST for 20,534 games, selected HTML for
4,000 games, and recovered shifts for **24,534 games**.

The eight games below returned no ordinary shifts from either public source and
remain unavailable; nothing was imputed:

- 2007-08: `2007020011`
- 2008-09: `2008020259`, `2008020409`, `2008021077`, `2008030311`
- 2009-10: `2009020081`, `2009020658`, `2009020885`

Additional served-source findings:

- Stats REST returned only one `typeCode=505` marker for `2013020971`; its 786
  ordinary shifts came from the HTML fallback.
- Stats REST returned no ordinary shifts for 57 games late in 2024-25; all 57
  were recovered from paired HTML reports.
- The `2007030174` MIN HTML report embeds COL player Ryan Smyth. That
  opposing-team row is rejected rather than assigned to MIN.
- Same-season unique-bio fallback maps Brent Burns in `2008020160`, Derek
  Boogaard in `2009020079`, and Matt D'Agostini in `2009020439`; those players
  appear in HTML but are absent from that game's Stats REST skater table.
- The REST source contains 75 zero-duration ordinary-shift artifacts. They are
  retained for source fidelity and excluded from interval derivation.

Every one of the **28,493** primary manifest rows and **8,018** side-qualified
HTML manifest rows was regenerated from the local raw cache. A final cache-only
replay made no requests and changed **0 of 43** committed root CSV files.

## 7. Shift files, sizes, and checksums

`Goals` counts retained `typeCode=505` marker rows. SHA-256 covers the committed
gzip bytes.

| Season | Games | Served | REST | HTML | Missing | Shift rows | Goals | Bytes | SHA-256 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 2007-08 | 1,315 | 1,314 | 0 | 1,314 | 1 | 993,091 | 0 | 8,018,009 | `b35908fb19ca02ca817616d6f1edfc3fe974c7da404dd577d93c434fa5b32589` |
| 2008-09 | 1,317 | 1,313 | 0 | 1,313 | 4 | 1,007,595 | 0 | 8,092,481 | `881b7dc28c4b9f906ba41db054931584fc073e8c39ad23e5e2890057b1f0581a` |
| 2009-10 | 1,319 | 1,316 | 0 | 1,316 | 3 | 1,014,581 | 0 | 8,123,993 | `ed3102e01ce4d2b3181f74efe9d39e5b93f702799374008fad3fa5e7857d1208` |
| 2010-11 | 1,319 | 1,319 | 1,319 | 0 | 0 | 1,043,268 | 7,544 | 8,121,240 | `ed7dd777f5afff755ddddc32ac1bebf59a68b62b8fc1cee65c8eaa0b8d38b2eb` |
| 2011-12 | 1,316 | 1,316 | 1,316 | 0 | 0 | 1,037,744 | 7,370 | 8,095,325 | `355ff77788005bcc9386ad4c1e303f57107cd2a567c625da9d5dbbc08b9a78a7` |
| 2012-13 | 806 | 806 | 806 | 0 | 0 | 641,452 | 4,480 | 4,993,220 | `0b1bfc536487e518ff44b1aa8e0c1d3ad62a3160a206d78ab72e891109006ed8` |
| 2013-14 | 1,323 | 1,323 | 1,322 | 1 | 0 | 1,061,924 | 7,502 | 8,246,745 | `c0617692e90996b883fbf8beb7f0daee0b54c2d7441c1e3d892665104d76b266` |
| 2014-15 | 1,319 | 1,319 | 1,319 | 0 | 0 | 1,067,763 | 7,377 | 8,276,686 | `1d5cf8c29db5ba7b778b68e92f094e68a1491f5029aa0043b4f839330cc28353` |
| 2015-16 | 1,321 | 1,321 | 1,321 | 0 | 0 | 1,066,758 | 7,192 | 8,305,939 | `7681efcbc841c9377908035f3e9b4dc847caf303fbccc5f0475705899f99e6d0` |
| 2016-17 | 1,317 | 1,317 | 1,317 | 0 | 0 | 1,059,042 | 7,377 | 8,222,073 | `0972ad9017741004c6faa312d3bfdf5d2d0e2dbb284435dd8797d3d169e71326` |
| 2017-18 | 1,355 | 1,355 | 1,355 | 0 | 0 | 1,068,110 | 8,187 | 8,304,376 | `0d438d1e1f5ea507451adc2bd0d6fbd05ff381d54f5d574564936622f3e9da84` |
| 2018-19 | 1,358 | 1,358 | 1,358 | 0 | 0 | 1,058,512 | 8,250 | 8,265,304 | `893a1e4d4318e6680ceb57df4523f7549a1280b2350de257e7c75f11defb84d6` |
| 2019-20 | 1,212 | 1,212 | 1,212 | 0 | 0 | 943,357 | 7,362 | 7,394,014 | `435e6a306dc08de13b888cc3c88c526e14aa9396eca40ccb02d87f5eb1d672dd` |
| 2020-21 | 952 | 952 | 952 | 0 | 0 | 743,748 | 5,903 | 5,803,162 | `3e6daf188fedadbb82cb796d85b8e55b23198c270ee74bbc8184d98617a48031` |
| 2021-22 | 1,401 | 1,401 | 1,401 | 0 | 0 | 1,093,024 | 9,169 | 8,881,836 | `cffc2b551604e253a6c86b4232cbe06315f362adc3afef2af61d35c2a07f76a6` |
| 2022-23 | 1,400 | 1,400 | 1,400 | 0 | 0 | 1,078,525 | 9,092 | 9,310,568 | `30b840c97179d2ba5bb2b76e6a95a44b1632911729972a3388f21db2adcd58b6` |
| 2023-24 | 1,400 | 1,400 | 1,400 | 0 | 0 | 1,070,981 | 8,869 | 9,256,523 | `e44d3db27c8773509507cd8c9b274a4d3901dc664b2eea110702fbce2444e37f` |
| 2024-25 | 1,398 | 1,398 | 1,341 | 57 | 0 | 1,069,781 | 8,281 | 9,276,782 | `427926f6bffe0b59ec733eb3c3d9277c587796e12c56fc51bb77f9b369b6c7fa` |
| 2025-26 | 1,394 | 1,394 | 1,394 | 0 | 0 | 1,061,857 | 8,891 | 9,206,331 | `fda0a923dd614957971bf822719609a2661dbdc380a6eb68bbea436e232fa3ba` |

All 19 shift files total **154,194,607 bytes (147.051 MiB)**. This is below
the 200 MB rule, so every season is committed whole; no split or reassembly is
needed. The 76 derived files add **23,043,406 bytes (21.976 MiB)**.

## 8. Derivation validation

The derivation emitted **883,113 skater-game TOI rows**, **633,725 line/pair
rows**, **381,148 PP-unit rows**, and **883,113 dressed rows**. It compared
883,075 rows with Tier 1; 38 derived rows have no Tier 1 counterpart.
`toiAll` is within five seconds for **860,950/883,075 (97.495%)** rows, and
`toiPP` is within five seconds for **858,240/883,075 (97.188%)** rows.

| Season | Games | Skater TOI | Lines | PP units | TOI all <=5s | TOI PP <=5s | Missing Tier 1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2007-08 | 1,314/1,315 | 47,290 | 34,357 | 27,045 | 86.648% | 92.988% | 0 |
| 2008-09 | 1,313/1,317 | 47,247 | 34,127 | 25,831 | 86.363% | 96.516% | 1 |
| 2009-10 | 1,316/1,319 | 47,369 | 34,648 | 23,370 | 85.346% | 96.721% | 2 |
| 2010-11 | 1,319/1,319 | 47,466 | 35,406 | 22,687 | 99.823% | 98.123% | 0 |
| 2011-12 | 1,316/1,316 | 47,371 | 34,228 | 20,455 | 99.935% | 98.404% | 0 |
| 2012-13 | 806/806 | 29,014 | 20,981 | 12,467 | 99.872% | 98.087% | 0 |
| 2013-14 | 1,323/1,323 | 47,623 | 33,168 | 19,927 | 99.893% | 98.182% | 0 |
| 2014-15 | 1,319/1,319 | 47,478 | 32,204 | 18,135 | 99.823% | 97.776% | 0 |
| 2015-16 | 1,321/1,321 | 47,554 | 33,106 | 17,866 | 99.889% | 97.495% | 1 |
| 2016-17 | 1,317/1,317 | 47,406 | 32,743 | 16,867 | 99.918% | 97.977% | 0 |
| 2017-18 | 1,355/1,355 | 48,780 | 34,206 | 16,255 | 99.965% | 98.171% | 0 |
| 2018-19 | 1,358/1,358 | 48,887 | 34,712 | 15,539 | 99.892% | 98.130% | 0 |
| 2019-20 | 1,212/1,212 | 43,629 | 30,780 | 14,414 | 98.198% | 91.916% | 0 |
| 2020-21 | 952/952 | 34,250 | 25,008 | 10,891 | 99.439% | 92.782% | 0 |
| 2021-22 | 1,401/1,401 | 50,448 | 35,945 | 19,694 | 99.225% | 95.903% | 0 |
| 2022-23 | 1,400/1,400 | 50,376 | 37,296 | 25,874 | 99.913% | 98.795% | 0 |
| 2023-24 | 1,400/1,400 | 50,389 | 36,622 | 25,953 | 99.782% | 98.789% | 0 |
| 2024-25 | 1,398/1,398 | 50,321 | 36,841 | 23,697 | 99.259% | 99.094% | 1 |
| 2025-26 | 1,394/1,394 | 50,215 | 37,347 | 24,181 | 99.837% | 99.002% | 33 |

The largest discrepancies are served-source disagreements. In particular,
several early HTML totals are almost exactly twice the Stats REST Tier 1 value;
the shift archive preserves the public HTML intervals instead of altering them.
Worst 20 rows, seconds:

| Season | gameId | playerId | Derived all | NHL all | Diff | Derived PP | NHL PP | PP diff |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2007-08 | 2007020938 | 8467096 | 2,223 | 1,112 | 1,111 | 605 | 303 | 302 |
| 2019-20 | 2019020287 | 8474230 | 1,308 | 249 | 1,059 | 2 | 2 | 0 |
| 2007-08 | 2007020362 | 8470602 | 2,114 | 1,057 | 1,057 | 564 | 282 | 282 |
| 2010-11 | 2010020124 | 8471242 | 379 | 1,423 | 1,044 | 0 | 250 | 250 |
| 2010-11 | 2010020124 | 8470137 | 604 | 1,647 | 1,043 | 75 | 338 | 263 |
| 2007-08 | 2007020080 | 8467400 | 2,085 | 1,043 | 1,042 | 836 | 443 | 393 |
| 2007-08 | 2007020596 | 8470151 | 2,102 | 1,074 | 1,028 | 164 | 82 | 82 |
| 2019-20 | 2019020144 | 8474722 | 1,584 | 571 | 1,013 | 0 | 0 | 0 |
| 2007-08 | 2007020556 | 8469770 | 2,018 | 1,009 | 1,009 | 239 | 120 | 119 |
| 2007-08 | 2007020886 | 8467096 | 2,007 | 1,004 | 1,003 | 48 | 24 | 24 |
| 2007-08 | 2007020517 | 8465009 | 1,981 | 991 | 990 | 278 | 120 | 158 |
| 2007-08 | 2007020080 | 8457063 | 1,977 | 989 | 988 | 451 | 262 | 189 |
| 2007-08 | 2007020297 | 8459462 | 1,975 | 988 | 987 | 388 | 194 | 194 |
| 2007-08 | 2007020076 | 8459424 | 1,960 | 980 | 980 | 694 | 347 | 347 |
| 2019-20 | 2019021013 | 8479369 | 1,749 | 773 | 976 | 0 | 0 | 0 |
| 2007-08 | 2007020064 | 8458951 | 1,949 | 975 | 974 | 591 | 296 | 295 |
| 2007-08 | 2007020393 | 8459462 | 1,949 | 975 | 974 | 352 | 176 | 176 |
| 2007-08 | 2007020608 | 8470281 | 1,948 | 974 | 974 | 193 | 97 | 96 |
| 2019-20 | 2019020163 | 8477512 | 1,718 | 745 | 973 | 9 | 9 | 0 |
| 2011-12 | 2011020091 | 8469454 | 1,945 | 973 | 972 | 422 | 211 | 211 |

## 9. Dressed-skater validation

Across 49,084 team-games, dressed counts are: **0: 16, 15: 4, 16: 13,
17: 147, 18: 48,900, 19: 3, 20: 1**. All **184** exceptions follow as
`gameId/team=count`; zeroes correspond to the eight unavailable games.

- **2007-08:** `2007020051/BOS=17`, `2007020055/FLA=17`, `2007020105/FLA=17`, `2007020107/CAR=17`, `2007020205/BUF=17`, `2007020417/OTT=17`, `2007020523/CAR=17`, `2007020573/MTL=17`, `2007020643/CAR=17`, `2007020786/OTT=17`, `2007020949/OTT=17`, `2007020991/PIT=17`, `2007021032/CAR=17`, `2007021052/NYI=17`, `2007020011/CHI=0`, `2007020011/MIN=0`
- **2008-09:** `2008020160/MIN=19`, `2008020185/PHI=17`, `2008020277/DET=17`, `2008020471/NYI=17`, `2008020574/PHI=17`, `2008020609/WSH=17`, `2008020703/DET=17`, `2008020928/NYI=17`, `2008020940/NYI=17`, `2008020967/TBL=17`, `2008021009/NYI=17`, `2008021114/COL=17`, `2008021162/CGY=16`, `2008021183/CGY=17`, `2008021194/CGY=17`, `2008021212/CGY=15`, `2008021226/CGY=15`, `2008021230/DET=17`, `2008020259/BOS=0`, `2008020259/TOR=0`, `2008020409/CGY=0`, `2008020409/DET=0`, `2008021077/PHX=0`, `2008021077/VAN=0`, `2008030311/CAR=0`, `2008030311/PIT=0`
- **2009-10:** `2009020079/MIN=19`, `2009020346/MIN=17`, `2009020373/NYR=17`, `2009020522/MIN=17`, `2009020655/TBL=20`, `2009020711/EDM=17`, `2009020789/MTL=17`, `2009020826/CAR=17`, `2009021066/DET=17`, `2009021077/DET=17`, `2009021229/TBL=17`, `2009030213/MTL=17`, `2009020081/CAR=0`, `2009020081/PIT=0`, `2009020658/DAL=0`, `2009020658/NYI=0`, `2009020885/CBJ=0`, `2009020885/SJS=0`
- **2010-11:** `2010020027/NJD=15`, `2010020036/NJD=16`, `2010020064/DET=17`, `2010020148/NSH=17`, `2010020334/NJD=17`, `2010020858/FLA=17`, `2010021017/EDM=17`, `2010021061/CHI=17`, `2010021075/DET=17`, `2010021172/FLA=17`, `2010021192/EDM=16`, `2010021204/MIN=17`, `2010021204/VAN=17`, `2010021227/ATL=17`
- **2011-12:** `2011020268/EDM=17`, `2011020419/CAR=17`, `2011020618/DET=17`, `2011020676/EDM=17`, `2011021007/MIN=17`
- **2012-13:** `2012020374/ANA=17`, `2012020696/CAR=17`
- **2013-14:** `2013020290/DET=17`, `2013020553/BUF=16`, `2013020702/COL=17`, `2013021139/EDM=17`
- **2014-15:** `2014020126/LAK=17`, `2014020444/MIN=17`, `2014021077/PIT=17`, `2014021105/PIT=17`, `2014021150/PIT=17`, `2014021220/PIT=17`
- **2015-16:** `2015020931/CAR=17`, `2015030114/FLA=17`
- **2016-17:** `2016020228/NYR=17`, `2016020601/VAN=17`, `2016020712/COL=17`, `2016021130/BUF=17`, `2016021145/TBL=17`, `2016021179/TBL=17`
- **2018-19:** `2018021212/ANA=17`
- **2019-20:** `2019020248/BOS=17`, `2019020422/CHI=17`, `2019020967/OTT=17`
- **2020-21:** `2020020142/COL=17`, `2020020162/VGK=17`, `2020020197/CAR=17`, `2020020321/COL=17`, `2020020478/WSH=17`, `2020020522/TBL=17`, `2020020569/VGK=17`, `2020020579/VGK=16`, `2020020620/VGK=17`, `2020020644/TBL=17`, `2020020764/VGK=15`, `2020020794/VGK=17`, `2020020814/WSH=17`, `2020020821/VGK=17`, `2020020830/WSH=17`, `2020020835/VGK=17`, `2020020851/VGK=17`, `2020020856/WSH=17`, `2020020866/VGK=17`
- **2021-22:** `2021020030/COL=17`, `2021020368/COL=17`, `2021020394/STL=17`, `2021020406/STL=17`, `2021020432/STL=17`, `2021020456/FLA=16`, `2021020458/BOS=17`, `2021020459/CAR=16`, `2021020460/COL=16`, `2021020472/NJD=17`, `2021020480/EDM=17`, `2021020568/MTL=16`, `2021020700/TBL=16`, `2021020949/COL=17`, `2021020962/COL=17`, `2021021279/NYI=17`, `2021021281/VGK=17`, `2021021300/FLA=16`
- **2022-23:** `2022020010/EDM=17`, `2022020041/FLA=17`, `2022020262/FLA=17`, `2022020334/FLA=17`, `2022020389/FLA=17`, `2022020474/FLA=17`, `2022020479/BUF=17`, `2022020881/EDM=17`, `2022020898/EDM=17`, `2022020950/NYR=17`, `2022020952/NSH=17`, `2022020968/NYR=16`, `2022020976/NYR=17`, `2022020991/NYR=16`, `2022021101/MTL=17`, `2022021128/ARI=17`, `2022021165/ARI=17`, `2022021247/WSH=17`, `2022021261/WSH=17`, `2022021277/WSH=17`, `2022021287/CBJ=17`, `2022021289/TOR=17`
- **2023-24:** `2023020004/OTT=17`, `2023020008/LAK=17`, `2023020009/EDM=17`, `2023020009/VAN=17`, `2023020041/MIN=17`, `2023020159/EDM=17`, `2023020826/OTT=17`, `2023020867/DAL=17`, `2023021010/CBJ=17`, `2023021304/TBL=17`, `2023021310/EDM=17`
- **2024-25:** `2024020078/FLA=17`, `2024020817/CAR=17`, `2024021146/PHI=17`, `2024021232/EDM=17`, `2024021248/EDM=17`, `2024021269/TOR=17`, `2024021289/EDM=17`, `2024021306/EDM=17`, `2024030116/TOR=19`
- **2025-26:** `2025020538/TBL=17`, `2025020929/EDM=17`

The derivation replay changed **0 of 76** gzip files.
