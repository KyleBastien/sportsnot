# League draft-history snapshots — schema and interpretation

Raw snapshots of the three Google Sheets that hold the SportsNot(TM) fantasy-hockey
league's playoff-draft history, plus a per-tab reading of what the cells actually mean.

**The CSVs are raw. All interpretation lives in this file.** Nothing was cleaned,
reordered, deduplicated, or normalized — trailing spaces, typos, stray cells, `#N/A`
and stale duplicate tabs are all preserved on purpose so downstream parsers see the
true shape.

Open items that need a league member's answer are in `OPEN_QUESTIONS.md`.

---

## 1. Provenance

| # | Spreadsheet title | Spreadsheet ID | Season covered |
|---|---|---|---|
| 1 | `SportsNot(TM) 2026 Fantasy Hockey` | `11jklDKn0xTYwW4A4Is9FDggj6q-fdvkuVnoo9A-M7j8` | 2026 playoffs (R1, R2 only — see §4.3) |
| 2 | `SportsNot(TM) 2025 Fantasy Hockey` | `1ExXl0jmsYSNotlOUQBQmi-soUZzWPd3N45BC-aIZwU0` | 2025 playoffs |
| 3 | `SportsNot(TM) Fantasy Hockey` | `1-LBNUxnuSgPLm7BUvYw2FFD2yYkP7BjxdsVNhbd5jb8` | 2024 playoffs |

Snapshot date: 2026-08-25.

### How the data was pulled, and what is missing

The three sheets are **not** link-shared publicly. The documented
`export?format=csv|xlsx` endpoints, the `gviz/tq` endpoint and the `pub?output=csv`
endpoint all return the Google sign-in interstitial to an unauthenticated client, so
the intended "no auth needed" CSV/xlsx download path does not work.

They *are* shared with `kyle.bastien@pushpress.com`, so every tab was read through the
authenticated Google Sheets API instead (`spreadsheets.values.get`, full-width range
per tab, default `FORMATTED_VALUE` rendering — the same rendering a CSV export
produces).

Consequences to be aware of:

* **`sheet<N>.xlsx` is not present.** The xlsx export requires Drive's `files.export`
  endpoint, which the available authenticated client does not expose; the
  unauthenticated endpoint hits the sign-in wall. Everything the xlsx would have
  carried *as cell values* is in the CSVs. What is genuinely lost is the non-value
  layer: formulas, cell notes/comments, fill colours, strike-through and merge
  information. See `OPEN_QUESTIONS.md` Q1 for the two ways to close this.
* Because the source was the values API rather than a file export, the CSVs contain
  **rendered values, not formulas**. Cells that are formulas in the sheet appear as
  their result, including the literal `#N/A` at `sheet1__round-2.csv` I22.
* Each CSV is padded to the tab's **used** rectangle (widest populated row × last
  populated row) and uses `\n` line endings. A Google CSV export would pad to the same
  used range but use `\r\n`.

### Files

| File | Sheet / tab | Rows | Cols |
|---|---|---|---|
| `sheet1__round-1.csv` | 1 / `Round 1` | 49 | 9 |
| `sheet1__round-2.csv` | 1 / `Round 2` | 41 | 13 |
| `sheet1__round-3-4.csv` | 1 / `Round 3+4` | 49 | 13 |
| `sheet1__wins.csv` | 1 / `Wins` | 13 | 3 |
| `sheet2__round-1.csv` | 2 / `Round 1` | 49 | 15 |
| `sheet2__round-2.csv` | 2 / `Round 2` | 49 | 13 |
| `sheet2__round-3-4.csv` | 2 / `Round 3+4` | 49 | 13 |
| `sheet2__wins.csv` | 2 / `Wins` | 13 | 3 |
| `sheet3__round-1.csv` | 3 / `Round 1` | 41 | 8 |
| `sheet3__round-2.csv` | 3 / `Round 2` | 41 | 10 |
| `sheet3__round-3-round-4.csv` | 3 / `Round 3 + Round 4` | 41 | 10 |
| `sheet3__wins.csv` | 3 / `Wins` | 21 | 3 |

