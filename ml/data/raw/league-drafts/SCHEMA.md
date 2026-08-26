# League draft-history snapshots — schema and interpretation

Raw snapshots of the three Google Sheets that hold the SportsNot(TM) fantasy-hockey
league's playoff-draft history, plus a per-tab reading of what the cells actually mean.

**The CSVs are raw. All interpretation lives in this file.** Nothing was cleaned,
reordered, deduplicated, or normalized — trailing spaces, typos, stray cells, `#N/A`
and stale duplicate tabs are all preserved on purpose so downstream parsers see the
true shape.

Open items that still need a league member's answer are in `OPEN_QUESTIONS.md`.

---

## 1. Provenance

| # | Spreadsheet title | Spreadsheet ID | Season covered |
|---|---|---|---|
| 1 | `SportsNot(TM) 2026 Fantasy Hockey` | `11jklDKn0xTYwW4A4Is9FDggj6q-fdvkuVnoo9A-M7j8` | 2026 playoffs (R1, R2 only — see §4.3) |
| 2 | `SportsNot(TM) 2025 Fantasy Hockey` | `1ExXl0jmsYSNotlOUQBQmi-soUZzWPd3N45BC-aIZwU0` | 2025 playoffs |
| 3 | `SportsNot(TM) Fantasy Hockey` | `1-LBNUxnuSgPLm7BUvYw2FFD2yYkP7BjxdsVNhbd5jb8` | 2024 playoffs |

Snapshot date: 2026-08-25.

### Files

`sheet1.xlsx`, `sheet2.xlsx`, `sheet3.xlsx` are the **unmodified Google `.xlsx` exports**
(`/export?format=xlsx`), each containing all four of its workbook's tabs. They carry
the non-value layer — formulas, merges, fill colours, strike-through, hyperlinks — which
a CSV cannot. §5, §6 and §7 lean on them heavily.

The twelve CSVs are the **unmodified per-tab Google CSV exports**
(`/export?format=csv&gid=<GID>`), byte-for-byte as served: CRLF line endings, no
trailing newline, padded to each tab's used rectangle. A `.gitattributes` in this
directory marks them binary so git cannot rewrite those line endings.

| File | Sheet / tab | GID | Rows | Cols |
|---|---|---|---|---|
| `sheet1__round-1.csv` | 1 / `Round 1` | 746784285 | 49 | 9 |
| `sheet1__round-2.csv` | 1 / `Round 2` | 1558839250 | 41 | 13 |
| `sheet1__round-3-4.csv` | 1 / `Round 3+4` | 1709664086 | 49 | 13 |
| `sheet1__wins.csv` | 1 / `Wins` | 409897040 | 13 | 3 |
| `sheet2__round-1.csv` | 2 / `Round 1` | 746784285 | 49 | 15 |
| `sheet2__round-2.csv` | 2 / `Round 2` | 1558839250 | 49 | 13 |
| `sheet2__round-3-4.csv` | 2 / `Round 3+4` | 1709664086 | 49 | 13 |
| `sheet2__wins.csv` | 2 / `Wins` | 409897040 | 13 | 3 |
| `sheet3__round-1.csv` | 3 / `Round 1` | 0 | 41 | 8 |
| `sheet3__round-2.csv` | 3 / `Round 2` | 156531731 | 41 | 10 |
| `sheet3__round-3-round-4.csv` | 3 / `Round 3 + Round 4` | 2028824781 | 41 | 10 |
| `sheet3__wins.csv` | 3 / `Wins` | 2114047094 | 21 | 3 |

Every file is non-empty, and every row count above equals the used-range row count of
the corresponding xlsx worksheet. Cell references in this document are 1-based A1
notation, identical between the CSV and the source tab (no rows or columns were dropped
from the top or left).

Note that sheets 1 and 2 share GIDs tab-for-tab: sheet 1 was created by duplicating
sheet 2's workbook, which is also why one of its tabs still holds 2025 data (§4.3).

### CSV vs xlsx: two things render differently

* **Numbers.** The CSV carries display text (`16`); the xlsx carries the underlying
  double (`16.0`).
* **Dates.** The three `Last Updated` cells are real date serials with a `m/d` display
  format. The CSV shows `5/12`; the xlsx shows `2025-05-12`. **The year only exists in
  the xlsx**, and it is load-bearing evidence — see §4.

---

## 2. The layout, in one picture

Every round tab in all three sheets is the **same shape**: four stacked per-manager
roster blocks in columns A–E (round 1) or A–G (rounds 2, 3+4), with free-floating notes
and statistics blocks scattered to the right.

It is *not* a draft board — managers are stacked vertically, not spread across columns,
and the grid says nothing about pick sequence.

```
      A          B                C                D          E              F         G
 1               Position         Player           Team       Points ...     (free)    (free)
 2 ┌─ Ben        Forward 1        <player>         <team>     <pts>
 3 │             Forward 2        <player>         <team>     <pts>
   │             Forward 3..5, Defense 1..3, Goalie 1, [IR - F, IR - D]
13 └─            Total                             <total>
14 ┌─ Judah      Forward 1        ...                                   <- next block starts
```

* **Row 1 is the only header row.** Column headers are `""`, `"Position "`, `"Player "`,
  `"Team"`, then the points columns (§5). Note the trailing spaces in `Position ` and
  `Player `.
* **Column A is a merged cell spanning each block.** Every round tab has exactly four
  merge ranges and nothing else merged: `A2:A13`, `A14:A25`, `A26:A37`, `A38:A49` on
  12-row-block tabs, and `A2:A11`, `A12:A21`, `A22:A31`, `A32:A41` on 10-row-block tabs.
  In the CSV a merge renders as the value on the first row and `""` on the rest, so a
  parser must forward-fill column A. The merge ranges are the authoritative block
  boundaries.
* **Block order in column A is always Ben, Judah, Kyle, Levi** — alphabetical, and *not*
  the draft order. Never infer pick order from block order.
* **Each block ends with a `Total` row** whose value sits in column E.
* **There are no footer rows.** The last populated row is the last block's `Total`.
* Block length: 12 rows (10 roster slots + IR-F + IR-D + Total) where IR slots exist,
  10 rows otherwise. So `4 × 12 + 1 = 49` rows, or `4 × 10 + 1 = 41`.
* Every round tab also carries an `autoFilter` over the roster range (e.g.
  `$A$1:$G$41`) — cosmetic, no effect on the data.

### Blocks are colour-coded, and the colours are stable across all three seasons

Each manager's block has a solid background fill, the same in all nine round tabs of all
three workbooks:

