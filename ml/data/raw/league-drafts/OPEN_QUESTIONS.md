# Open questions for the league

Things I could not settle from the data alone. Cell references are into the CSVs in this
directory (identical to the source tabs' A1 notation); see `SCHEMA.md` for the layout.

The xlsx exports closed most of the earlier list — formulas, fill colours,
strike-through and date serials answered them outright. What survives is below, ordered
by how much the answer changes the pipeline. A short record of what got resolved is at
the end.

---

### Q1 — Is the draft a snake, and does reading order = pick 1→4?

The `Order` / `Draft Order:` lists (per-tab table in `SCHEMA.md` §3.2) are the only
pick-sequence information anywhere in the three workbooks. There are no pick numbers, and
nothing states the direction.

* Is the first name in the list the **first** pick of that round?
* Sheet 3 writes the list down a column (`G10:G13`, `I10:I13`); sheets 1 and 2 write it
  across a row (`J6:M6`, `J7:M7`) — except `sheet1__round-1.csv`, which writes it down a
  column at `I6:I9`. Same meaning in all three orientations?
* **Is it a snake?** i.e. after manager 4 takes their `Forward 1`, does manager 4 also
  pick first for `Forward 2`? If it snakes, I can reconstruct every overall pick number
  from the order list plus the slot labels. If it's a straight repeating order, same
  thing but simpler. If it's neither — if you drafted freely and filled slots in
  whatever order — then the slot labels carry no pick information and I should not model
  pick position at all.

This is the single biggest open item: it decides whether draft position is a usable
feature.

---

### Q2 — The Kulikov / Trouba slot: who held it in which round?

`sheet3__round-3-round-4.csv` row 7, with the formula from the xlsx:

```
,Defense 1,Dmitry Kulikov,Panthers,5,0,2,(+3 because of Jacob Trouba for Round 3)
E7 = =3 + (G7 - F7)
```

So the arithmetic is settled — 2 points for Kulikov plus a hardcoded 3 for Trouba = the
5 shown. What isn't settled is the roster fact:

* Did **Trouba** hold Ben's `Defense 1` slot for round 3 and Kulikov for round 4, or the
  other way round?
* Was Trouba a mid-round replacement (Kulikov's team advanced, Trouba's didn't?), or a
  scoring correction after the fact?
* Any other in-round substitutions in 2024 or 2025 that were *not* noted? The two
  unflagged swaps I found in `sheet2__round-3-4.csv` (see the resolved list, R5) say
  undocumented changes do happen, so I'd rather not assume this is the only one.

---

### Q3 — `Makar` on `Oilers` — which half is wrong?

`sheet3__round-3-round-4.csv` row 39:

```
,Defense 1,Makar,Oilers,12,20,32
```

Cale Makar played for Colorado, and Colorado was out before the 2024 conference finals,
so a Makar pick in a Panthers/Oilers/Rangers/Stars round shouldn't exist. Two extra
clues from the xlsx: the row is **not** yellow-highlighted, and yellow marks
round-3 eliminations — so the sheet genuinely believed this was a surviving Oilers
player. The same block's `Forward 1` is also bare-surnamed (`McDavid`, Oilers), which is
correct.

* Is row 39 a different Oilers defenseman mis-typed as `Makar` (Bouchard? Nurse?)?
* Or is `Oilers` the typo and this is a stale Makar row carried over from an earlier
  round?

32 points is the largest single line in Levi's winning 2024 block, so this row matters
for any "what wins" analysis.

---

### Q4 — Should I recompute `Point Potential per Series`, or drop it?

The formula is `(sum of all four blocks' starters) / N`, i.e. league points that round
divided by a series count. Sheet 3 uses the correct count per round (`/8`, `/4`, `/2`);
**sheets 1 and 2 hardcode `/4` everywhere**, so the 2025 round-1 figure (54.25) and
round-3+4 figure (59.25) are not comparable with sheet 3's.

* Was the divisor meant to be the series count, i.e. are sheets 1 and 2 simply buggy?
* Is this column something you actually used, or scratch work? If it was a real
  decision input, I'd like to model it correctly; if not I'll drop it.

Related: `Teams Scored` appears as a label in **every** round tab with nothing underneath
it in any of them. Was that block ever used?

---

### Q5 — What exactly does `Dropped` mean, and where's the replacement?

`Dropped` marks a player the `Total` formula excludes: `sheet2__round-2.csv` `H4` (Mark
Scheifele) and `H44` (Josh Morrissey); `sheet1__round-2.csv` `H4` (Alex Tuch) and `H38`
(Rasmus Dahlin).

* Does `Dropped` mean the player forfeited their points entirely, or that they were
  **replaced** and the replacement's points counted somewhere? In the 2025 cases the
  formula pulls in an `Activated` IR player in the same edit, which looks like a
  swap — is that the rule?
* If replaced, where is the replacement recorded? The slot still shows the dropped
  player's name.
* Same question for `Activated` on IR rows (`sheet2__round-1.csv` `F48`,
  `sheet2__round-2.csv` `H11` / `H48`): does activating mean the player replaced a
  starter, or just started counting?
* And `Not playing` (`sheet2__round-1.csv` `F45`, Luke Hughes, 0 points) — a scratch, or
  a pick who turned out ineligible?

---

### Q6 — Was 2026 played, and is there a 2026 round 3+4 anywhere?

`sheet1__round-1.csv` and `sheet1__round-2.csv` hold complete 2026 rosters with **every
points cell empty**. The xlsx makes it starker than the CSV did: the `Total` cells hold
no formula at all (the sums were deleted, not just starved), there is **no 2026 date
anywhere in the workbook**, and the only two dates present — `2025-05-12` and
`2025-05-25` — are leftovers copied from the 2025 sheet.

* Did you play 2026 and score it **in the app** instead of the sheet? If so that's where
  the real 2026 data is and I should pull from there.
* Or did 2026 get drafted and then abandoned?
* Either way: who won 2026, and was there a round 3+4 draft at all?

Right now 2026 contributes 8 unscored roster observations and no outcomes.

---

### Q7 — Confirm `Evi` is `Levi` (low risk, just want it on the record)

I've merged both to `levi`. Three things support it: `sheet3__wins.csv` credits `Levi`
for the same five years `sheet2__wins.csv` credits `Evi`; `sheet1__round-1.csv` `I6:I9`
lists the order as Kyle / Ben / **Evi** / Judah in a workbook whose blocks are Ben /
Judah / Kyle / **Levi**; and the pale-green block fill `FFD9EAD3` is Levi's in all three
workbooks.

Just confirm there isn't a fifth member named Evi that I've folded away.

---

### Q8 — Minor: two stray cells, safe to ignore?

* `sheet1__round-1.csv` `C24` — Judah's `IR - D` player cell contains a lone comma
  (`","` in the CSV). Stray keystroke, or shorthand?
* `sheet3__round-1.csv` `F24`/`G24` hold a second header pair `Points when drafted` /
  `Current Points`, with values `5` / `8` at `F25`/`G25` for the Zach Hyman row only —
  and a live `E25 = =G25-F25` behind it, so those 3 points *are* in Kyle's 2024 round-1
  total. Real data for that one player, or a prototype I should treat as noise?

---

### Q9 — Why are 2014–2017 league champions blank?

The `Wins` tabs record an NHL champion for 2014–2017 but no `Gemmell Cup Winner`. Did the
league start in 2018, or are those results lost? (Decides whether "no champion" is
missing data or out-of-scope.)

---

## Answers (from the SportsNot repo ruleset, the NHL record, and the sheets themselves)

Answered in a follow-up session with the app codebase in context. The league's rules are
codified in this repo (`plans/sportsnot-plan.md` §Core Gameplay,
`packages/utils/src/lib/utils.ts`, `packages/types/src/lib/types.ts`) — the sheets are
hand-kept records of the same league the app was built for, so the app's ruleset is
authoritative where the sheets are ambiguous. Items still needing Kyle's word are marked
**[confirm]**.

### A1 — Yes, it is a snake; first name in the list = first pick. But do NOT reconstruct pick numbers from slot labels.

The app codifies this league's rules: snake draft each round
(`generateSnakeDraftOrder`), re-draft between rounds ordered **worst → best** by
standings (`generateReDraftOrder`, sorts points ascending). The sheets confirm it
empirically: `sheet2__round-2.csv` order is Judah, Ben, Levi, Kyle — exactly ascending
round-1 standings (Kyle/Levi tied 59; Kyle, listed later/better, is the recorded
round-1 winner via the tie-breaking array formula). So: first listed = first pick,
direction reverses each pass, and all three orientations (row vs. column) mean the same
thing. Round-1-of-a-season order is randomized (app rule), which fits the 2026 list
(Kyle/Ben/Evi/Judah) matching no standings.

**However:** the slot labels (`Forward 1`…`Forward 5`, `Defense 1`…) are ROSTER slots,
not pick sequence. In a snake, a manager fills whichever slot they like on each turn, so
"order list + slot labels" does NOT recover overall pick numbers unless managers happened
to fill slots in label order — the app records `pick_number` separately for exactly this
reason. **Parser guidance:** emit `snake_slot` (from the order list) and `position`, but
leave `pick_number` NULL for sheet-era drafts; the opponent model (US-020) should be fit
on round-level order + positional need, not exact pick indices. **[confirm]** only if
Kyle says rows were in fact written in pick order — then pick numbers become recoverable.

### A2 — Trouba held Ben's Defense 1 for Round 3; Kulikov for Round 4.

2024 bracket: Trouba's Rangers made the conference final (round 3) and were eliminated
by Kulikov's Panthers, who advanced to the final (round 4). So within the combined
R3+4 tab, Ben's Defense 1 was Jacob Trouba for round 3 (+3, hardcoded in `E7`), replaced
after the Rangers' elimination by Dmitry Kulikov for round 4 (`G7-F7` = 2). This is a
**mid-tab replacement after a round-3 elimination**, possible because 2024 drafted
rounds 3 and 4 together (one draft covering both rounds — note for the parser: sheet-era
seasons have THREE draft events, R1 / R2 / R3+4, not four). **[confirm]** whether the
R3+4 replacement-after-elimination was a standing league rule (everyone could swap) or a
one-off, and whether other unflagged swaps exist beyond the two found in
`sheet2__round-3-4.csv` (R5).

### A3 — The `Makar / Oilers` row is Evan Bouchard; `Oilers` is correct, the name is wrong.

Evan Bouchard (Oilers D) scored **32 points in the 2024 playoffs** — matching `Current
Total Points` = 32 exactly — with ~20 through two rounds, matching `Points when
drafted` = 20. Cale Makar's Avalanche were eliminated in round 2 with Makar at 15
points, so the 20/32 pair is impossible for him. The un-highlighted row (= surviving
team) fits the Oilers, who reached the final. The league demonstrably knows Bouchard
(drafted by name in `sheet1__round-1.csv`, 2026). **Parser guidance:** add a
name-override mapping `sheet3__round-3-round-4.csv` row 39 → Evan Bouchard (NHL id for
Bouchard, team Oilers).

### A4 — Drop the column; recompute anything needed from raw points.

`Point Potential per Series` is scratch analytics, not part of the ruleset (the app has
no such concept). Sheet 3 divides by the true series count (8/4/2); sheets 1–2 hardcode
`/4` — a copy-template bug, since both workbooks were cloned from a 4-series layout. The
pipeline derives per-series normalizations itself from raw data, so: **do not ingest
this column**. `Teams Scored` is populated nowhere in any workbook — ignore it.

### A5 — `Dropped`/`Activated` is the league's IR retroactive point swap; `Not playing` is the same event where the starter scored 0.

This is the app's codified IR rule (plan §Core Gameplay: "Retroactive point swap when
replacing injured players (same position only)"). Reading: an injured **starter** is
marked `Dropped` and forfeits their round points entirely (excluded from `Total`); the
same-position **IR** player is marked `Activated` and their full round points count
retroactively instead. The replacement is recorded on the IR row itself — the starter
slot keeps the dropped player's name by convention. Every observed instance pairs
same-position within one block: Scheifele (F, Dropped) ↔ McMichael (IR-F, Activated);
Morrissey (D, Dropped) ↔ Pietrangelo (IR-D, Activated); and Luke Hughes (D, `Not
playing`, 0 — he had season-ending shoulder surgery in April 2025 and never dressed) ↔
Jake Sanderson (IR-D, Activated) in the same block. So `Not playing` = the
dropped-starter side of a swap where there were no points to forfeit. The two unflagged
formula-only swaps (R5) are the same mechanic applied without writing the labels.
**Parser guidance:** treat `Dropped`/`Not playing` starters as points-excluded and pair
each with the same-position `Activated` IR row in the same block.

### A6 — 2026 was played and scored in the SportsNot app; the sheets were abandoned mid-season.

That is what this repository is: the league's app, whose v1 shipped for the 2026
playoffs (see `tasks/prd-v1-bugfixes-and-dark-mode.md` and the mock/OTP/round-progression
PRDs from the 2026 run-up). The 2026 rosters in sheet 1 with deleted `Total` formulas
are drafts recorded before scoring moved into the app; the struck-through-then-deleted
IR rows match the app's per-league `allowIrSlots` toggle (IR disabled for 2026). The
authoritative 2026 data (including any round 3+4 and the champion) lives in the app's
Supabase `draft_picks`/`rosters` tables. **[confirm]**: who won 2026, whether rounds 3–4
were drafted in-app, and whether Kyle wants a one-off CSV export of the app's 2026
drafts added here (the ML pipeline deliberately does not read Supabase).

### A7 — `Evi` = `Levi`: treat as confirmed.

Same win years (2019–22, 24, 25) credited to `Evi` in sheets 1–2 and `Levi` in sheet 3;
same block fill `FFD9EAD3` in all three workbooks; the 2026 order list names Evi in a
workbook whose blocks include Levi. Canonical manager id: `levi`, alias `evi`.
**[confirm]** only as a formality.

### A8 — Stray comma: ignore. Hyman 5/8: real data, honor it.

`sheet1__round-1.csv` `C24` lone comma = stray keystroke in an otherwise-empty 2026 IR
cell (IR was being retired that season); ignore. The Hyman `Points when drafted` 5 /
`Current Points` 8 pair with live `E25 = G25 - F25` is real: it is a per-player
instance, inside a round-1 tab, of the drafted/current pattern the later tabs formalize —
Hyman entered Kyle's roster mid-round with 5 points already banked and was credited 3.
**Parser guidance:** honor the mini-columns for that one row (credit 3, not 8).

### A9 — League records begin in 2018; 2014–2017 are NHL-champion backfill.

Every workbook's Wins tab lists NHL champions from 2014 but Gemmell Cup winners only
from 2018 (Ben). The natural reading: the league was founded in 2018 and earlier NHL
rows are context, not lost league seasons. Championship history for the record: 2018
Ben, 2019–2022 Levi, 2023 Kyle, 2024 Levi, 2025 Levi. Out of scope for draft modeling
either way (only 2024+ drafts exist). **[confirm]** as a formality.

---

### Still needing Kyle (summary)

1. **A1**: were sheet rows written in pick order? (If yes, pick numbers become
   recoverable; the pipeline currently assumes NOT.)
2. **A2**: was the R3+4 replace-after-elimination a standing rule, and are there other
   unflagged swaps?
3. **A6**: 2026 champion, whether R3–4 happened in-app, and whether to export the app's
   2026 draft data into this directory.
4. **A7 / A9**: one-word confirmations.

---

## Resolved by the xlsx exports

Kept for the record — these were open questions before link-sharing was enabled.

* **R1 — xlsx access.** Closed. All three `/export?format=xlsx` downloads now succeed
  anonymously, and the twelve per-tab CSV exports too. The committed CSVs turned out to
  be byte-identical to the genuine exports, so nothing had to be re-derived.
* **R2 — Colour coding.** Each manager has a stable block fill across all three
  workbooks (Ben `FFF4CCCC`, Judah `FFCFE2F3`, Kyle `FFFFF2CC`, Levi `FFD9EAD3`). In
  `sheet3__round-3-round-4.csv` a fifth colour, pure yellow `FFFF00`, marks columns B–D
  of 14 rows — every one a Rangers or Stars player, i.e. **eliminated after round 3**.
* **R3 — Cell comments.** There are none, in any of the three workbooks. No
  `comments*.xml` or `threadedComments*.xml` parts exist, so nothing was annotated that
  way.
* **R4 — Merged cells.** Column A *is* merged, one range per manager block (`A2:A13` …
  or `A2:A11` …). Those ranges are now the authoritative block boundaries.
* **R5 — The round-3+4 total mismatch.** Fully explained, and it uncovered a real data
  hazard. The formulas are hand-edited per block:
  `sheet2` R3+4 `E13 = sum(E2:E3) + sum(E5:E10) + E11 + 'Round 2'!E13` skips Ben's
  `Forward 3` (Sam Reinhart, 12) and swaps in his IR-F (Verhaeghe, 15), which is the +3;
  `E25 = sum(E14:E16) + sum(E18:E22) + E23 + 'Round 2'!E25` skips Judah's `Forward 4`
  (Hyman, 3) for his IR-F (Brown, 2), which is the −1. **Neither row carries a `Dropped`
  or `Activated` flag** — the substitution exists only in the formula. Kyle's and Levi's
  formulas are untouched, which is why they reconciled. Q2 and Q5 above ask whether
  more of these are lurking.
* **R6 — IR slot history.** Sheet 3 (2024) has no IR rows; sheet 2 (2025) uses them; in
  `sheet1__round-1.csv` (2026) **all eight IR rows are struck through**, and they're
  deleted outright in round 2. IR looks introduced for 2025 and retired during 2026.
* **R7 — `Current Winner`.** A real array formula,
  `{=INDIRECT(ADDRESS(1+MATCH(<max>, E11:E41, 0), 1))}`, not a typed name. It returns
  `#N/A` on empty data (hence `sheet1__round-2.csv` `I22`) and resolves ties to the
  first matching block — which is why `sheet2__round-1.csv` reports `Kyle ` when Kyle and
  Levi both finished on 59.
* **R8 — Season dating.** The `Last Updated` cells are date serials carrying the year:
  2024-05-05 / 05-21 / 05-31 for sheet 3, 2025-05-04 / 05-12 / 05-25 for sheet 2. That
  confirms the 2024 and 2025 assignments from the data itself rather than from roster
  inference, and shows sheet 1's two dates are 2025 leftovers.
* **R9 — `Points for Round` is derived.** Every per-player cell in column E on the
  rounds 2 / 3+4 tabs is `=G - F`. The maintained inputs are `Points when drafted` and
  `Current Total Points`; E is a display column.