Every file is non-empty, and every row count above equals the row count of the tab's
used range as reported by the API. Row/column references in this document are 1-based
A1 notation **into the CSV**, which is identical to the source tab's A1 notation (no
rows or columns were dropped from the top or left).

---

## 2. The layout, in one picture

Every round tab in all three sheets is the **same shape**: four stacked per-manager
roster blocks in columns A–E (round 1) or A–G (rounds 2, 3+4), with free-floating
notes and statistics blocks scattered to the right.

It is *not* a draft board — managers are stacked vertically, not spread across
columns, and the grid says nothing about pick sequence.

```
      A          B                C                D          E              F         G
 1               Position         Player           Team       Points ...     (free)    (free)
 2    Ben        Forward 1        <player>         <team>     <pts>
 3    (blank)    Forward 2        <player>         <team>     <pts>
 ...             Forward 3..5, Defense 1..3, Goalie 1, [IR - F, IR - D]
 13   (blank)    Total                             <total>
 14   Judah      Forward 1        ...                                   <- next block starts
```

* **Row 1 is the only header row.** Column headers are `""`, `"Position "`,
  `"Player "`, `"Team"`, then the points columns (§5). Note the trailing spaces in
  `Position ` and `Player `.
* **Column A carries the manager name only on the block's first row**; every other
  row in the block is `""`. This is the sheet's stand-in for a visually-grouped cell —
  there are no actual merged cells in the roster area. A parser must forward-fill
  column A.
* **Block order in column A is always Ben, Judah, Kyle, Levi** — alphabetical, and
  *not* the draft order. Never infer pick order from block order.
* **Each block ends with a `Total` row** whose value sits in column E.
* **There are no footer rows.** The last populated row is the last block's `Total`.
* Block length: 12 rows (10 roster slots + IR-F + IR-D + Total) where IR slots exist,
  10 rows otherwise. So `4 × 12 + 1 = 49` rows, or `4 × 10 + 1 = 41`.

The right-hand side of each tab holds unrelated free-text blocks (`Notes`,
`Statistics`, `Scoring`, `Teams Scored`, `Draft Order:`/`Order`, `Last Updated`,
`Current Max`, `Current Winner`, `Round N Point Potential per Series`). **Their column
positions differ from tab to tab** and they are vertically offset to sit next to
whatever roster row they happened to be typed beside — the vertical position carries
no meaning. Per-tab cell maps are in §4. A parser should read columns A–E (round 1) or
A–G (rounds 2/3+4) and treat everything to the right as out-of-band annotation.

---

## 3. Roster slots and how picks are recorded

### Slot labels (column B), verbatim

| Label | Meaning | Present in |
|---|---|---|
| `Forward 1` … `Forward 5` | 5 forward picks | all round tabs |
| `Defense 1` … `Defense 3` | 3 defenseman picks | all round tabs |
| `Goalie 1` | goalie/team pick (§3.2) | all round tabs |
| `IR - F` | injured-reserve forward | sheet1 R1, sheet1 R3+4, sheet2 all 3 rounds |
| `IR - D` | injured-reserve defenseman | sheet1 R1, sheet1 R3+4, sheet2 all 3 rounds |
| `Total` | block subtotal / running total | sheet1 all, sheet2 all, sheet3 R1 |
| `Total across Rounds` | same thing, renamed | sheet3 R2, sheet3 R3+4 |

Sheet 3 has **no IR slots at all**, and `sheet1__round-2.csv` has none either while
sheet 1's other two tabs do (see `OPEN_QUESTIONS.md` Q4).

### 3.1 Draft order — recorded, but only as a list

There are **no pick numbers anywhere**. Draft order appears once per tab as a short
list of four manager names in a floating block:

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
order (left-to-right or top-to-bottom) is taken to be pick 1 through pick 4; nothing
in the sheet states this explicitly.

**Snake direction is not recorded and cannot be recovered from these sheets.** Within
a block, roster rows are in slot order (`Forward 1`, `Forward 2`, …), which is a
position label, not a pick index — so there is no way to tell whether a round reversed
the order, nor which slot was taken at which overall pick. Only the four-manager
sequence per round survives. See `OPEN_QUESTIONS.md` Q5.