| Manager | Fill (ARGB) | Colour |
|---|---|---|
| Ben | `FFF4CCCC` | pale red |
| Judah | `FFCFE2F3` | pale blue |
| Kyle | `FFFFF2CC` | pale yellow |
| Levi | `FFD9EAD3` | pale green |

This is an independent confirmation of the manager mapping in §6, and lets a parser
identify a block by fill rather than by row arithmetic. One caveat: Kyle's pale yellow
`FFF2CC` is **not** the same as the pure yellow `FFFF00` used as a row highlight in one
tab (§4.1) — don't conflate them.

The `Wins` tabs have no fills at all.

### The right-hand annotation area

The right-hand side of each tab holds unrelated free-text blocks (`Notes`, `Statistics`,
`Scoring`, `Teams Scored`, `Draft Order:`/`Order`, `Last Updated`, `Current Max`,
`Current Winner`, `Round N Point Potential per Series`). **Their column positions differ
from tab to tab** and they are vertically offset to sit next to whatever roster row they
happened to be typed beside — the vertical position carries no meaning. Per-tab cell
maps are in §4. A parser should read columns A–E (round 1) or A–G (rounds 2/3+4) and
treat everything to the right as out-of-band annotation.

Two cells in that area are **hyperlinks** (present in every round tab, target identical
in all three workbooks): the `Statistics` labels link to
`https://www.nhl.com/stats/skaters?reportType=season&seasonFrom=20232024&seasonTo=20232024&gameType=2&position=F&sort=pointsPerGame&page=0&pageSize=50`.
The season is hardcoded to **2023-24** even in the 2025 and 2026 workbooks — copied
forward and never updated, so it says nothing about the tab's own season.

Sheet 3's three round tabs each anchor the same embedded **1512×2016 JPEG** at
column H, row 4 (`xl/media/image1.jpg`, 199 KB — it is what makes `sheet3.xlsx` 20×
larger than the other two). Sheets 1 and 2 have no images.

**There are no cell comments or notes in any of the three workbooks** — no
`comments*.xml` or `threadedComments*.xml` parts exist. Everything annotated is
annotated as cell text, fill, or strike-through.

---

## 3. Roster slots and how picks are recorded

### Slot labels (column B), verbatim

| Label | Meaning | Present in |
|---|---|---|
| `Forward 1` … `Forward 5` | 5 forward picks | all round tabs |
| `Defense 1` … `Defense 3` | 3 defenseman picks | all round tabs |
| `Goalie 1` | goalie/team pick (§3.2) | all round tabs |
| `IR - F` | injured-reserve forward | sheet1 R1 (struck through), sheet1 R3+4, sheet2 all 3 rounds |
| `IR - D` | injured-reserve defenseman | sheet1 R1 (struck through), sheet1 R3+4, sheet2 all 3 rounds |
| `Total` | block subtotal / running total | sheet1 all, sheet2 all, sheet3 R1 |
| `Total across Rounds` | same thing, renamed | sheet3 R2, sheet3 R3+4 |

### 3.1 The IR slot has a life cycle, and strike-through records its end

* Sheet 3 (2024): **no** `IR - F` / `IR - D` rows in any round. The rule didn't exist.
* Sheet 2 (2025): present and used in all three rounds, with `Activated` flags.
* Sheet 1 (2026): present in `Round 1`, but **every IR row is struck through** —
  `B11:D11`, `B12:D12`, `B23:D23`, `B24:D24`, `B35:D35`, `B36:D36`, `B47:D47`,
  `B48:D48`, i.e. the IR-F and IR-D rows of all four blocks, and nothing else in any
  workbook is struck through. In `Round 2` the rows are gone entirely (10-row blocks).

Read together: IR was introduced for 2025 and retired during 2026 — struck out in
round 1, deleted in round 2. **The strike-through is invisible in the CSV**, so a
parser reading `sheet1__round-1.csv` alone would treat the (empty) 2026 IR rows as
live slots.

### 3.2 Draft order — recorded, but only as a list

There are **no pick numbers anywhere**. Draft order appears once per tab as a short list
of four manager names in a floating block:

| Tab | Cells | Label | Order |
|---|---|---|---|
| sheet1 R1 | I6:I9 | *(none — sits under the `Statistics` header at I1)* | Kyle, Ben, Evi, Judah |
| sheet1 R2 | J6:M6 | `Draft Order:` (J5) | Judah, Ben, Levi, Kyle |
| sheet1 R3+4 | J7:M7 | `Draft Order:` (J6) | Judah, Ben, Levi, Kyle |
| sheet2 R1 | — | *(absent)* | — |
| sheet2 R2 | J6:M6 | `Draft Order:` (J5) | Judah, Ben, Levi, Kyle |
| sheet2 R3+4 | J7:M7 | `Draft Order:` (J6) | Judah, Ben, Levi, Kyle |
| sheet3 R1 | G10:G13 | `Order` (G9) | Levi, Ben, Kyle, Judah |
| sheet3 R2 | I10:I13 | `Order` (I9) | Ben, Levi, Judah, Kyle |
| sheet3 R3+4 | I10:I13 | `Order` (I9) | Ben, Kyle, Judah, Levi |

Note the two orientations: sheet 3 writes the order **down a column**, sheets 1 and 2
write it **across a row** — except sheet1 R1, which writes it down a column. Reading
order (left-to-right or top-to-bottom) is taken to be pick 1 through pick 4; nothing in
the sheet states this explicitly.

**Snake direction is not recorded and cannot be recovered from these sheets.** Within a
block, roster rows are in slot order (`Forward 1`, `Forward 2`, …), which is a position
label, not a pick index — so there is no way to tell whether a round reversed the order,
nor which slot was taken at which overall pick. Only the four-manager sequence per round
survives. See `OPEN_QUESTIONS.md` Q1.

`sheet2__round-1.csv` records no order at all; its right-hand area holds the
`Eliminated Teams:` block instead.

### 3.3 Goalie / team picks — three different conventions

The `Goalie 1` slot is a **team** pick, not a player pick: you get the team's goalie
production, scored as wins and shutouts (§5). How it is written changed every year:

| Sheet | Convention | Examples (Player column) |
|---|---|---|
| 3 (2024) | `<Nickname> Goalie (<goalie's personal name>)`, sometimes without the word `Goalie`, sometimes without the name | `Panthers Goalie (Sergei Bobrovsky)`, `Rangers (Igor Shesterkin)`, `Canucks Goalie (Thatcher Demko)`, `Oilers Goalie`, `Avalanche Goalie` |
| 2 (2025) | bare team nickname, duplicated into the Team column | `Panthers`, `Jets`, `Oilers`, `Capitals`, `Stars`, `Hurricanes` |
| 1 (2026) | full `City Nickname` | `Carolina Hurricanes`, `Colorado Avalanche`, `Edmonton Oilers`, `Buffalo Sabers`, `Vegas Knights`, `Buffalo Sabres` |

