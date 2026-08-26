# Open questions for the league

Things I could not settle from the data alone. Each one changes how the parser or the
training set should be built, so I'd rather ask than guess. Cell references are into
the CSVs in this directory (identical to the source tabs' A1 notation); see `SCHEMA.md`
for the layout.

Ordered roughly by how much the answer matters.

---

### Q1 — Can you make the three sheets link-viewable, or export the xlsx yourself?

The sheets are not publicly link-shared: `export?format=csv`, `export?format=xlsx`,
`gviz/tq?tqx=out:csv` and `pub?output=csv` all return the Google sign-in page to an
unauthenticated client. I read every tab through the authenticated Sheets values API
instead, so **the CSVs here are complete as to cell values, but `sheet1.xlsx` /
`sheet2.xlsx` / `sheet3.xlsx` are missing** — and with them the formulas, cell notes,
fill colours, strike-through and merge info (see Q3).

Two ways to close it, whichever you prefer:

1. Set each sheet to "Anyone with the link → Viewer", tell me, and I'll pull the real
   xlsx exports and commit them.
2. Download all three via **File → Download → Microsoft Excel (.xlsx)** yourself and
   drop them in this directory as `sheet1.xlsx`, `sheet2.xlsx`, `sheet3.xlsx`.

Or say it doesn't matter and I'll note the CSVs as the sole source of record.

---

### Q2 — Is `Evi` the same person as `Levi`?

I've assumed yes and canonicalized both to `levi`. Evidence: `sheet3__wins.csv` credits
`Levi` for 2019/2020/2021/2022/2024 (`B15`, `B16`, `B17`, `B18`, `B20`) while
`sheet2__wins.csv` credits `Evi` for the same five years (`B7`–`B10`, `B12`); and
`sheet1__round-1.csv` `I6:I9` lists the draft order as Kyle, Ben, **Evi**, Judah in a
workbook whose four roster blocks are Ben, Judah, Kyle, **Levi**.

Confirm — is `Evi` a nickname/typo for Levi, or is there a fifth league member named
Evi who I've just merged away?

---

### Q3 — What did the colour-coding and any cell comments mean?

The values API can't see fills, strike-through or cell notes, so none of that is in
these CSVs. Given the app has eliminated-player strike-through, I assume the sheets
used something similar.

* Were eliminated teams / eliminated players marked by fill colour or strike-through
  rather than text? If so, which colour meant what?
* Are there cell comments (right-click → Comment) recording trades, substitutions or
  pick order anywhere? If yes, in which tabs?
* Are any of the roster cells actually merged, or is a blank column A simply left blank
  on continuation rows (which is what the values suggest)?

If any of this carries real information, I need the xlsx from Q1 to capture it.

---

### Q4 — Is a whole roster re-drafted every round, and is the IR slot drafted too?

The data reads as a **full re-draft each round**: the same player shows up in different
managers' blocks in consecutive rounds (e.g. Connor McDavid is Levi's `Forward 1` in
`sheet2__round-1.csv` A38 and Ben's `Forward 1` in `sheet2__round-2.csv` A2). Confirm
that's right — that each round is an independent draft over the surviving teams, not a
keeper/carry-over roster with waiver adds.

And on the IR slots specifically, the sheets are inconsistent:

* Sheet 3 (2024) has **no** `IR - F` / `IR - D` rows in any round.
* Sheet 2 (2025) has them in all three rounds.
* Sheet 1 (2026) has them in `Round 1` and in the stale `Round 3+4`, but **not** in
  `Round 2` (`sheet1__round-2.csv` blocks are 10 rows, not 12).

Was IR a rule introduced for 2025? And is the `sheet1__round-2.csv` omission a rule
change for 2026, or just rows someone forgot to add?

---

### Q5 — Is the `Order` / `Draft Order:` list a snake, and does reading order = pick 1→4?

The order lists (per-tab table in `SCHEMA.md` §3.1) are the only pick-sequence
information in the sheets. There are no pick numbers, and nothing states the direction.

* Is the first name in the list the **first** pick of that round?
* Sheet 3 writes the list down a column (`G10:G13`, `I10:I13`); sheets 1 and 2 write it
  across a row (`J6:M6`, `J7:M7`) — except `sheet1__round-1.csv`, which writes it down
  a column at `I6:I9` with no label. Same meaning in all three orientations?
* **Is the draft a snake?** i.e. within a round, after manager 4 picks their `Forward
  1`, does manager 4 also pick first for `Forward 2`? If it snakes, I can reconstruct
  every overall pick number from the order list plus the slot labels. If it's a
  straight repeating order, same thing but simpler. If it's neither — if you just
  drafted freely and filled slots in whatever order — then slot labels carry no pick
  information at all and I should not model pick position.

This one materially changes what the model can learn about draft position.

---

### Q6 — How should the Kulikov / Trouba substitution be recorded?

`sheet3__round-3-round-4.csv` row 7:

```
,Defense 1,Dmitry Kulikov,Panthers,5,0,2,(+3 because of Jacob Trouba for Round 3)
```

The slot names Kulikov, the note credits Jacob Trouba for round 3, and the row's own
arithmetic doesn't close (`E7`=5 for the round, `F7`=0 when drafted, but `G7`=2 rather
than 5).

* Who actually occupied Ben's `Defense 1` slot — Trouba for round 3 and Kulikov for
  round 4, or the reverse?
* Which of 5 / 0 / 2 is the trustworthy number, and what happened to the other?
* Was this a one-off correction, or did in-round substitutions happen elsewhere without
  a note? (This is the only note of its kind in any of the nine round tabs.)

---

### Q7 — `Makar` listed with team `Oilers` — which is wrong, the team or the player?

`sheet3__round-3-round-4.csv` row 39:

```
,Defense 1,Makar,Oilers,12,20,32
```

Cale Makar played for Colorado, and Colorado was eliminated before the 2024 conference
finals — so a Makar pick in a Panthers/Oilers/Rangers/Stars round shouldn't exist. The
same block's `Forward 1` (row 33) is also bare-surnamed (`McDavid`, Oilers), which is
correct for 2024.

* Is row 39 meant to be a different Oilers defenseman (Bouchard? Nurse?) mis-typed as
  `Makar`?
* Or is `Oilers` the typo and this is a leftover Makar row from an earlier round?

32 points is the biggest single line in Levi's winning block, so this row matters for
any "what wins" analysis.

---

### Q8 — Why don't the round-3+4 totals match the sum of their own rows?

The `Total` rule works everywhere else. Round 1: total = the nine starters, plus any
`Activated` IR. Rounds 2/3+4: total = previous round's total + this round's starters,
minus `Dropped`, plus `Activated` IR. That reproduces all four blocks in
`sheet2__round-1.csv` and all four in `sheet2__round-2.csv` exactly.

On `sheet2__round-3-4.csv` it doesn't. The implied round-3+4 contributions (from
`E13`, `E25`, `E37`, `E49` minus the round-2 totals) are **72 / 53 / 48 / 66** for
Ben / Judah / Kyle / Levi, but summing `Points for Round` over the nine starters gives
**69 / 54 / 48 / 66**. Kyle and Levi match; Ben is 3 high and Judah is 1 low, and
neither block has a `Dropped` or `Activated` flag to explain it.

Was there a manual adjustment, a hardcoded cell, or a formula reaching a row it
shouldn't? If you can open the sheet and tell me what's actually in `E13` and `E25`
(formula vs literal), that settles it. Otherwise: should I trust the `Total` row or the
per-player rows when they disagree?

---

### Q9 — What are `Round N Point Potential per Series` and `Teams Scored`?

`Point Potential per Series` appears once per round tab with these values: 23.5
(2024 R1), 47.75 (2024 R2), 113 (2024 R3+4), 54.25 (2025 R1), 37.75 (2025 R2), 59.25
(2025 R3+4), and 0 in both unscored 2026 tabs. It's a formula result and I can't
reverse it from values alone.

* What does it measure — expected points available per playoff series, given the
  rosters? Something else?
* Is it a useful target/feature, or scratch work?

Separately, `Teams Scored` appears as a label in **every** round tab with **nothing
underneath it in any of them**. Was that block ever used, or is it a leftover header?

---

### Q10 — Was the 2026 season actually played, and is there a 2026 round 3+4 somewhere?

`sheet1__round-1.csv` and `sheet1__round-2.csv` have complete 2026 rosters but **every
points cell is empty**, all four `Total` rows are blank, `Current Max` is 0, and
`Current Winner` is `#N/A` (`I22`). `sheet1__round-3-4.csv` is a byte-identical copy of
the 2025 round-3+4 tab that was never cleared, and `sheet1__wins.csv` has no 2026 row.

* Did you play 2026 and score it **in the app** instead of the sheet? If so, that's
  where the real 2026 data lives and I should pull from there, not from sheet 1.
* Or did 2026 get drafted and then abandoned?
* Either way: who won 2026, and is there a round 3+4 draft for 2026 at all?

Right now 2026 contributes 8 unscored roster observations and no outcomes.

---

### Q11 — What exactly does `Dropped` mean, and where's the replacement?

`Dropped` appears in column H on the round-2/3+4 tabs and marks a player whose points
the `Total` formula excludes (verified — see Q8's rule): `sheet2__round-2.csv` `H4`
(Mark Scheifele) and `H44` (Josh Morrissey); `sheet1__round-2.csv` `H4` (Alex Tuch) and
`H38` (Rasmus Dahlin).

* Does `Dropped` mean the player was dropped mid-round and forfeited their points
  entirely, or that they were dropped and **replaced**, with the replacement's points
  counted somewhere I'm not seeing?
* If replaced, where is the replacement recorded? The slot still shows the dropped
  player's name.
* Likewise `Activated` on IR rows (`sheet2__round-1.csv` `F48`, `sheet2__round-2.csv`
  `H11` / `H48`) — does activating an IR player mean they replaced a starter, or that
  they simply started counting?
* And `Not playing` (`sheet2__round-1.csv` `F45`, Luke Hughes, 0 points) — is that a
  scratch, or a pick of a player who turned out to be ineligible?

---

### Q12 — Is the unlabelled list at `sheet1__round-1.csv` I6:I9 really the draft order?

It sits directly under the `Statistics` header at `I1` with no label of its own, reads
Kyle / Ben / Evi / Judah, and is the only order list in the three sheets written that
way. Every other tab labels its list `Order` or `Draft Order:`.

Is it the 2026 round-1 draft order — or is it final standings, or something else that
happens to be four names?

---

### Q13 — Minor: two stray cells, safe to ignore?

* `sheet1__round-1.csv` `C24` — Judah's `IR - D` player cell contains a lone comma
  (`","` in the CSV). Stray keystroke, or shorthand for something?
* `sheet3__round-1.csv` `F24`/`G24` hold a second header pair `Points when drafted` /
  `Current Points`, with values `5` / `8` at `F25`/`G25` for the Zach Hyman row only.
  Abandoned experiment with the columns rounds 2+ later adopted — or real data for that
  one player that I should keep?

---

### Q14 — Why are 2014–2017 league champions blank?

`Wins` tabs record an NHL champion for 2014–2017 but no `Gemmell Cup Winner`. Did the
league start in 2018, or are those results just lost? (Affects whether I treat
"no champion" as missing data or as out-of-scope years.)