`sheet2__round-1.csv` records no order at all; its right-hand area holds the
`Eliminated Teams:` block instead.

### 3.2 Goalie / team picks — three different conventions

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
often-present goalie personal name in sheet 3. A parser must resolve the `Goalie 1`
row against a team vocabulary, not a player vocabulary, and must strip the `(...)`
suffix and the word `Goalie` in sheet 3.

### 3.3 Player name format

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

### 3.4 Team column

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
enough to matter — see `OPEN_QUESTIONS.md` Q7.

---

## 4. Tab-by-tab

### 4.1 Sheet 3 — `SportsNot(TM) Fantasy Hockey` = **2024** playoffs

**How the season was determined.** The playoff field pins it exactly. `Round 1`
rosters draw on Avalanche, Bruins, Canucks, Capitals, Islanders, Knights, Kings,
Lightning, Leafs, Jets, Oilers, Panthers, Predators, Rangers, Stars and Hurricanes —
the 2024 first-round field. `Round 2` narrows to Avalanche, Bruins, Canucks, Panthers,
Hurricanes, Rangers, Oilers, Stars: the eight 2024 second-round teams.
`Round 3 + Round 4` narrows to Panthers, Oilers, Rangers, Stars — the 2024 conference
finalists — and the 2024 Stanley Cup was Panthers over Oilers. Goalie picks name
Bobrovsky (Panthers), Shesterkin (Rangers), Demko (Canucks), Oettinger (Stars),
Skinner (Oilers) and Kochetkov (Hurricanes), all correct for 2024. The `Wins` tab
records a 2024 champion and leaves 2025 blank, so the workbook was live during 2024.
Its title carries no year because it was the league's only sheet at the time.

#### `sheet3__round-1.csv` — round 1 draft + round-1 scoring

41 rows × 8 cols. Header row 1: `""`, `Position `, `Player `, `Team`, `Points`, `""`,
`""`, `Notes`. Blocks of 10 rows (no IR): Ben rows 2–11, Judah 12–21, Kyle 22–31,
Levi 32–41, each ending in a `Total` row with the value in column E.

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
Levi, Ben, Kyle, Judah; `G15` `Last Updated` / `G16` `5/5`; `G18` `Current Max` / `G19`
`53`; `G21` `Current Winner` / `G22` `Kyle `; `H27` `Statistics`; `H31` `Scoring` with
`H32:H33` the scoring rules; `H36` `Teams Scored` (no values beneath); `H39` `Round 1
Point Potential per Series` / `H40` `23.5`.

**Irregularity:** `F24`/`G24` hold a stray second header pair `Points when drafted` /
`Current Points`, and `F25`/`G25` hold `5` / `8` for the Zach Hyman row — a
single-row abandoned experiment with the columns that rounds 2 and 3+4 later adopted
properly. Only one player has these values.

#### `sheet3__round-2.csv` — round 2 draft + cumulative scoring

41 rows × 10 cols. Header row 1 gains the three-column points scheme (§5): `Points for
Round`, `Points when drafted`, `Current Total Points` in E, F, G. Blocks: Ben 2–11,
Judah 12–21, Kyle 22–31, Levi 32–41; 10 rows each, with `Total across Rounds` in B.

```
A1:J1     ,Position ,Player ,Team,Points for Round,Points when drafted,Current Total Points,,,Notes
A2:G2     Ben,Forward 1,Nathan MacKinnon,Avalanche,5,9,14
A10:G10   ,Goalie 1,Panthers Goalie (Sergei Bobrovsky),Panthers,8,0,8
A11:E11   ,Total across Rounds,,,66
A32:G32   Levi ,Forward 1,Connor McDavid,Oilers,9,12,21
```

Annotations: `J1` `Notes`, `J2` scoring reminder; `I9` `Order` / `I10:I13` = Ben, Levi,
Judah, Kyle; `I15` `Last Updated` / `I16` `5/21`; `I18` `Current Max` / `I19` `108`;
`I21` `Current Winner` / `I22` `Levi `; `J27` `Statistics`; `J31` `Scoring` / `J32:J33`
rules; `J36` `Teams Scored`; `J39` `Round 2 Point Potential per Series` / `J40`
`47.75`.