In sheet 1's `Round 3+4` (a stale copy of sheet 2's — §4.3) the sheet-2 bare-nickname
form is what appears.

So a goalie pick is identified by team in sheets 1 and 2, and by team *plus* an
often-present goalie personal name in sheet 3. A parser must resolve the `Goalie 1` row
against a team vocabulary, not a player vocabulary, and must strip the `(...)` suffix
and the word `Goalie` in sheet 3.

### 3.4 Player name format

`First Last`, with these exceptions and defects:

* **Last name only** — `sheet3__round-3-round-4.csv` C33 `McDavid`, C39 `Makar`.
* **Diacritics inconsistent for the same player** — `Martin Nečas`
  (`sheet2__round-1.csv` C31) vs `Martin Necas` (`sheet1__round-1.csv` C28,
  `sheet1__round-2.csv` C32).
* **No periods in initials** — `JT Miller ` (`sheet3__round-1.csv` C13; also has a
  trailing space).
* **Trailing spaces** on some names — `Kyle Connor `, `John Carlson `, `JT Miller `.
* **Misspellings** (all left as-is):

| Cell | As written | Intended |
|---|---|---|
| `sheet3__round-1.csv` C5, `sheet3__round-2.csv` C5 | `Elias Petterson` | Elias Pettersson |
| `sheet3__round-2.csv` C7 | `Brady Skijei` | Brady Skjei |
| `sheet3__round-2.csv` C16 | `David Pastrank` | David Pastrnak |
| `sheet3__round-3-round-4.csv` C8 | `Aaraon Ekblad` | Aaron Ekblad |
| `sheet3__round-3-round-4.csv` C28 | `Brandon Mountour` | Brandon Montour |
| `sheet1__round-1.csv` C46 | `Buffalo Sabers` | Buffalo Sabres (spelled correctly at `sheet1__round-2.csv` C40) |

### 3.5 Team column

Nickname-only in sheets 2 and 3 (`Oilers`, `Panthers`, `Bruins `, `Hurricanes ` — note
the trailing spaces in sheet 3).

Sheet 1's `Round 1` and `Round 2` switch to **city names** (`Minnesota`, `Dallas`,
`Colorado`, `Edmonton`, `Boston`, `Carolina`, `Buffalo`, `Anaheim`, `Montreal`,
`Tampa Bay`) but are not consistent about it: `Kings` (`sheet1__round-1.csv` D17) is a
nickname, `Vegas` is neither a full city nor the usual nickname, `Philly`
(`sheet1__round-1.csv` D6) is slang for the city, and `Pittsburg` (D41, D45) and
`Monteral` (`sheet1__round-2.csv` D14, D17, D33) are misspellings.

One outright wrong value: `sheet3__round-3-round-4.csv` row 39 lists `Makar` with team
`Oilers`; Cale Makar played for Colorado. That row's points (12 / 20 / 32) are large
enough to matter, and the row is **not** highlighted as eliminated (§4.1), so the sheet
itself believed it was an Oilers player. See `OPEN_QUESTIONS.md` Q3.

---

## 4. Tab-by-tab

### 4.1 Sheet 3 — `SportsNot(TM) Fantasy Hockey` = **2024** playoffs

**How the season was determined.** Two independent lines, one of them decisive:

1. **The `Last Updated` date cells carry the year.** In the xlsx they are
   `2024-05-05` (`Round 1` G16), `2024-05-21` (`Round 2` I16) and `2024-05-31`
   (`Round 3 + Round 4` I16). The CSV shows only `5/5`, `5/21`, `5/31`.
2. The playoff field agrees exactly. `Round 1` rosters draw on Avalanche, Bruins,
   Canucks, Capitals, Islanders, Knights, Kings, Lightning, Leafs, Jets, Oilers,
   Panthers, Predators, Rangers, Stars and Hurricanes — the 2024 first-round field.
   `Round 2` narrows to Avalanche, Bruins, Canucks, Panthers, Hurricanes, Rangers,
   Oilers, Stars: the eight 2024 second-round teams. `Round 3 + Round 4` narrows to
   Panthers, Oilers, Rangers, Stars — the 2024 conference finalists — and the 2024
   Stanley Cup was Panthers over Oilers. Goalie picks name Bobrovsky (Panthers),
   Shesterkin (Rangers), Demko (Canucks), Oettinger (Stars), Skinner (Oilers) and
   Kochetkov (Hurricanes), all correct for 2024.

The `Wins` tab records a 2024 champion and leaves 2025 blank, so the workbook was live
during 2024. Its title carries no year because it was the league's only sheet at the
time.

#### `sheet3__round-1.csv` — round 1 draft + round-1 scoring

41 rows × 8 cols. Header row 1: `""`, `Position `, `Player `, `Team`, `Points`, `""`,
`""`, `Notes`. Blocks of 10 rows (no IR), per the merge ranges `A2:A11`, `A12:A21`,
`A22:A31`, `A32:A41`, each ending in a `Total` row with the value in column E.

Example rows (verbatim):

```
A1:H1    ,Position ,Player ,Team,Points,,,Notes
A2:E2    Ben,Forward 1,Nathan MacKinnon,Avalanche,9
A10:E10  ,Goalie 1,Panthers Goalie (Sergei Bobrovsky),Panthers,8
A11:E11  ,Total,,,36
A12:E12  Judah ,Forward 1,Leon Draisaitl,Oilers,10
A40:E40  ,Goalie 1,Hurricanes Goalie (Pyotr Kochetkov),Hurricanes,8
```

Annotation cells: `H1` `Notes`; `H2` scoring reminder; `G9` `Order` with `G10:G13` =
Levi, Ben, Kyle, Judah; `G15` `Last Updated` / `G16` `5/5` (= 2024-05-05); `G18`
`Current Max` / `G19` `53`; `G21` `Current Winner` / `G22` `Kyle `; `H27` `Statistics`
(hyperlinked); `H31` `Scoring` with `H32:H33` the scoring rules; `H36` `Teams Scored`
(no values beneath); `H39` `Round 1 Point Potential per Series` / `H40` `23.5`.

**Irregularity:** `F24`/`G24` hold a stray second header pair `Points when drafted` /
`Current Points`, and `F25`/`G25` hold `5` / `8` for the Zach Hyman row — with a working
`E25 = =G25-F25` formula behind it. A single-row prototype of the three-column scheme
that rounds 2 and 3+4 later adopted properly. Only one player has these values, and
`E25`'s formula result (3) is what the `Total` sums.

