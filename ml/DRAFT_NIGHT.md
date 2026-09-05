# Draft Night Guide — using the Draft Oracle CLI to pick

This is the operator's guide for the SportsNot playoff draft: what to run before the
season, what to run the day of each draft, and how to drive the interactive assistant
while you're on the clock. Everything at draft time is **offline** — the assistant reads
only a precomputed artifact directory, so a dead Wi-Fi connection at the bar cannot hurt
you once the artifact exists.

All commands run from `ml/`:

```
cd ml
```

---

## TL;DR — the five commands

```
uv run oracle injuries                                   # 1. refresh injury statuses (needs network)
uv run oracle project --season 2027 --round 1            # 2. build the round's artifact (a few minutes)
less artifacts/2027-r1/cheatsheet.md                     # 3. read the board; slot_strategies.md once you know your seat
uv run oracle draft --artifact artifacts/2027-r1 \
    --managers ben,judah,kyle,levi --slot 3 \
    --session gemmell-r1.json                            # 4. live assistant: `pick`, `recommend`, `board`
# 5. inside the session: type `recommend` whenever you're on the clock
```

Rounds 2, 3 and 4 repeat steps 1–4 with `--round 2` / `--round 3`. The league drafts
once for rounds 3+4 combined, and `--round 3` builds that combined artifact automatically
(the manifest records `draft_event: R3_4`; goalie-slot values include the Cup Final
weighted by each team's chance of getting there).

---

## Once per season: get the new season into the archive

The models train on the committed NHL archive under `data/raw/nhl-archive/`. `oracle
project` normalizes that archive; it does **not** download anything. So before the first
round of a new playoff year you need that season's three files plus its bracket:

```
team-games-2026-27.csv.gz   skater-games-2026-27.csv.gz   skater-bios-2026-27.csv.gz   bracket-2027.json
```

The fetch script is committed next to the data (`data/raw/nhl-archive/fetch_nhl.py`).
Its `SEASONS` list is hard-coded at the top of the file — extend the range by one year,
run it to a scratch directory, and copy only the new season's files into the archive:

```
# edit SEASONS in fetch_nhl.py:  range(2015, 2027)   # adds 20262027
python data/raw/nhl-archive/fetch_nhl.py /tmp/nhl-2027
cp /tmp/nhl-2027/*2026-27* /tmp/nhl-2027/bracket-2027.json data/raw/nhl-archive/
uv run oracle normalize --force
```

Read `data/raw/nhl-archive/PROVENANCE.md` first if the fetch misbehaves — it documents
the two NHL API traps the script is built around (a silent 10,000-row cap and per-month
partitioning). The bracket file is what tells the artifact which 16 teams are alive; the
NHL API publishes it the day the regular season ends, so fetch after that.

If you drafted last year and want the opponent model to learn from it, also refresh the
league history (`data/raw/league-drafts/`, see `SCHEMA.md` there) and run:

```
uv run oracle league-drafts && uv run oracle match-drafts && uv run oracle train-opponents
```

This is optional — the committed opponent model already knows how ben, judah, kyle and
levi draft.

---

## Day of the draft: build the artifact

### 1. Injuries (the one thing humans on their phones won't have)

```
uv run oracle injuries              # pulls ESPN's public injuries feed
uv run oracle injuries --no-fetch   # offline: last-known table + your overrides only
```

Skaters marked `out`, `ir` or `day_to_day` get the `injured` flag in the artifact; the
return-time model then discounts their projected games. If you know something ESPN
doesn't (a coach's "he's playing tonight"), add it to `data/overrides/injuries.yaml` —
the file header documents the format. Overrides are the final authority:

```yaml
overrides:
  - player: "Connor McDavid"
    player_id: 8478402
    status: healthy         # out | ir | day_to_day | healthy
  - player: "Cale Makar"
    player_id: 8480069
    status: day_to_day
    return_game: 3          # expected back for game 3 of the series; pins availability
```

Re-run `oracle injuries --no-fetch` after editing so the override lands in
`data/normalized/injuries.parquet` before you build the artifact.

### 2. Projections

```
uv run oracle project --season 2027 --round 1                    # Gemmell Cup (no IR)
uv run oracle project --season 2027 --round 1 --ir               # a league WITH IR slots
uv run oracle project --season 2027 --round 1 --slot-rollouts 40 # faster slot plans
uv run oracle project --season 2027 --round 1 --no-slot-strategies   # fastest
```