#### `sheet3__round-3-round-4.csv` — rounds 3 **and** 4 combined

41 rows × 10 cols, same layout as round 2. This tab covers the conference finals and
the Stanley Cup Final as **one** drafted round: one roster per manager, one set of
points. The two NHL rounds are not separable in the data. Note the label drift — the
tab is named `Round 3 + Round 4` but the statistics block at `J39` says `Round 3 Point
Potential per Series`.

```
A1:J1     ,Position ,Player ,Team,Points for Round,Points when drafted,Current Total Points,,,Notes
A2:G2     Ben,Forward 1,Sam Reinhart,Panthers,7,9,16
A7:H7     ,Defense 1,Dmitry Kulikov,Panthers,5,0,2,(+3 because of Jacob Trouba for Round 3)
A33:G33   Levi ,Forward 1,McDavid,Oilers,7,24,31
A39:G39   ,Defense 1,Makar,Oilers,12,20,32
A41:E41   ,Total across Rounds,,,172
```

**Mid-round substitution.** `H7` reads `(+3 because of Jacob Trouba for Round 3)` on
Ben's `Defense 1` row. The slot is *recorded* as Dmitry Kulikov, but the points reflect
a different player for part of the span, and the row's own arithmetic does not close
(5 for the round + 0 when drafted, yet 2 as the current total). This is the only
explicit substitution note in any sheet. See `OPEN_QUESTIONS.md` Q6.

Annotations: `J1`/`J2` notes; `I9` `Order` / `I10:I13` = Ben, Kyle, Judah, Levi; `I15`
`Last Updated` / `I16` `5/31`; `I18` `Current Max` / `I19` `172`; `I21` `Current
Winner` / `I22` `Levi `; `J27` `Statistics`; `J31` `Scoring` / `J32:J33`; `J36` `Teams
Scored`; `J39` potential / `J40` `113`.

#### `sheet3__wins.csv` — league champions by year

21 rows × 3 cols, and the one tab that is **not** in the standard shape.

**Rows 1–9 are entirely empty.** The header row that sheets 1 and 2 carry (`Year`,
`Gemmell Cup Winner`, `NHL Stanley Cup Winner`) is absent here; data starts cold at
row 10. Columns are positional: A = year, B = league champion, C = NHL Stanley Cup
winner.

```
A10:C10  2014,,Kings
A14:C14  2018,Ben,Capitals
A15:C15  2019,Levi,St. Louis Blues
A20:C20  2024,Levi,Panthers
A21:C21  2025
```

2014–2017 have an NHL champion but no league champion — the league's own records start
in 2018. Row 21 is a bare `2025` placeholder written before the 2025 playoffs; `A21`
is the last populated cell, so this tab's used range ends mid-row.

`Lighting` at C16 and C17 is a misspelling of Lightning. The trophy is the
"Gemmell Cup".

### 4.2 Sheet 2 — `SportsNot(TM) 2025 Fantasy Hockey` = **2025** playoffs

**How the season was determined.** The title says 2025 and the data agrees exactly.
`sheet2__round-1.csv` H5:O5 lists the eight first-round losers — Blues, Avalanche,
Wild, Kings, Senators, Lightning, Canadiens, Devils — which is precisely the 2025 set,
and the 16 teams appearing across round-1 rosters are the 2025 field. `Round 2` narrows
to Oilers, Hurricanes, Jets, Panthers, Capitals, Leafs, Stars, Knights (the 2025 second
round) and `Round 3+4` to Oilers, Panthers, Hurricanes, Stars (the 2025 conference
finalists); the 2025 Cup was Panthers over Oilers. `Last Updated` values 5/4, 5/12 and
5/25 track the 2025 calendar.

#### `sheet2__round-1.csv`

49 rows × 15 cols — the widest tab, because of the `Eliminated Teams:` block. 12-row
blocks (IR-F and IR-D present): Ben 2–13, Judah 14–25, Kyle 26–37, Levi 38–49.