#### `sheet3__round-2.csv` — round 2 draft + cumulative scoring

41 rows × 10 cols. Header row 1 gains the three-column points scheme (§5): `Points for
Round`, `Points when drafted`, `Current Total Points` in E, F, G. 10-row blocks, with
`Total across Rounds` in B.

```
A1:J1     ,Position ,Player ,Team,Points for Round,Points when drafted,Current Total Points,,,Notes
A2:G2     Ben,Forward 1,Nathan MacKinnon,Avalanche,5,9,14
A10:G10   ,Goalie 1,Panthers Goalie (Sergei Bobrovsky),Panthers,8,0,8
A11:E11   ,Total across Rounds,,,66
A32:G32   Levi ,Forward 1,Connor McDavid,Oilers,9,12,21
```

Annotations: `J1` `Notes`, `J2` scoring reminder; `I9` `Order` / `I10:I13` = Ben, Levi,
Judah, Kyle; `I15` `Last Updated` / `I16` `5/21` (= 2024-05-21); `I18` `Current Max` /
`I19` `108`; `I21` `Current Winner` / `I22` `Levi `; `J27` `Statistics` (hyperlinked);
`J31` `Scoring` / `J32:J33` rules; `J36` `Teams Scored`; `J39` `Round 2 Point Potential
per Series` / `J40` `47.75`.

#### `sheet3__round-3-round-4.csv` — rounds 3 **and** 4 combined

41 rows × 10 cols, same layout as round 2. This tab covers the conference finals and the
Stanley Cup Final as **one** drafted round: one roster per manager, one set of points.
The two NHL rounds are not separable in the data. Note the label drift — the tab is
named `Round 3 + Round 4` but the statistics block at `J39` says `Round 3 Point
Potential per Series`.

```
A1:J1     ,Position ,Player ,Team,Points for Round,Points when drafted,Current Total Points,,,Notes
A2:G2     Ben,Forward 1,Sam Reinhart,Panthers,7,9,16
A7:H7     ,Defense 1,Dmitry Kulikov,Panthers,5,0,2,(+3 because of Jacob Trouba for Round 3)
A33:G33   Levi ,Forward 1,McDavid,Oilers,7,24,31
A39:G39   ,Defense 1,Makar,Oilers,12,20,32
A41:E41   ,Total across Rounds,,,172
```

**Mid-round substitution, and the adjustment is in the formula.** `H7` reads
`(+3 because of Jacob Trouba for Round 3)` on Ben's `Defense 1` row, and `E7` is
literally `=3 + (G7 - F7)` — the only hand-patched per-player formula in any workbook.
`G7-F7` is `2-0 = 2` (Kulikov), plus a hardcoded 3 for Trouba, giving the 5 shown in the
CSV. So the row's arithmetic does close once the formula is visible; from the CSV alone
it looks broken. Who actually held the slot in which round is still unstated — see
`OPEN_QUESTIONS.md` Q2.

**Yellow row highlighting marks round-3 eliminations.** This is the one tab with a fifth
fill colour: pure yellow `FFFFFF00` over columns B–D of these rows —

| Manager | Highlighted rows | Player / team |
|---|---|---|
| Ben | *(none)* | his whole block is Panthers |
| Judah | 13, 15, 16, 18, 20 | Wyatt Johnston (Stars), Chris Kreider (Rangers), Jamie Benn (Stars), K'Andre Miller (Rangers), Rangers Goalie |
| Kyle | 22, 23, 24, 27, 30 | Jason Robertson, Tyler Seguin, Roope Hintz, Ryan Suter, Stars Goalie — all Stars |
| Levi | 34, 36, 38, 39 | Artemi Panarin (Rangers), Mika Zibanejad (Rangers), Adam Fox (Rangers), Miro Heiskanen (Stars) |

Every highlighted row is a **Rangers or Stars** player, and Rangers and Stars are exactly
the two teams that lost the 2024 conference finals. Nothing on an Oilers or Panthers row
is highlighted. So **yellow = eliminated after round 3, i.e. did not play round 4**. None
of this is in the CSV. (This is also why row 39 `Makar`/`Oilers` is un-highlighted — the
sheet treated it as an Oilers player; see §3.5.)

Annotations: `J1`/`J2` notes; `I9` `Order` / `I10:I13` = Ben, Kyle, Judah, Levi; `I15`
`Last Updated` / `I16` `5/31` (= 2024-05-31); `I18` `Current Max` / `I19` `172`; `I21`
`Current Winner` / `I22` `Levi `; `J27` `Statistics` (hyperlinked); `J31` `Scoring` /
`J32:J33`; `J36` `Teams Scored`; `J39` potential / `J40` `113`.

#### `sheet3__wins.csv` — league champions by year

21 rows × 3 cols, and the one tab that is **not** in the standard shape.

**Rows 1–9 are entirely empty.** The header row that sheets 1 and 2 carry (`Year`,
`Gemmell Cup Winner`, `NHL Stanley Cup Winner`) is absent here; data starts cold at
row 10. Columns are positional: A = year, B = league champion, C = NHL Stanley Cup
winner. No fills, no formulas.

```
A10:C10  2014,,Kings
A14:C14  2018,Ben,Capitals
A15:C15  2019,Levi,St. Louis Blues
A20:C20  2024,Levi,Panthers
A21:C21  2025,,
```

2014–2017 have an NHL champion but no league champion — the league's own records start
in 2018. Row 21 is a bare `2025` placeholder written before the 2025 playoffs.

`Lighting` at C16 and C17 is a misspelling of Lightning. The trophy is the "Gemmell Cup".

### 4.2 Sheet 2 — `SportsNot(TM) 2025 Fantasy Hockey` = **2025** playoffs

**How the season was determined.** The `Last Updated` cells in the xlsx read
`2025-05-04` (`Round 1` G18), `2025-05-12` (`Round 2` I18) and `2025-05-25` (`Round 3+4`
I19). The title agrees, and so does the field: `sheet2__round-1.csv` H5:O5 lists the
eight first-round losers — Blues, Avalanche, Wild, Kings, Senators, Lightning,
Canadiens, Devils — precisely the 2025 set, and the 16 teams across round-1 rosters are
the 2025 field. `Round 2` narrows to Oilers, Hurricanes, Jets, Panthers, Capitals,
Leafs, Stars, Knights; `Round 3+4` to Oilers, Panthers, Hurricanes, Stars. The 2025 Cup
was Panthers over Oilers.

#### `sheet2__round-1.csv`

49 rows × 15 cols — the widest tab, because of the `Eliminated Teams:` block. 12-row
blocks (IR-F and IR-D present): merges `A2:A13`, `A14:A25`, `A26:A37`, `A38:A49`.

