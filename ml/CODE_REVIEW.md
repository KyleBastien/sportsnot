# Draft Oracle — Code & Data Review

**Date:** 2026-08-29 · **Branch:** `ralph/ml-draft-optimizer` @ `fcf8a59` · **Scope:** all 29 commits (26 Ralph stories + combined-R3+R4 feature + committed 2026 artifacts)

**Method.** Multi-agent review (81 agents): eight specialized reviewers (rules fidelity, temporal leakage, ML methodology, optimizer, ingestion-vs-provenance, computational artifact validation, test quality, SPEC compliance) plus a completeness critic, followed by two independent adversarial verifiers per finding, each instructed to refute. Every finding below was **independently reproduced by verifiers running the actual code and data**; zero findings were refuted or left disputed. Quality gates were run directly: **566/567 pytest pass, `ruff` clean, `mypy --strict` clean** (the one failure is finding M-20).

---

## Verdict

This is a genuinely strong implementation with one crucial saving grace and three broken seams.

**The core that picks players is sound.** The rules engine is byte-faithful to the TypeScript reference (down to Node's stable-sort tie semantics, verified against actual Node output, plus a 20k-case fuzz). The best-of-7 series math reproduces hand calculations exactly (p=0.5 lengths 0.125/0.25/0.3125/0.3125, E[games]=5.8125; 2-2-1-1-1 venue pattern; shutout-replaces-win throughout). The optimizer enforces the full ruleset, genuinely rolls out to draft end, and its retroactive IR-swap math matches hand-computed scenarios. Temporal leakage discipline on the paths that matter is real: per-round rebuilds, strictly pre-cutoff retraining, leave-one-season-out opponent fits, and **betting odds never touch a pick**. The committed 2026 artifacts pass every computational check (quantile ordering, decomposition identities, bracket-alive membership, r4 containing exactly CAR/VGK), and the combined R3+R4 valuation is numerically correct to <1e-4. Honesty rules are visibly practiced — reports print their own misses.

**What's broken clusters in three places:**
1. **The market/odds evaluation layer is corrupted** (C-1, C-2, M-2, M-4, M-5): the Kaggle archive's placeholder prices were ingested as real, its column semantics were misread, and a UTC/local date mismatch silently drops ~2/3 of even the good prices. Because picks run stat-only, **no draft recommendation is affected** — but every committed market-related evaluation number (market ablation, market-aware Brier track, 2024-25 "market") is wrong and must be regenerated after fixes.
2. **Three integration seams ship disconnected** (M-9, M-10, M-11): the draft-time CLI never uses the fitted opponent model it was built for; snapshot pinning silently loses league picks/odds/injuries; and the injuries feed stores ESPN athlete ids that no consumer can join — making the injured flag and IR-stash valuation permanent no-ops against the real feed.
3. **The 2026 opponent-model artifact double-counts** the duplicated Gemmell sheet+app rows and pools two different leagues into one choice set (M-3).

Recommended posture: fix the P0 list below, regenerate the odds table, model reports, opponent artifact, and backtest report, and re-commit. The projection/optimizer core does not need rework.

---

## Critical findings

### C-1 · Kaggle odds parsed under false column semantics — garbage market probabilities for most seasons
`ml/src/draft_oracle/ingest/odds.py:688`

The parser assumes (per PROVENANCE §8) that the Kaggle `spread` sign on the home row identifies the favorite. The committed data contradicts this: `spread` is game-level and identical on **both** rows in 29,415/29,417 two-row games, so `favorite_side` degenerates to `home` for 100% of games in 2004–2019 and 2025. PROVENANCE §9 itself states §8's assumption is wrong. Combined with C-2, whole seasons come out as `home favorite, implied = 0.4901` constants.
**Impact:** corrupts `odds.parquet`, the game-win market feature and its ablation, and the backtest's market-Brier track. Not pick-affecting (picks are stat-only).
**Fix:** identify the favorite from a source that actually encodes it (the raw ESPN summaries' `homeTeamOdds.favorite`, present in the committed 2025-26 raw payloads), or treat Kaggle rows as unattributed prices; regenerate all downstream market artifacts.

### C-2 · Kaggle placeholder prices (constant −105) ingested as genuine coverage — the entire 2024-25 "market" is fabricated
`ml/src/draft_oracle/ingest/odds.py:731`

`favorite_moneyline` is a constant −105 for **every** row of seasons 2004–2018 and 2025 (2,920/2,920 rows), 98.7% of 2019, and 80.7% of 2026-through-Dec — i.e. puck-line juice, not a win price. The parser publishes these as `covered=True` real prices. The evidence to catch it was already recorded: per-row `xval_delta` vs real SBR prices averages 0.07 on overlap seasons and is checked nowhere; a season with `nunique(price)==1` is a trivially detectable placeholder.
**Impact:** violates the "flagged, never imputed" contract in effect; fabricates the 2024-25 market track in committed reports.
**Fix:** add a variance/placeholder guard per season-source (e.g. reject a season whose price column is near-constant), mark those rows uncovered, and actually consume `xval_delta` as a cross-source sanity gate.

---

## Major findings

### M-1 · A genuinely pre-round projection artifact cannot be built
`ml/src/draft_oracle/projection_artifact.py:664` — The round-N as-of cutoff is derived from round-N's **own first played game**, and per-series snapshots freeze at each matchup's first played game. The league drafts *before* the round starts, so at real decision time `oracle project` fails (loudly — it fails closed, which is the right direction) or skips every series. Backtests are unaffected (rounds complete). **Fix:** derive the cutoff from the previous round's completion (or bracket announcement) and freeze snapshots at that boundary, so the tool works at the moment it exists to serve. *(The committed 2026 artifacts were necessarily built retroactively; their manifests honestly record `as_of_cutoff`.)*

### M-2 · Market join on exact `game_date` drops ~2/3 of covered odds (UTC vs local)
`ml/src/draft_oracle/models/game_win.py:271` + `ingest/odds.py:647` — Kaggle/ESPN rows carry UTC calendar dates (a 7pm ET game is stamped the next day — documented in PROVENANCE §9); the NHL archive uses local dates; `consolidate_odds` knows this (±1-day cross-source tolerance) but writes UTC dates through, and `_attach_market` joins with no tolerance. Measured: only ~32–34% of covered 2025/2026 odds attach — matching the game-win manifest's own 31.6% "coverage" despite ~100% underlying fill. **Fix:** normalize odds dates to the NHL local-date convention at consolidation (the ±1-day matcher already exists), then regenerate.

### M-3 · Opponent model double-counts 2026 Gemmell and pools two leagues into one draft
`ml/src/draft_oracle/optimize/opponents.py:265` — `league_draft_picks` intentionally carries the 2026 Gemmell R1/R2 twice (sheet + app copies of the same draft; 32/32 identical player ids) plus the separate Press Play-offs league. `_build_choices` groups by `(season, draft_event, position)` only — no `league_name`, no `source` dedupe — so 2026 is modeled as fictitious 7-manager pseudo-drafts with double-weighted Gemmell picks and cross-league asset pools. The committed opponent manifest proves it: ben shows 105 picks vs the true 87 (105 = 87 + 18 duplicated rows). *(Found independently by two reviewers.)* **Fix:** dedupe on `(league_name, draft_event)` preferring `source='app'`, and fit within league; regenerate the opponent artifact and its validation numbers.

### M-4 · Fixed April-1 playoff windows mislabel 705 regular-season games as playoffs
`ml/src/draft_oracle/ingest/odds.py:326` — The 2020/2021 exceptions are handled, but every other season's window opens Apr 1 while regular seasons run into mid/late April (2021-22 to May 1): 232 mislabels in 2022 alone. Consequences: the pre-playoff market feature silently drops each team's most recent weeks of odds, and the backtest's series-market lookup can pick up April regular-season meetings between eventual playoff opponents. **Fix:** label `is_playoff` by joining to the archive's `gameTypeId` (already available) instead of date windows.

### M-5 · The backtest's "market-aware" Brier track uses mid-series closing lines
`ml/src/draft_oracle/backtest/replay.py:648` — Track 2 averages de-vigged lines from games played *during* the evaluated series, so it is not an as-of-round-start market benchmark (labeling says post-hoc calibration-only, which mitigates, but the number cannot be read as "what the market said before the series"). **Fix:** restrict to the series' game-1 line, or clearly relabel.

### M-6 · Committed backtest report grades the combined R3_4 event on round-3 production only (stale vs HEAD)
`ml/artifacts/backtests/2023-2024-2025-seed20260827/report.md` — The report was generated at `3bf1537`, before `fcf8a59` rewrote replay to draft R3_4 once and score across both rounds. Its league-comparison line "oracle 43.5 vs league 35.0" scores round 3 only; independently recomputed, the league's real R3_4 rosters earned means of 58.75 (2024) and 59.25 (2025) across both rounds. **Fix:** regenerate the backtest report at HEAD (after M-7's scorer fix) — the currently committed comparison doesn't measure the event the league plays.

### M-7 · Backtest league scorer violates the retroactive IR swap rule
`ml/src/draft_oracle/backtest/replay.py:920` — `_score_league_roster` unconditionally skips IR rows and counts the excluded starter: executed with a real swap scenario it returns 13.0 where league rules give 10. The parser correctly flags `points_excluded`/`ir_activated`, but nothing outside the parser consumes those columns; 2025 (the IR season, 5 documented activations) is mis-scored in every league comparison. No test covers this path. **Fix:** honor the flags in `_score_league_roster` (swap in the activated IR player's points), add the missing test.

### M-8 · No test exercises rounds 2–4 or the combined R3_4 event end-to-end
`ml/tests/test_backtest.py` — Instrumenting the full suite: all 22 `build_projection_artifact` calls and all 9 `replay_round` calls use `playoff_round=1`. The combined-event folding, `scored_rounds=[3,4]` summation, round-2/3 cutoffs, and surviving-team eligibility narrowing never execute under test — precisely where M-6/M-7 lived. **Fix:** extend the synthetic archive fixture through a final and add an R3_4 end-to-end test.

### M-9 · The draft-time CLI never uses the fitted opponent model
`ml/src/draft_oracle/cli/draft.py:455` — `oracle draft` and `oracle recommend` hard-code `GreedyOpponentModel`; managers are hard-coded `seat1..seatN` so per-manager fitted models (keyed ben/judah/kyle/levi) could not even attach; `opponent_model_from_config` is called only from tests. The US-020 model that was fit, validated, and blended per FR-15 influences offline reports only — never a live recommendation, contradicting US-021/PRD US-010/US-012. **Fix:** add `--opponents fitted --managers ben,judah,levi,kyle` (or artifact autoload) to the draft CLI.

### M-10 · Snapshot pinning is a hollow contract
`ml/src/draft_oracle/projection_artifact.py:971` + `ingest/normalize.py:46` — Snapshots freeze only the 5 core tables, but pinned runs read `league_draft_picks.parquet`, odds, and injuries from the snapshot dir — files no snapshot contains. Under any pinned snapshot, fitted opponents silently fall back to greedy, the report's league-comparison section (a US-026 headline criterion) silently vanishes, and mutable live inputs still leak in — falsifying the code's own "(snapshot, seed) fully determines every score" claim. **Fix:** snapshot all consumed tables, or fail loudly when a pinned run needs an unsnapshotted input.

### M-11 · Injuries feed keys ESPN athlete ids; every consumer joins NHL ids — a permanent no-op
`ml/src/draft_oracle/ingest/injuries.py:220` — Team ids get an ESPN→NHL conversion; player ids don't. NHL ids live in [8.4M, 8.5M]; real ESPN athlete ids are ~4–5M — the id spaces are disjoint, so `injured` flags and IR-stash valuation can never match a real player from the live feed (tests pass because fixtures use archive-matching ids). Manual overrides are also keyed on `espn_id`. **Fix:** add an ESPN→NHL player-id mapping (name+team match through the existing `entity_match` machinery) at ingestion.

---

## Minor findings

| # | Location | Finding |
|---|----------|---------|
| m-1 | `models/projections.py:522` | Actual round points re-derived inline (`goals+assists`) instead of calling `rules.player_points` — drift hazard, currently harmless. |
| m-2 | `backtest/replay.py:291` | Leakage guard's date check is tautological; a demonstrated skater/team-table desync leaks round-N production past it. |
| m-3 | `models/series_sim.py:392` | Pre-series snapshots freeze per-series, not at the round cutoff — with overlapping rounds a feature can absorb games on/after the declared `as_of_cutoff`. |
| m-4 | `backtest/replay.py:1120` | Backtest injects the *current* injuries snapshot into historical rounds (pick-affecting only under `ir=True`). |
| m-5 | `ingest/odds.py:312` | `devig_favorite_only` inverts the favorite for prices in (−100, −109]: "favorite" probability comes out below 0.5. |
| m-6 | `models/skater_production.py:204` | 2020 bubble round-robin games misassigned to round 2 via team-pair collision — contaminates a few 2020 training labels and snapshots. |
| m-7 | `optimize/recommend.py:554` | Vectorized fast path scores greedy opponents by projection (`asset_value`), diverging from `GreedyOpponentModel`'s `rank_value`. |
| m-8 | `optimize/recommend.py:520` | Fast-path `expected_points` excludes the owner's already-drafted roster value; the object path includes it — the two paths' E[roster] mean different things. |
| m-9 | `optimize/recommend.py:547` | Vectorized kernel silently corrupts rollouts when a manager has no legal asset (argmax over all −inf → index 0) where the object path raises. |
| m-10 | `optimize/slot_strategies.py:494` | Report section labeled "fitted league model" actually runs the league-average model with the affinity feature zeroed for every seat. |
| m-11 | `optimize/simulator.py:211` | Eliminated-team filter keys on `team_id` only; a skater with unresolved `team_id=None` stays draftable after elimination. |
| m-12 | `ingest/odds.py:353` | Preseason filter is September-only; 23–54 early-October preseason games per season enter as covered regular-season odds. |
| m-13 | `ingest/nhl_api.py:389` | Live `skater_summary` reproduces the documented 10k-row silent-truncation trap: `total` never checked, no date partitioning. *(Flagged independently by two reviewers.)* |
| m-14 | `artifacts/2026-r3/run_manifest.json` | Manifest stamps a `git_sha` (3bf1537) that cannot reproduce the r3 combined-event artifact — dirty-tree generation with no dirty marker. |
| m-15 | `ml/run_2026_backtest.py` | Docstring contradicts its config (claims rollouts=1000/n_drafts=32; code sets 500/8); file also sits outside the SPEC directory contract and mypy coverage. *(Two reviewers.)* |
| m-16 | `ml/tests/` | SPEC's "no network in tests" is convention-only — no conftest socket/transport guard. |
| m-17 | `tests/test_normalize.py` | NHL-archive normalizers tested only on synthetic frames; no real-file smoke test (fixtures do match real headers). |
| m-18 | `ml/artifacts/2026-r*/` | 2026 artifacts force-added past `.gitignore` against the SPEC artifacts contract (self-declared temporary in `ad0cfd4` — fine if actually reverted). |
| m-19 | `cli/project.py:47` | The draft-time entry point imports the full training stack (LightGBM, scikit-learn, httpx) at startup — SPEC wants the CLI to run without it. |
| m-20 | `backtest/report.py` | `write_report` stamps a fresh wall-clock timestamp per call, so render→write round-trips differ — the 1 failing test in the suite, and a determinism-rule violation. Found by direct test run. |

## Observations (info)

- **Verified clean, worth recording:** core as-of discipline (per-round rebuilds, pre-cutoff retraining, LOSO opponent fits, odds never in picks); retroactive IR-swap math, VOR ranks, snake order, full-depth rollout, seed determinism; all four 2026 artifacts pass every structural/computational check; the combined R3+R4 valuation is correct to <1e-4 with only second-order approximations; the draft CLI works end-to-end offline against committed artifacts; pinned stack 100% respected; all 17 RNG constructions seeded.
- The **US-010 team/series feature matrix** (with its market and injuries joins) is built and tested but consumed by no model or pipeline — dead weight or future wiring, worth deciding which.
- The **shutout model shows no held-out skill over the base rate** (its report says so honestly) yet is the sole source of per-team shutout-upside differentiation in goalie valuation — consider shrinking it toward the base rate.
- `_row_seed` masks `player_id` to 16 bits, so distinct players can share a Monte-Carlo stream (correlation, not bias).
- Golden vectors are equivalent to but not "copied verbatim" from `utils.test.ts` as docstrings claim — provenance nit.
- Cross-source safeguards (`xval_delta`, `neutral_site`) are recorded but consumed nowhere — C-2 would have been caught by the first one.
- Test suite overall is genuinely strong: 567 tests, exact-enumeration checks on the series simulator, hypothesis properties on the right invariants, parsers validated against the real committed snapshots, all HTTP mocked.

---

## Priority fix list

**P0 — before trusting any market/evaluation number:**
1. C-2 placeholder guard + C-1 favorite semantics (or drop the Kaggle price column and keep SBR + ESPN-completion only — coverage 2016-22 + Dec 2025-Jun 2026 is still substantial).
2. M-2/M-4 date-convention normalization and gameTypeId-based playoff labels.
3. Regenerate: `odds.parquet`, game-win report/ablation, backtest report — with M-6 staleness and M-7's league scorer fixed and M-8's tests added.

**P1 — before the next real draft (April 2027):**
4. M-1 pre-round cutoff mechanism (the tool must run *before* a round starts).
5. M-9 wire fitted opponents into `oracle draft`/`recommend`; M-3 dedupe/split the 2026 leagues and refit.
6. M-11 ESPN→NHL player-id mapping so injuries and IR stash valuation work live.

**P2 — hygiene:**
7. M-10 snapshot completeness; M-5; the minors, roughly in table order; revert `ad0cfd4`'s force-added artifacts once analysis is done (per its own commit message).

---

*Review by Claude (multi-agent adversarially-verified pass; 81 agents, ~5.8M tokens). Every listed finding was independently reproduced against the code and committed data by two verifiers; findings the verifiers could not reproduce were discarded (there were none — the finder pass had a 100% confirmation rate).*