```
A1:I1     ,Position ,Player ,Team,Points,,,Notes,Statistics
A2:E2     Ben,Forward 1,Nikita Kucherov,Lightning,4
A12:E12   ,IR - D,Haydn Fleury,Jets,0
A13:E13   ,Total,,,52
A45:H45   ,Defense 3,Luke Hughes,Devils,0,Not playing,,Round 1 Point Potential per Series
A48:F48   ,IR - D,Jake Sanderson,Senators,3,Activated
```

Annotations: `H1` `Notes` / `I1` `Statistics`; `H2` goalie-scoring reminder; `H4`
`Eliminated Teams:` with `H5:O5` = Blues, Avalanche, Wild, Kings, Senators, Lightning,
Canadiens, Devils; `G17` `Last Updated` / `G18` `5/4`; `G20` `Current Max` / `G21`
`59`; `G25` `Current Winner` / `G26` `Kyle `; `H31` a second `Statistics`; `H37`
`Scoring` / `H38:H39` rules; `H42` `Teams Scored`; `H45` `Round 1 Point Potential per
Series` / `H46` `54.25`.

**Per-row status flags live in column F on round-1 tabs** (F and G are unused by the
roster block there): `F45` `Not playing`, `F48` `Activated`.

#### `sheet2__round-2.csv`

49 rows × 13 cols, 12-row blocks: Ben 2–13, Judah 14–25, Kyle 26–37, Levi 38–49.
Three-column points scheme in E/F/G.

```
A1:K1     ,Position ,Player ,Team,Points for Round,Points when drafted,Current Total Points,,,Notes,Statistics
A2:G2     Ben,Forward 1,Connor McDavid,Oilers,6,11,17
A4:H4     ,Forward 3,Mark Scheifele,Jets,5,6,11,Dropped
A11:H11   ,IR - F,Connor McMichael,Capitals,1,5,6,Activated
A13:E13   ,Total,,,88
```

Annotations: `J1` `Notes` / `K1` `Statistics`; `J2` reminder; `J5` `Draft Order:` /
`J6:M6` = Judah, Ben, Levi, Kyle; `I17` `Last Updated` / `I18` `5/12`; `I20` `Current
Max` / `I21` `100`; `I25` `Current Winner` / `I26` `Kyle `; `J31` `Statistics`; `J37`
`Scoring` / `J38:J39`; `J42` `Teams Scored`; `J45` `Round 2 Point Potential per
Series` / `J46` `37.75`.

**Per-row status flags live in column H on round-2 and round-3+4 tabs** (E/F/G are
taken by points): `H4` `Dropped`, `H11` `Activated`, `H44` `Dropped`, `H48`
`Activated`.

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

Annotations: `J2`/`K2` labels; `J3` reminder; `J6` `Draft Order:` / `J7:M7` = Judah,
Ben, Levi, Kyle; `I18` `Last Updated` / `I19` `5/25`; `I21` `Current Max` / `I22`
`163`; `I26` `Current Winner` / `I27` `Levi`; `J32` `Statistics`; `J38` `Scoring` /
`J39:J40`; `J43` `Teams Scored`; `J46` `Round 3+4 Point Potential per Series` / `J47`
`59.25`.

As in sheet 3, rounds 3 and 4 are one combined drafted round.

#### `sheet2__wins.csv`

13 rows × 3 cols. Proper header at row 1 (`Year`, `Gemmell Cup Winner`, `NHL Stanley
Cup Winner`), then 2014–2025 one row each.

```
A1:C1    Year,Gemmell Cup Winner,NHL Stanley Cup Winner
A6:C6    2018,Ben,Capitals
A7:C7    2019,Evi,St. Louis Blues
A13:C13  2025,Evi,Panthers
```

This is the same table as `sheet3__wins.csv` with a header added, the 2025 result
filled in, and **every `Levi` replaced by `Evi`** — see §6.

### 4.3 Sheet 1 — `SportsNot(TM) 2026 Fantasy Hockey` = **2026** playoffs, partly