```
A1:I1     ,Position ,Player ,Team,Points,,,Notes,Statistics
A2:E2     Ben,Forward 1,Nikita Kucherov,Lightning,4
A12:E12   ,IR - D,Haydn Fleury,Jets,0
A13:E13   ,Total,,,52
A45:H45   ,Defense 3,Luke Hughes,Devils,0,Not playing,,Round 1 Point Potential per Series
A48:F48   ,IR - D,Jake Sanderson,Senators,3,Activated
```

Annotations: `H1` `Notes` / `I1` `Statistics` (hyperlinked); `H2` goalie-scoring
reminder; `H4` `Eliminated Teams:` with `H5:O5` = Blues, Avalanche, Wild, Kings,
Senators, Lightning, Canadiens, Devils; `G17` `Last Updated` / `G18` `5/4`
(= 2025-05-04); `G20` `Current Max` / `G21` `59`; `G25` `Current Winner` / `G26`
`Kyle `; `H31` a second `Statistics` (also hyperlinked); `H37` `Scoring` / `H38:H39`
rules; `H42` `Teams Scored`; `H45` `Round 1 Point Potential per Series` / `H46` `54.25`.

**Per-row status flags live in column F on round-1 tabs** (F and G are unused by the
roster block there): `F45` `Not playing`, `F48` `Activated`.

#### `sheet2__round-2.csv`

49 rows × 13 cols, 12-row blocks. Three-column points scheme in E/F/G.

```
A1:K1     ,Position ,Player ,Team,Points for Round,Points when drafted,Current Total Points,,,Notes,Statistics
A2:G2     Ben,Forward 1,Connor McDavid,Oilers,6,11,17
A4:H4     ,Forward 3,Mark Scheifele,Jets,5,6,11,Dropped
A11:H11   ,IR - F,Connor McMichael,Capitals,1,5,6,Activated
A13:E13   ,Total,,,88
```

Annotations: `J1` `Notes` / `K1` `Statistics` (hyperlinked); `J2` reminder; `J5` `Draft
Order:` / `J6:M6` = Judah, Ben, Levi, Kyle; `I17` `Last Updated` / `I18` `5/12`
(= 2025-05-12); `I20` `Current Max` / `I21` `100`; `I25` `Current Winner` / `I26`
`Kyle `; `J31` `Statistics` (hyperlinked); `J37` `Scoring` / `J38:J39`; `J42` `Teams
Scored`; `J45` `Round 2 Point Potential per Series` / `J46` `37.75`.

**Per-row status flags live in column H on round-2 and round-3+4 tabs** (E/F/G are taken
by points): `H4` `Dropped`, `H11` `Activated`, `H44` `Dropped`, `H48` `Activated`.

#### `sheet2__round-3-4.csv`

49 rows × 13 cols, 12-row blocks. Header row 1 stops at column G here — the `Notes` /
`Statistics` labels have slipped down to row 2 (`J2`, `K2`), so this tab's right-hand
blocks all sit one row lower than round 2's.

```
A1:G1     ,Position ,Player ,Team,Points for Round,Points when drafted,Current Total Points
A2:K2     Ben,Forward 1,Leon Draisaitl,Oilers,17,16,33,,,Notes,Statistics
A10:G10   ,Goalie 1,Oilers,Oilers,14,0,14
A13:E13   ,Total,,,160
A27:I27   ,Forward 2,Roope Hintz,Stars,2,10,12,,Levi
```

Annotations: `J2`/`K2` labels (K2 hyperlinked); `J3` reminder; `J6` `Draft Order:` /
`J7:M7` = Judah, Ben, Levi, Kyle; `I18` `Last Updated` / `I19` `5/25` (= 2025-05-25);
`I21` `Current Max` / `I22` `163`; `I26` `Current Winner` / `I27` `Levi`; `J32`
`Statistics` (hyperlinked); `J38` `Scoring` / `J39:J40`; `J43` `Teams Scored`; `J46`
`Round 3+4 Point Potential per Series` / `J47` `59.25`.

As in sheet 3, rounds 3 and 4 are one combined drafted round.

**This tab hides two roster swaps in its `Total` formulas** — see §5.

#### `sheet2__wins.csv`

13 rows × 3 cols. Proper header at row 1, then 2014–2025 one row each. No formulas.

```
A1:C1    Year,Gemmell Cup Winner,NHL Stanley Cup Winner
A6:C6    2018,Ben,Capitals
A7:C7    2019,Evi,St. Louis Blues
A13:C13  2025,Evi,Panthers
```

Same table as `sheet3__wins.csv` with a header added, the 2025 result filled in, and
**every `Levi` replaced by `Evi`** — see §6.

### 4.3 Sheet 1 — `SportsNot(TM) 2026 Fantasy Hockey` = **2026** playoffs, partly

**How the season was determined.** Round 1's rosters include Porter Martone
(`sheet1__round-1.csv` C6), whose first NHL season is 2025-26, plus Logan Stankoven on
Carolina and Darren Raddysh on Tampa Bay (`sheet1__round-2.csv` C3,
`sheet1__round-1.csv` C9), both post-2025 team situations. Anaheim and Buffalo appear as
playoff teams, which they were not in 2024 or 2025. Together with the title, that places
`Round 1` and `Round 2` in the **2026** playoffs.

**There is no 2026 date anywhere in this workbook.** `Round 1` has no date cell at all,
and the two that exist are 2025 leftovers: `Round 2` `I16` = `2025-05-12` and
`Round 3+4` `I19` = `2025-05-25`, both identical to sheet 2's. Combined with the empty
points columns, that is strong evidence nothing here was ever scored.

`Round 3+4` and `Wins` are **not 2026 data** — see below.

#### `sheet1__round-1.csv` — 2026 round 1, drafted but never scored

49 rows × 9 cols, 12-row blocks (IR present but struck through — §3.1). Same layout as
sheet 2's round 1.

**The entire `Points` column (E) is empty**, all four `Total` rows are empty **and hold
no formula at all** (the `sum(...)` formulas were deleted, not just starved of inputs),
and the statistics block reads `0`.

```
A1:I1     ,Position ,Player ,Team,Points,,,Notes,Statistics
A2:H2     Ben,Forward 1,Kirill Kaprizov,Minnesota,,,,Goalie points - 2 ponts per win + 2 for shutout
A6:I6     ,Forward 5,Porter Martone,Philly,,,,,Kyle
A10:D10   ,Goalie 1,Carolina Hurricanes,Carolina
A13:B13   ,Total
A24:C24   ,IR - D,","
```