`--managers` defaults to 4. Use `--ir` for a league that drafts IR_F/IR_D (Press Play-offs
does; the Gemmell Cup doesn't) — it changes replacement levels and roster shape, so
build a separate artifact per league if they differ. The run retrains every model on
pre-round data only, then writes `artifacts/2027-r1/`:

| File | What it is |
| --- | --- |
| `cheatsheet.md` | The board: every skater and team sorted by value over replacement, with p10/p50/p90 |
| `slot_strategies.md` | A full draft plan for each snake seat 1..N, with contingency picks for your first two turns |
| `skaters.csv` / `teams.csv` | The same numbers as data (parquet twins alongside) |
| `run_manifest.json` | Seeds, commit, CLI flags — proof of what produced the board |

Expect a few minutes with slot strategies on, well under a minute without. Build it
**before** the snake order is revealed; the slot plans exist precisely because you get no
time once your seat drops.

### 3. Read the cheat sheet

```
less artifacts/2027-r1/cheatsheet.md
```

Columns worth understanding:

- **Proj** — expected fantasy points this round (goals + assists for skaters; wins×2 with
  shutouts worth 4 for the team/goalie slot). **p10/p50/p90** — the downside, median and
  upside of that projection.
- **Repl** — the replacement level for the position: what the best *undrafted* player at
  that position will roughly score. **VOR** = Proj − Repl. This is the number the board
  is sorted by, and it's why a 5.2-point defenseman can rank above a 5.9-point forward.
- **Status** — an injury flag if the player is doubtful.
- The **G rows are entire teams**, not goalies. `COL 8.17` means "owning Colorado's
  goaltending this round is worth 8.17 expected points".

Once the snake order is announced, open `slot_strategies.md` and jump to `## Slot N` for
your seat: it lists your expected pick numbers, the recommended pick at each turn, the
top-3 alternatives, and — for your first two turns — what to take if your primary target
is gone.

---

## Live: the interactive assistant

### Start it

```
uv run oracle draft --artifact artifacts/2027-r1 \
    --managers ben,judah,kyle,levi \
    --slot 3 \
    --session gemmell-r1.json
```

- `--managers` — list the **real manager ids in snake order** (seat 1 first). The names
  must match the league history exactly (lowercase: `ben`, `judah`, `kyle`, `levi`) so
  the fitted opponent model attaches each manager's own drafting tendencies. Passing a
  bare number (`--managers 4`) still works but the assistant will tell you it's running
  on league-average behaviour with no per-manager affinity — you lose the "judah always
  reaches for Oilers" signal.
- `--slot` — your seat (1-based) in that order.
- `--ir` — add it for the IR league, matching the artifact you built.
- `--session` — where the pick log autosaves after every pick. **Give each league its own
  file name.** The assistant refuses to start on top of an existing log; use `--resume
  gemmell-r1.json` to continue one.
- `--eliminated CAR,NJD` — only needed if a team was eliminated *after* the artifact was
  built (mid-round knowledge). Between rounds, rebuild the artifact instead; the bracket
  handles elimination. Unknown abbreviations are rejected loudly, so a typo can't
  silently leave a team on the board.
- `--rollouts 100` — trade a little precision for speed if the room is impatient
  (default 500).

### The commands

| Command | What it does |
| --- | --- |
| `pick 1 McDavid` / `pick judah Bouchard` | Record a pick. The first token is a seat number or manager id; the name is fuzzy-matched (`pick 2 COL` for a goalie slot). Rejected with the reason if it's not that manager's turn, the player is gone, the position is full, or the team is eliminated. |
| `recommend` | **Your top-5 picks right now**, with a full multi-step lookahead. Under 10 seconds. |
| `recommend --depth 1` | The fast path (under 5 s) — one turn of lookahead. Nearly always the same #1. |
| `board` | Remaining players by position, best projection first. |
| `roster` / `roster judah` | A roster so far. |
| `undo` | Take back the last pick (someone mis-announced). |
| `save other.json` / `resume other.json` | Write or reload a session; `resume` switches the autosave target to the resumed file and leaves the current log alone. |
| `quit` | Exit. The log is already saved. |

### Reading `recommend`

```
[#3 kyle] > recommend
recommendation (fitted opponents)
- On the clock: kyle (pick #3)
- Replacement level (points): F 4.75 / D 3.67 / G 6.89

| Rank | Pos | Player          | Team | E[roster] | Proj | VOR   | P(survive) | Need |
| 1    | F   | Leon Draisaitl  | EDM  | 52.95     | 7.14 | +2.39 | 0.00       | 5/5  |
| 2    | D   | Evan Bouchard   | EDM  | 51.71     | 5.18 | +1.51 | 0.00       | 3/3  |
| 3    | D   | Darren Raddysh  | TBL  | 51.33     | 4.65 | +0.98 | 1.00       | 3/3  |
| 4    | F   | Kirill Kaprizov | MIN  | 51.33     | 5.52 | +0.77 | 1.00       | 5/5  |
| 5    | G   | COL             | COL  | 51.33     | 8.17 | +1.28 | 1.00       | 1/1  |
```

- **E[roster]** is the number that ranks the table: the expected total points of your
  *finished* roster if you take this player now and draft sensibly afterwards, with the
  other managers simulated drafting the way they historically do. It already accounts for
  what taking this player costs you later. **Take rank 1 unless you have information the
  model doesn't.**
- **Proj / VOR** — this player's own value, as on the cheat sheet.
- **P(survive)** — the chance this player is still available at your *next* turn.
  `0.00` means take him now or lose him; `1.00` means you can safely wait a round and
  address something else first. The gap between rank 1 and a `1.00` alternative is the
  price of waiting.
- **Need** — open slots at that position on your roster (`5/5` = you've drafted no
  forwards yet). The assistant will never recommend a position you've filled, and it will
  force the goalie slot before you run out of picks.

The header line tells you which opponent model is running. `fitted opponents` means every
seat has a real manager's history attached. `fitted opponents: league-average, no
per-manager affinity` means the names didn't match (check spelling and lowercase) — the
recommendation is still sound, just blind to individual tendencies.

### A typical turn

```
[#1 ben]   > pick 1 McDavid          # record what ben announced
[#2 judah] > pick 2 MacKinnon
[#3 kyle]  > recommend               # you're up
[#3 kyle]  > pick 3 Draisaitl        # record your own pick too
[#4 levi]  > pick 4 COL              # goalie slots are team abbreviations
```

Record **every** pick, including your own, or the board and the rollouts drift from
reality. If two people talk over each other and a wrong name lands, `undo` and re-enter.

### Drafting in two leagues on the same night

Run two terminals, two artifacts if the IR setting differs, two `--session` files:

```
uv run oracle draft --artifact artifacts/2027-r1     --managers ben,judah,kyle,levi --slot 3 --session gemmell-r1.json
uv run oracle draft --artifact artifacts/2027-r1-ir  --managers connor.fehr,kyle,tobi,paul.markhauser --slot 2 --ir --session press-r1.json
```

(Build the IR artifact with `--artifacts-root` or rename the directory; the default
output path is `artifacts/<season>-r<round>/`.)

---

## One-shot alternative: `oracle recommend`

If you only want the opening pick — say, to sanity-check the slot plan before the draft —
there's a stateless command that answers "best first pick from seat N":

```
uv run oracle recommend --artifact-dir artifacts/2027-r1 --managers ben,judah,kyle,levi --seat 3
```

It cannot be told about picks already made, so once the draft starts use the interactive
assistant.

---

## Troubleshooting

| You see | It means |
| --- | --- |
| `session log already exists at …` | Start with `--resume <that file>` to continue it, or pick a new `--session` name. The tool never overwrites a pick log. |
| `--managers contains duplicate id(s)` | A copy-paste typo listed one manager twice. |
| `unknown team abbrev(s): MON` | Montreal is `MTL`. Real NHL abbreviations only; a team not in this round's bracket is also reported here. |
| `not kyle's turn` / `already drafted` / `position full` | The rules engine is enforcing the league rules; record the picks in the order they actually happened. |
| `fitted opponents: league-average, no per-manager affinity` | Manager names didn't match the league history. Lowercase, exact ids. |
| The artifact is from last round | Eliminated teams' players are still on the board. Rebuild with `oracle project --round N`; use `--eliminated` only as a stopgap. |

Nothing in `oracle draft` or `oracle recommend` touches the network or trains a model.
Both work with the machine-learning libraries entirely absent.

---

## Honest expectations

The committed evidence (`artifacts/backtests/*/report.md`, `CODE_REVIEW_R4.md`) says:
replaying the last three seasons, the oracle's average seat would have won the league
twice and finished second twice; it beat the *average* manager in 10 of 12 rounds and
lost to the *best* manager in 5 of 12. Treat it as a strong, consistent second opinion,
not an oracle in the literal sense — particularly on the **goalie/team slot**, which is
the model's weakest component and the round's biggest single lever (Carolina's goaltending
was 40 of the winning 74 points in the 2026 final). If your own read on a goaltending
matchup disagrees with the board, that's the one place your judgment has the most room to
add value. On skaters, trust the VOR order.