**How the season was determined.** Round 1's rosters include Porter Martone
(`sheet1__round-1.csv` C6), whose first NHL season is 2025-26, plus Logan Stankoven on
Carolina and Darren Raddysh on Tampa Bay (`sheet1__round-2.csv` C3,
`sheet1__round-1.csv` C9), both post-2025 team situations. Anaheim and Buffalo appear
as playoff teams, which they were not in 2024 or 2025. Together with the title, that
places `Round 1` and `Round 2` in the **2026** playoffs.

`Round 3+4` and `Wins`, however, are **not 2026 data** — see below.

#### `sheet1__round-1.csv` — 2026 round 1, drafted but never scored

49 rows × 9 cols, 12-row blocks (IR present): Ben 2–13, Judah 14–25, Kyle 26–37,
Levi 38–49. Same layout as sheet 2's round 1.

**The entire `Points` column (E) is empty**, all four `Total` rows are empty, and the
statistics block reads `0`. Rosters were drafted; nothing was ever scored here.

```
A1:I1     ,Position ,Player ,Team,Points,,,Notes,Statistics
A2:H2     Ben,Forward 1,Kirill Kaprizov,Minnesota,,,,Goalie points - 2 ponts per win + 2 for shutout
A6:I6     ,Forward 5,Porter Martone,Philly,,,,,Kyle
A10:D10   ,Goalie 1,Carolina Hurricanes,Carolina
A13:B13   ,Total
A24:C24   ,IR - D,","
```

Annotations: `H1` `Notes` / `I1` `Statistics`; `H2` reminder; **`I6:I9` = Kyle, Ben,
Evi, Judah** — the draft order, with *no label above it* (it sits directly under the
`Statistics` header at `I1`); `G17` `Last Updated`, `G20` `Current Max`, `G25` `Current
Winner` — all three labels present with **empty value cells beneath**; `H31`
`Statistics`; `H37` `Scoring` / `H38:H39` rules; `H42` `Teams Scored`; `H45` `Round 1
Point Potential per Series` / `H46` `0`.