Annotations: `H1` `Notes` / `I1` `Statistics` (hyperlinked); `H2` reminder; **`I6:I9` =
Kyle, Ben, Evi, Judah** — the draft order, with *no label above it* (it sits directly
under the `Statistics` header at `I1`); `G17` `Last Updated`, `G20` `Current Max`, `G25`
`Current Winner` — all three labels present with **empty value cells beneath**; `H31`
`Statistics` (hyperlinked); `H37` `Scoring` / `H38:H39` rules; `H42` `Teams Scored`;
`H45` `Round 1 Point Potential per Series` / `H46` `0`.

**Irregularity:** `C24` (Judah's `IR - D` player cell) contains a lone comma `,`. A
stray keystroke, not a player. It is CSV-quoted as `","` in the file.

**Irregularity:** this is the only tab whose draft-order list uses the name `Evi`
alongside four roster blocks labelled Ben / Judah / Kyle / Levi — direct evidence that
`Evi` and `Levi` are the same manager (§6).

#### `sheet1__round-2.csv` — 2026 round 2, drafted but never scored

41 rows × 13 cols. **10-row blocks — no `IR - F` / `IR - D` rows** (merges `A2:A11`,
`A12:A21`, `A22:A31`, `A32:A41`), unlike sheet 1's other two tabs.

All three points columns are empty. `E` holds no formulas here either. `Current Max` is
`0` and `Current Winner` renders as `#N/A` — the array formula
`INDIRECT(ADDRESS(1+MATCH(I19, E11:E41, 0), 1))` failing to match a max of 0 against
empty totals.

```
A1:K1     ,Position ,Player ,Team,Points for Round,Points when drafted,Current Total Points,,,Notes,Statistics
A2:J2     Ben,Forward 1,Jack Eichel,Vegas,,,,,,Goalie points - 2 ponts per win + 2 for shutout
A4:H4     ,Forward 3,Alex Tuch,Buffalo,,,,Dropped
A14:D14   ,Forward 3,Cole Caufield,Monteral
A22:I22   Kyle ,Forward 1,Matt Boldy,Minnesota,,,,,#N/A
```

Annotations: `J1` `Notes` / `K1` `Statistics` (hyperlinked); `J2` reminder; `J5` `Draft
Order:` / `J6:M6` = Judah, Ben, Levi, Kyle; `I15` `Last Updated` / `I16` `5/12`
(= **2025**-05-12, a leftover); `I18` `Current Max` / `I19` `0`; `I21` `Current Winner` /
`I22` `#N/A`; `J27` `Statistics` (hyperlinked); `J31` `Scoring` / `J32:J33`; `J36`
`Teams Scored`; `J39` `Round 2 Point Potential per Series` / `J40` `0`. Status flags in
column H: `H4` and `H38` both `Dropped`.

#### `sheet1__round-3-4.csv` — **stale 2025 data, not 2026**

49 rows × 13 cols. Every roster cell is identical to `sheet2__round-3-4.csv`. Diffing the
two CSVs gives exactly six differing cells, all of them formula results:

| Cell | sheet1 | sheet2 | What it is |
|---|---|---|---|
| `E13` | `72` | `160` | Ben's `Total` |
| `E25` | `53` | `135` | Judah's `Total` |
| `E37` | `48` | `148` | Kyle's `Total` |
| `E49` | `66` | `163` | Levi's `Total` |
| `I22` | `72` | `163` | `Current Max` |
| `I27` | `Ben` | `Levi` | `Current Winner` |

Every player, team, `Points for Round`, `Points when drafted` and `Current Total Points`
value matches — including the 2025 conference finalists (Oilers, Panthers, Hurricanes,
Stars) and the `2025-05-25` date. The 2026 workbook was created by duplicating the 2025
one; `Round 1` and `Round 2` were cleared and re-drafted for 2026, and **`Round 3+4` was
never cleared**.

The formulas show it was not a blind copy, though: the cross-tab references were
**re-pointed to sheet 1's new round-2 geometry**. Sheet 2 has
`E13 = sum(E2:E3) + sum(E5:E10) + E11 + 'Round 2'!E13` (12-row blocks, totals at
E13/E25/E37/E49); sheet 1 has the same expression ending in `'Round 2'!E11` (10-row
blocks, totals at E11/E21/E31/E41). Someone fixed up the references for the new layout
and left the 2025 rosters in place.

That also explains the `Total` gap exactly. `Total` is cumulative (§5), so sheet 2's
value = round-3+4 contribution + round-2 total: 72+88=160, 53+82=135, 48+100=148,
66+97=163. Sheet 1's round-2 totals are blank, so only the contribution shows.
`Current Winner` flips to `Ben` purely as a consequence, and is **not** a real result.

**This tab must be excluded from any 2026 training data, and deduplicated against
`sheet2__round-3-4.csv` rather than treated as a second observation.**

#### `sheet1__wins.csv`

13 rows × 3 cols. **Identical to `sheet2__wins.csv`** — same header, same 2014–2025 rows,
same `Evi` spelling. No 2026 row. Also a leftover of the duplication; it carries no
information beyond sheet 2's copy.

---

## 5. Points, scoring, and what the formulas reveal

### Column meanings

| Column | Round 1 tabs | Rounds 2 / 3+4 tabs |
|---|---|---|
| E | `Points` — points scored by that player during round 1. **Entered by hand.** | `Points for Round` — **derived**, `=G - F` |
| F | *(free; used for status flags)* | `Points when drafted` — the player's playoff points to date at the moment of this round's draft. Entered. |
| G | *(free; used for the Last Updated / Current Max / Current Winner labels)* | `Current Total Points` — the player's cumulative playoff points now. Entered. |

**On rounds 2 and 3+4 the `Points for Round` column is not source data.** Every
per-player cell in E is the formula `=G - F` (or `=G-F`; both spellings occur), so the
maintained inputs are F and G, and E is a display-only delta. Anything downstream that
treats E as the primary observation is reading a derived column — and it inherits any
error in F or G. The one exception is `sheet3__round-3-round-4.csv` `E7`, hand-patched to
`=3 + (G7 - F7)` for the Trouba substitution (§4.1).

`Points when drafted` is a **league-wide** running total for that player, not that
manager's total: sheet 2 has Connor McDavid at 11 `Points when drafted` in round 2
(`sheet2__round-2.csv` F2, Ben's pick) which is exactly the 11 he scored for *Levi* in
round 1 (`sheet2__round-1.csv` E38). It exists to show whether a pick was a value pick
or a chalk pick.

The `Total` row's value sits in **column E**, not in G, even on tabs where E is
per-player round points.

### The scoring rule, as stated in the sheets

Repeated verbatim in every round tab's `Scoring` block:

```
Points = goals + assists.
goalie is 2 points/win + 2 for shutouts
```

and in the `Notes` block: `Goalie points - 2 ponts per win + 2 for shutout` (`ponts` is
a typo present in all nine round tabs).

### `Total` is cumulative, and each block's formula is hand-maintained

Round 1 totals are a plain sum of the nine starting slots — `=sum(E2:E10)` — with IR rows
excluded. Rounds 2 and 3+4 add the previous round's total by cross-tab reference, e.g.
`sheet3__round-2.csv` `E11 = =sum(E2:E10) + 'Round 1'!E11`. Sheet 3 says so outright by
naming the row `Total across Rounds`.

But the sums are **not** uniform. Each block's formula was edited by hand to skip or
include individual rows, and those edits are the only record of some roster changes:

| Formula (verbatim) | What it does |
|---|---|
| `sheet2` R1 `E49 = =sum(E38:E44) + E46 + E48` | Levi: skips `E45` (Luke Hughes, flagged `Not playing`), keeps the goalie, adds `E48` (IR-D Sanderson, flagged `Activated`) |
| `sheet2` R2 `E13 = =sum(E2:E3) + sum(E5:E11) + 'Round 1'!E13` | Ben: skips `E4` (Scheifele, `Dropped`), includes `E11` (IR-F McMichael, `Activated`) |
| `sheet2` R2 `E49 = =sum(E38:E43) + sum(E45:E46) + E48 + 'Round 1'!E49` | Levi: skips `E44` (Morrissey, `Dropped`), adds `E48` (IR-D Pietrangelo, `Activated`) |
| `sheet2` R3+4 `E13 = =sum(E2:E3) + sum(E5:E10) + E11 + 'Round 2'!E13` | Ben: skips `E4` (Sam Reinhart, 12) and swaps in `E11` (IR-F Verhaeghe, 15) — **with no text flag on either row** |
| `sheet2` R3+4 `E25 = =sum(E14:E16) + sum(E18:E22) + E23 + 'Round 2'!E25` | Judah: skips `E17` (Zach Hyman, 3) and swaps in `E23` (IR-F Connor Brown, 2) — **with no text flag on either row** |
| `sheet2` R3+4 `E37`, `E49` | Kyle and Levi: plain `sum(E26:E34)` / `sum(E38:E46)`, no edits |

The last two rows of that table resolve what looked from the CSV like broken arithmetic:
the round-3+4 contributions implied by the totals are 72 / 53 / 48 / 66, while summing
`Points for Round` over the nine written starters gives 69 / 54 / 48 / 66. Ben is +3
because Reinhart (12) was replaced by Verhaeghe (15); Judah is −1 because Hyman (3) was
replaced by Brown (2). Kyle and Levi match because their formulas are untouched.

**Consequence for the pipeline: on the round-3+4 tabs the roster as written is not the
roster as scored, and only the xlsx formulas say which is which.** Two of the eight
scored 2025 blocks have an undocumented starter→IR substitution. A CSV-only parser will
mis-attribute those points.

### `Current Max` and `Current Winner` are computed

* `Current Max` = `=MAX(E13, E25, E37, E49)` (or `MAX(E11, E21, E31, E41)` on 10-row-block
  tabs) — the highest block total.
* `Current Winner` = the array formula
  `{=INDIRECT(ADDRESS(1+MATCH(<max cell>, E11:E41, 0), 1))}` — it finds the row whose
  total equals the max and returns column A of that row, i.e. the manager name. It
  returns `#N/A` when there is nothing to match, which is why `sheet1__round-2.csv` `I22`
  reads `#N/A`.

Because it resolves by `MATCH` on the first equal value, a tie would silently report
only the earlier block. `sheet2__round-1.csv` is exactly that case: Kyle and Levi both
finish on 59, and the cell reports `Kyle `.

### `Point Potential per Series` — mean league points per series, with an inconsistent divisor

The formula is always the sum of all four blocks' starter ranges over a divisor:

```
=(SUM(E2:E10) + SUM(E14:E22) + SUM(E26:E34) + SUM(E38:E46)) / N
```

So it is "total points scored by the whole league this round ÷ N". `N` is the number of
NHL series in the round — but only sheet 3 gets that right:

| Tab | Divisor | Series actually in that round | Value |
|---|---|---|---|
| sheet3 R1 | **8** | 8 | 23.5 |
| sheet3 R2 | 4 | 4 | 47.75 |
| sheet3 R3+4 | **2** | 2 conference finals (+ the final) | 113 |
| sheet2 R1 | **4** | 8 | 54.25 |
| sheet2 R2 | 4 | 4 | 37.75 |
| sheet2 R3+4 | **4** | 2 (+ the final) | 59.25 |
| sheet1 R1 / R2 | 4 | — | 0 (no inputs) |

Sheets 1 and 2 hardcode `/4` in every round. The 2025 round-1 and round-3+4 figures are
therefore not comparable with sheet 3's. Treat this column as unreliable, or recompute
it. See `OPEN_QUESTIONS.md` Q4.

### The `Statistics` block

| Label | Meaning |
|---|---|
| `Last Updated` | date the sheet was last scored. A real date cell with a `m/d` format — **the CSV loses the year, the xlsx keeps it** |
| `Current Max` | highest block total; `MAX` formula |
| `Current Winner` | manager holding that max; array formula, `#N/A` when empty, first-match on ties |
| `Round N Point Potential per Series` | league points that round ÷ series count; divisor unreliable outside sheet 3 |
| `Teams Scored` | a label with **no values beneath it in any tab** |
| `Eliminated Teams:` | `sheet2__round-1.csv` only, `H5:O5` — the eight first-round losers |
| `Statistics` | a hyperlink to NHL skater stats, season hardcoded to 2023-24 in all three workbooks |

---

## 6. Managers

Four managers, stable across all three seasons. Column A always lists them
alphabetically (Ben, Judah, Kyle, Levi), which is not the draft order.

### Canonical ids

| Canonical id | Block fill | Sheet 1 (2026) | Sheet 2 (2025) | Sheet 3 (2024) |
|---|---|---|---|---|
| `ben` | `FFF4CCCC` | `Ben` | `Ben` | `Ben` |
| `judah` | `FFCFE2F3` | `Judah ` | `Judah ` | `Judah ` |
| `kyle` | `FFFFF2CC` | `Kyle ` | `Kyle ` | `Kyle ` |
| `levi` | `FFD9EAD3` | `Levi` (round tabs), `Evi` (`Wins` and the round-1 draft-order list) | `Levi` (round tabs), `Evi` (`Wins`) | `Levi ` / `Levi` |

Surface forms to fold into `levi`: `Levi`, `Levi ` (trailing space), `Evi`. For the
others: `Ben`, `Judah `, `Judah`, `Kyle `, `Kyle`. **Trailing whitespace is present in
the raw data and must be stripped when matching** — it appears both in column A block
labels and in `Current Winner` values (`Kyle `, `Levi `).

The block fills are identical across all three workbooks, so colour is an independent
key for the same four people.

There are no team names in this league, only manager first names, so no team→manager
mapping is needed.

### Why `Evi` = `levi`

Two independent lines of evidence:

1. `sheet3__wins.csv` and `sheet2__wins.csv` are the same year-by-year table. Every row
   sheet 3 attributes to `Levi` (2019, 2020, 2021, 2022, 2024), sheet 2 attributes to
   `Evi`. No row disagrees, and no year names both.
2. `sheet1__round-1.csv` lists the four-manager draft order at `I6:I9` as Kyle, Ben,
   **Evi**, Judah — in a workbook whose four roster blocks are labelled Ben, Judah,
   Kyle, **Levi**. `Evi` occupies the slot `Levi` must occupy.

`sheet2__round-3-4.csv` `I27` also names `Levi` as the 2025 `Current Winner`, matching
`Evi` as the 2025 champion in `sheet2__wins.csv` `B13`.

Treated as the same person throughout this document. Flagged for confirmation as
`OPEN_QUESTIONS.md` Q7 only because it is an inference, not a statement in the data.

### League champions (`Wins` tabs)

`Gemmell Cup Winner` is the league champion; `NHL Stanley Cup Winner` is the real
outcome. Rows 2014–2017 have only the NHL result — league records begin in 2018.

| Year | Champion (canonical) | NHL |
|---|---|---|
| 2018 | `ben` | Capitals |
| 2019 | `levi` | St. Louis Blues |
| 2020 | `levi` | Lightning (`Lighting` in the raw) |
| 2021 | `levi` | Lightning (`Lighting` in the raw) |
| 2022 | `levi` | Avalanche |
| 2023 | `kyle` | Knights |
| 2024 | `levi` | Panthers |
| 2025 | `levi` | Panthers |

No 2026 result is recorded in any sheet.

---

## 7. What lives only in the xlsx

A CSV-only pipeline silently loses all of this. Each item is documented above; this is
the checklist.

| Layer | What it carries | Where |
|---|---|---|
| Formulas | `Points for Round` is derived (`=G-F`); two undocumented roster swaps in the round-3+4 totals; the Trouba `+3` patch; `Current Winner` logic; the inconsistent potential divisor | §5 |
| Merged cells | authoritative block boundaries in column A | §2 |
| Fill colours | manager identity per block; `FFFF00` = eliminated after round 3 in `sheet3__round-3-round-4.csv` | §2, §4.1 |
| Strike-through | the 2026 IR slots being retired | §3.1 |
| Date serials | the year on every `Last Updated`, which dates each workbook and exposes sheet 1's two 2025 leftovers | §1, §4 |
| Hyperlinks | the `Statistics` NHL-stats link, season stuck at 2023-24 | §2 |
| Embedded image | one 1512×2016 JPEG on each of sheet 3's round tabs | §2 |
| Cell comments | **none exist** — checked, no `comments*.xml` in any workbook | §2 |

Still absent from both formats, because they were never recorded: **pick numbers and
snake direction** (§3.2), and **any 2026 scoring or 2026 round-3+4 draft** (§4.3).

## 8. Summary of usable draft observations

| Season | Round | File | Rosters | Scored | Caveat |
|---|---|---|---|---|---|
| 2024 | 1 | `sheet3__round-1.csv` | yes | yes | stray prototype cells at F24:G25 |
| 2024 | 2 | `sheet3__round-2.csv` | yes | yes | — |
| 2024 | 3+4 | `sheet3__round-3-round-4.csv` | yes | yes | Trouba `+3` patch; yellow = eliminated; `Makar`/`Oilers` bad row |
| 2025 | 1 | `sheet2__round-1.csv` | yes | yes | Kyle/Levi tie at 59 reported as Kyle |
| 2025 | 2 | `sheet2__round-2.csv` | yes | yes | 2 flagged `Dropped`, 2 flagged `Activated` |
| 2025 | 3+4 | `sheet2__round-3-4.csv` | yes | yes | **2 unflagged starter→IR swaps** (Ben, Judah) |
| 2026 | 1 | `sheet1__round-1.csv` | yes | **no** | IR rows struck through; stray `,` at C24 |
| 2026 | 2 | `sheet1__round-2.csv` | yes | **no** | no IR slots |
| 2026 | 3+4 | — | **absent** | — | `sheet1__round-3-4.csv` is a 2025 duplicate |

Six fully scored manager-rounds × 4 managers = 24 scored roster observations, plus 8
unscored 2026 roster observations.

---

# app-export-2026 (Supabase export of the in-app 2026 season)

Exported by the owner via the SQL editor per `APP_EXPORT.md`, assembled and validated
from 100-row chunks (raw chunks kept in `incoming/`).

## app-export-2026__draft-picks.csv — COMPLETE (240 rows, validated)

One row per pick, true pick order. Columns: `league_name, playoff_round, pick_number,
manager, team_name, position, player_id, player_name, team_id, nhl_team_name,
picked_at`. Literal string `null` means SQL NULL (skater picks have team_id/nhl_team_name
null; goalie/team picks have player_id/player_name null).

- Two leagues: **The Gemmell Cup** (nuttguy, judah18, gemmell.levi, bentunigold; no IR;
  36 picks/round = 5F/3D/1G x4) and **Press Play-offs** (nuttguy, Tobi,
  paul.markhauser, connor.fehr; IR enabled; 44 picks/round = +IR_F/IR_D x4).
- Rounds 1-3 only; no round-4 draft exists (round-3 rosters carried through the final).
- `position` is the SLOT the pick filled (F/D/G/IR_F/IR_D), and unlike the sheets the
  row order IS the pick sequence — `pick_number` is authoritative.
- Validated: counts match the DB (`incoming/pick-counts.csv`), pick numbers contiguous
  1..N per league-round, every manager-round has a legal roster composition.
- Manager usernames map via the alias file: nuttguy=kyle, bentunigold=ben,
  judah18=judah, gemmell.levi=levi; Press-only managers keep their usernames.
- Owner caveat: prefer round 3 for validation; rounds 1-2 may carry artifacts from
  mid-playoffs draft bugs (none were detected by the checks above, but stay lenient).

## app-export-2026__rosters.csv, app-export-2026__draft-order.csv — PENDING

Queries 2 and 3 in `APP_EXPORT.md`; same chunked procedure. Add their column notes
here when they land.