**Irregularity:** `C24` (Judah's `IR - D` player cell) contains a lone comma `,`. A
stray keystroke, not a player. It is CSV-quoted as `","` in the file.

**Irregularity:** this is the only tab whose draft-order list uses the name `Evi`
alongside four roster blocks labelled Ben / Judah / Kyle / Levi — the direct evidence
that `Evi` and `Levi` are the same manager (§6).

#### `sheet1__round-2.csv` — 2026 round 2, drafted but never scored

41 rows × 13 cols. **10-row blocks — no `IR - F` / `IR - D` rows**, unlike sheet 1's
other two tabs: Ben 2–11, Judah 12–21, Kyle 22–31, Levi 32–41.

All three points columns (E, F, G) are empty, every `Total` is empty, `Current Max` is
`0`, and `Current Winner` renders as `#N/A` (a broken formula, `I22`).

```
A1:K1     ,Position ,Player ,Team,Points for Round,Points when drafted,Current Total Points,,,Notes,Statistics
A2:J2     Ben,Forward 1,Jack Eichel,Vegas,,,,,,Goalie points - 2 ponts per win + 2 for shutout
A4:H4     ,Forward 3,Alex Tuch,Buffalo,,,,Dropped
A14:D14   ,Forward 3,Cole Caufield,Monteral
A22:I22   Kyle ,Forward 1,Matt Boldy,Minnesota,,,,,#N/A
```

Annotations: `J1` `Notes` / `K1` `Statistics`; `J2` reminder; `J5` `Draft Order:` /
`J6:M6` = Judah, Ben, Levi, Kyle; `I15` `Last Updated` / `I16` `5/12` — **a 2025 date
left over from the copied workbook, since nothing here was scored**; `I18` `Current
Max` / `I19` `0`; `I21` `Current Winner` / `I22` `#N/A`; `J27` `Statistics`; `J31`
`Scoring` / `J32:J33`; `J36` `Teams Scored`; `J39` `Round 2 Point Potential per
Series` / `J40` `0`. Status flags in column H: `H4` and `H38` both `Dropped`.

#### `sheet1__round-3-4.csv` — **stale 2025 data, not 2026**

49 rows × 13 cols. This tab is a **cell-for-cell copy of `sheet2__round-3-4.csv`** in
every roster cell. Diffing the two files gives exactly six differing cells, all of them
formula results:

| Cell | sheet1 | sheet2 | What it is |
|---|---|---|---|
| `E13` | `72` | `160` | Ben's `Total` |
| `E25` | `53` | `135` | Judah's `Total` |
| `E37` | `48` | `148` | Kyle's `Total` |
| `E49` | `66` | `163` | Levi's `Total` |
| `I22` | `72` | `163` | `Current Max` |
| `I27` | `Ben` | `Levi` | `Current Winner` |

Every player, team, `Points for Round`, `Points when drafted` and `Current Total
Points` value is identical — including the 2025 conference finalists (Oilers, Panthers,
Hurricanes, Stars) and the `5/25` `Last Updated`. The 2026 workbook was created by
duplicating the 2025 one; `Round 1` and `Round 2` were cleared and re-drafted for 2026,
and **`Round 3+4` was never cleared**.

The `Total` difference is fully explained: on these tabs `Total` is *cumulative* across
rounds (§5), computed as the previous round's total plus this round's contribution.
Sheet 2's round-2 totals were 88 / 82 / 100 / 97, and adding sheet 1's figures
reproduces sheet 2's exactly (72+88=160, 53+82=135, 48+100=148, 66+97=163). In sheet 1
the round-2 totals are blank, so the formula returns only the round-3+4 contribution.
`Current Winner` flips to `Ben` purely as a consequence.

**This tab must be excluded from any 2026 training data, and deduplicated against
`sheet2__round-3-4.csv` rather than treated as a second observation.**

#### `sheet1__wins.csv`

13 rows × 3 cols. **Identical to `sheet2__wins.csv`** — same header, same 2014–2025
rows, same `Evi` spelling. No 2026 row. Also a leftover of the duplication; it carries
no information beyond sheet 2's copy.

---

## 5. Points and scoring columns

### Column meanings

| Column | Round 1 tabs | Rounds 2 / 3+4 tabs |
|---|---|---|
| E | `Points` — points scored by that player during round 1 | `Points for Round` — points scored during this round only |
| F | *(free; used for status flags)* | `Points when drafted` — the player's playoff points to date at the moment of this round's draft |
| G | *(free; used for the Last Updated / Current Max / Current Winner labels)* | `Current Total Points` = E + F |

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

and in the `Notes` block: `Goalie points - 2 ponts per win + 2 for shutout` (`ponts`
is a typo present in all nine round tabs).

### The `Total` rule, reverse-engineered

Round 1: `Total` = sum of the nine starting slots' points, **plus** any `IR` row
flagged `Activated`, **excluding** unflagged IR rows. Verified on all four
`sheet2__round-1.csv` blocks — e.g. Ben 4+9+8+6+2+4+4+5+10 = 52 = `E13`, with the IR
rows (3, 0) excluded; Levi's nine starters sum to 56 but `E49` is 59, the extra 3 being
`Jake Sanderson` at `E48`, flagged `Activated` at `F48`.

Rounds 2 and 3+4: `Total` is **cumulative** = previous round's `Total` + this round's
contribution, where the contribution is the sum of `Points for Round` over the starting
slots, minus any slot flagged `Dropped`, plus any IR slot flagged `Activated`. Verified
on all four `sheet2__round-2.csv` blocks — e.g. Ben: round-1 total 52, starters sum 40,
less `Mark Scheifele`'s 5 (`Dropped`, `H4`), plus `Connor McMichael`'s 1 (`Activated`,
`H11`) = 52+36 = 88 = `E13`. Sheet 3 states this outright by renaming the row `Total
across Rounds`.

The same reconstruction does **not** close on the round-3+4 tabs: the round-3+4
contributions implied by the totals are 72 / 53 / 48 / 66, but summing `Points for
Round` over the nine starters gives 69 / 54 / 48 / 66 — Ben is 3 high and Judah 1 low,
with no `Dropped` or `Activated` flag on either block to account for it. See
`OPEN_QUESTIONS.md` Q8.

### The `Statistics` block

| Label | Meaning |
|---|---|
| `Last Updated` | date the sheet was last scored, `M/D` with no year |
| `Current Max` | the highest `Total` across the four managers (matches the leader's total in every scored tab) |
| `Current Winner` | the manager holding that maximum; a formula, and `#N/A` when the data is empty |
| `Round N Point Potential per Series` | a computed number (`23.5`, `54.25`, `37.75`, `59.25`, `113`, `0`); derivation not recoverable from values alone — see `OPEN_QUESTIONS.md` Q9 |
| `Teams Scored` | a label with **no values beneath it in any tab** |
| `Eliminated Teams:` | `sheet2__round-1.csv` only, `H5:O5` — the eight first-round losers |

---

## 6. Managers

Four managers, stable across all three seasons. Column A always lists them
alphabetically (Ben, Judah, Kyle, Levi), which is not the draft order.

### Canonical ids

| Canonical id | Sheet 1 (2026) | Sheet 2 (2025) | Sheet 3 (2024) |
|---|---|---|---|
| `ben` | `Ben` | `Ben` | `Ben` |
| `judah` | `Judah ` | `Judah ` | `Judah ` |
| `kyle` | `Kyle ` | `Kyle ` | `Kyle ` |
| `levi` | `Levi` (round tabs), `Evi` (`Wins` and the round-1 draft-order list) | `Levi` (round tabs), `Evi` (`Wins`) | `Levi ` / `Levi` |

Surface forms to fold into `levi`: `Levi`, `Levi ` (trailing space), `Evi`. For the
others: `Ben`, `Judah `, `Judah`, `Kyle `, `Kyle`. **Trailing whitespace is present in
the raw data and must be stripped when matching** — it appears both in column A block
labels and in `Current Winner` values (`Kyle `, `Levi `).

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
`OPEN_QUESTIONS.md` Q2 only because it is an inference, not a statement in the data.

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

## 7. What the CSVs cannot carry

* **Formulas.** `Total`, `Current Max`, `Current Winner` and the point-potential
  figures are formulas in the sheet; only their rendered results are here. This is why
  `sheet1__round-2.csv` `I22` reads `#N/A` and why the stale `sheet1__round-3-4.csv`
  totals differ from sheet 2's.
* **Cell notes and comments.** Not retrievable through the values API. If picks, trades
  or substitutions were annotated as comments rather than as cell text, that is not in
  these files. `OPEN_QUESTIONS.md` Q3.
* **Colour coding, strike-through and merges.** The league's app has eliminated-player
  strike-through, so the sheets plausibly used fill colours or strike-through to mark
  eliminated teams and dropped players. Only the explicit text flags (`Dropped`,
  `Activated`, `Not playing`) survive here. `OPEN_QUESTIONS.md` Q3.
* **Pick numbers and snake direction.** Never recorded in the first place (§3.1).
* **Anything about 2026 rounds 3 and 4**, and any 2026 scoring at all (§4.3).

## 8. Summary of usable draft observations

| Season | Round | File | Rosters | Scored |
|---|---|---|---|---|
| 2024 | 1 | `sheet3__round-1.csv` | yes | yes |
| 2024 | 2 | `sheet3__round-2.csv` | yes | yes |
| 2024 | 3+4 | `sheet3__round-3-round-4.csv` | yes | yes |
| 2025 | 1 | `sheet2__round-1.csv` | yes | yes |
| 2025 | 2 | `sheet2__round-2.csv` | yes | yes |
| 2025 | 3+4 | `sheet2__round-3-4.csv` | yes | yes |
| 2026 | 1 | `sheet1__round-1.csv` | yes | **no** |
| 2026 | 2 | `sheet1__round-2.csv` | yes | **no** |
| 2026 | 3+4 | — | **absent** (`sheet1__round-3-4.csv` is a 2025 duplicate) | — |

Six fully scored manager-rounds × 4 managers = 24 scored roster observations, plus 8
unscored 2026 roster observations.
