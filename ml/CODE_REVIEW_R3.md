# Draft Oracle — Round-3 Code & Data Review

- **Date:** 2026-09-01
- **Scope:** the second fix round `3e0f231..38e1731` (11 commits, 51 files, +2805/−735)
  implementing US-201..US-211 against the round-2 findings in `ml/CODE_REVIEW_R2.md`,
  including the US-211 regeneration of all committed model/backtest evidence.
- **HEAD reviewed:** `38e1731` on `ralph/ml-draft-optimizer`.
- **Gates at HEAD:** 695 tests pass, `ruff` clean, `mypy --strict` clean, tree clean —
  *after* regenerating this container's local data (`oracle normalize --force`,
  `league-drafts`, `match-drafts`, `odds`). On a truly fresh clone the suite is
  **2 failed / 690 passed / 3 skipped** — see R3-m2, the only reason the gate line needs
  an asterisk.
- **Method:** 11 fix-verification agents (one per story, re-running each round-2 finding's
  original failure scenario), 3 fresh-regression finders (full source-diff sweep,
  independent validation + honesty audit of every regenerated artifact, test/gate
  integrity with independent mutation testing), a completeness critic focused on
  draft-night end-to-end readiness, and two adversarial verifiers per non-info finding.
  56 agents, zero refusals to converge: every finding below was independently confirmed;
  nothing rests on a single reviewer.

---

## Verdict

**This fix round is genuine, honest, and nearly closes the book.** All 23 round-2 finding
statuses re-verified by independent reproduction: **22 cleanly fixed** with guarding tests,
**1 partial** (R2-m10 — the honest opponent label landed in `oracle draft` but not
`oracle recommend`), 0 not fixed, 0 regressed.

The honesty audit came back clean everywhere it looked: configs and seeds byte-identical
across the evidence regeneration; every metric that moved moved *against* the tool and was
disclosed (game-win test Brier 0.2410→0.2427 after including shootout games; opponent
fitted-vs-greedy down from 3/3 seasons to 2/3; the 2026 market Brier now the honest game-1
number 0.2339 — which the model's 0.2224 *beats*, reversing the stale 0.2080 claim); the
corrected 2024 league table (levi 64.0, mean 55.25, best 65.0) recomputes exactly from raw
sheets + archive by two independent agents; all 10 model/backtest manifests carry clean git
provenance from `da5e568`, whose `ml/` source is byte-identical to HEAD, and all 8 model
artifacts reproduce at HEAD (6 byte-identical, 2 to float-ulp). A grep of every committed
artifact and doc finds **no condemned pre-fix number surviving** — no 0.2080, no pooled
72.0, no levi 78, no mid-series wording. The cold draft-night path is deterministic across
OS processes, works offline under an import block, and rejects illegal picks with reasons.

**What remains is one incomplete-scope major, one staleness major, and a tail of minors** —
the majors are both direct descendants of this round's own fixes (the shootout fix stopped
at one of three copies of the same pivot; the 2026-r* fixtures were not regenerated even
though this round changed their generating pipeline), and the notable minors are three
draft-night input-validation traps the critic found at the session boundary.

---

## Round-2 fix scorecard

| R2 finding | Story | Status | Independently reproduced evidence |
|---|---|---|---|
| R2-M1 league pooling | US-201 | **fixed** | kyle scores Press 50.0 / Gemmell 37.0 (never 72.0) on the real parquet; six per-league tables, 4 managers each; Tuch exclusion survives dedupe; regression test fails on the reverted grouping. |
| R2-M2 stale 2026 backtest | US-211 | **fixed** | Regenerated at HEAD; market track = game-1 semantics, Brier 0.2339 (recomputed independently to 4+ decimals over all 14 series), honestly worse than before and now *losing* to the model's 0.2224. |
| R2-M3 shootout drop | US-203 | **fixed** (in `game_win.py` — but see R3-M1) | `home_win` from the archive `win` column; all 11 seasons' pivot counts equal decided-game counts (952/1398 measured); SO game 2020020007 enters correctly; the 65 unattachable 2021 odds rows attach; honest Brier degradation 0.2410→0.2427, nothing tuned. |
| R2-M4 McDavid/Draisaitl | US-202 | **fixed** | Exactly one row corrected (override, confidence 1.0); raw sheets byte-identical; with the override removed, BOTH new validators (duplicate ownership, point-split cross-check) independently flag the wrong match; corrected table 64.0/55.25/65.0 reproduces. |
| R2-M5 + R2-m7 + R2-m16 mutants | US-204 | **fixed** | All three round-2 surviving mutants now killed by named numeric tests (101.0→63.0, 20.19→10.18, 37.0→16.0), re-verified by independent mutation runs with module provenance checked. |
| R2-m3 + R2-m4 opponents | US-205 | **fixed** | `_event_keys` revert now fails two tests (36-pool real-parquet assertion); team_id merge recovers exactly 78/77/82/76; refit artifact reproduces byte-identically; honest report shows fitted now losing 2026 membership to greedy (0.287 vs 0.292). |
| R2-m1/m2/m12/m14 ingest | US-206 | **fixed** | Opposite-favorite −165/−165 now flagged (home-side delta 0.1999 vs pre-fix 0.0082); NaN-spread ESPN games unattributed; cap guard raises with `total` absent; the PIT/DET reversed-orientation pair is excluded-and-counted (the new accounting even surfaced a second undocumented reversed row — the 2018 Winter Classic). |
| R2-m15 + R2-m11 parity | US-207 | **fixed** | Shared rank-then-key argmax + per-manager need_weight array; both round-2 divergence fixtures now match exactly; reverting the fix fails the new parity tests. |
| R2-m10 seatN label | US-207 | **partial** | `oracle draft` now emits an honest three-state label (all three verified live, tested). But standalone `oracle recommend` still prints plain "fitted opponents" under default seats with the affinity signal entirely zeroed — same degradation, other entry point, unlabeled and untested. Case-typos of real names ('Ben' vs 'ben') hit the same path. |
| R2-m9 + R2-m18 CLI | US-208 | **fixed** | `optimize/__init__` genuinely lazy (PEP 562); real `oracle draft`/`recommend` runs complete with lightgbm/sklearn/httpx import-blocked; upgraded subprocess test fails on pre-fix source; default autosave moved to `./draft-session.json`, no default invocation touches the fixtures. (Gitignore half left open — R3-m6.) |
| R2-m13 CSV checks | US-209 | **fixed** | csv==parquet parametrized over all 8 files at 1e-12; truncation, a single-digit edit, and a row swap are all caught. |
| R2-m17 + R2-m6 docs | US-210 | **fixed** | All four README sections verified against HEAD code; game-win report/manifest now state per-season coverage with 2024/2025 uncovered outright, test-guarded. (Two sentences made stale by this round's *own* sibling stories were missed — R3-m7.) |
| R2-m5 + R2-m8 provenance/regen | US-211 | **fixed** | All 10 manifests: git_sha `da5e568`, git_dirty=false, pinned seeds; skater-production reproduces at HEAD with the corrected train count (4837); the promised US-110 regen debt is paid. |

---

## New findings — major

### R3-M1 · The shootout fix stopped at `game_win.py`: `series_sim.py` and `shutout.py` still drop every SO game — train/serve feature skew in the production `p_series_win` path
`ml/src/draft_oracle/models/series_sim.py:330`, `ml/src/draft_oracle/models/shutout.py:291` — **confirmed** (two verifiers, measured)

Two byte-similar copies of the condemned pivot survive: `games.loc[home_goals != away_goals]`
in `series_sim._pivot_all_games` and `shutout._pivot_games` (winner still derived by goal
comparison at series_sim.py:491). `reconstruct_series_matchups` — the function the
production projection artifact and both backtests use to freeze pre-series team states —
therefore still excludes all 1,024 shootout games (7.1% of 14,508 decided games) from the
Elo/win_pct/points state the game-win model is *applied* to, while since US-203 the model
is *trained* on states that include them. The docstring's claim that the replay uses "the
exact same update rules as those models" is now false. Measured at the 2026 R1 freeze:
serve-vs-train Elo differs by up to +35.8 (VGK; PIT +19.4, EDM +17.1), win_pct by up to
5.1pp. `shutout.py` additionally drops 16 genuine 0-0 shootout wins — real shutouts —
from its training universe (bounded impact: the model is honestly no-skill anyway).
Fix: derive the winner from the `win` column in both remaining pivots (same one-line
pattern as US-203), then regenerate the dependent evidence.

### R3-M2 · The committed 2026-r1..r4 projection fixtures are stale: every generating input changed this round, and they were not regenerated
`ml/artifacts/2026-r1..r4/run_manifest.json` — **confirmed** (rebuilt at HEAD and diffed)

All four run manifests still carry git_sha `8000f5b` (the round-2 fix HEAD). The
projection pipeline trains game-win at build time (changed by US-203), scores from
`league_draft_picks` (changed by US-202's override), and fits opponents from the deduped
pick table (changed by US-205's team_id recovery) — so the fixtures embed the exact
shootout-dropping defect this round fixed and no longer reproduce at HEAD: rebuilding
2026-r1 moves `p_series_win` by up to 0.0135, `e_goalie_points` by up to 0.099, shifts
replacement levels, and **reorders the cheatsheet draft board** (committed rank 4 = G COL;
HEAD rank 4 = D Bouchard, COL drops to 5). The committed 2026-combined backtest *was*
regenerated at HEAD, so the two committed 2026 evidence sets currently disagree with each
other. SPEC §4's own rule ("regenerate only from a clean committed HEAD; manifests name
that commit") is satisfied in the letter but the fixtures now contradict the models beside
them. Fix: regenerate 2026-r1..r4 at a clean HEAD — but **after** R3-M1, or they'll need a
third pass. Note the interaction honestly: the regenerated fixtures' numbers *will* change
the committed cheatsheets.

---

## New findings — minor (all adversarially confirmed)

| # | Location | Finding |
|---|----------|---------|
| R3-m1 | `ingest/entity_match.py` | The duplicate-ownership validator covers skaters only (`position != 'G'` filter); two managers' goalie slots resolving to the same `team_id` — the same impossible-duplicate class — pass silently, and the point-split cross-check also skips G rows. Verified latent: 0 goalie-side duplicates in today's data. |
| R3-m2 | `tests/test_backtest.py:858,906` | The two key US-201/US-202 real-data regression tests read gitignored `data/normalized/*.parquet` with no existence guard: on a fresh clone the suite is 2 failed / 690 passed (verified in a clean worktree). Every sibling real-data test uses `pytest.skip`; these two should too — and the README's "Run tests" line documents no generation prerequisite (this container hit exactly this trap). |
| R3-m3 | `data/overrides/name_overrides.yaml` | The Draisaitl correction is a *global* bare-name override: any future row whose raw name is exactly "McDavid" — in any season, league, or event — silently resolves to Draisaitl at confidence 1.0. Verified safe today (exactly one such row in the corpus; app-era rows carry no point columns for the cross-check to catch a future mistake). A scoped override key (season/event/manager) would close it. |
| R3-m4 | `tests/test_committed_model_evidence.py:61` | The provenance guard accepts any well-formed 40-hex `git_sha` — not required to be an ancestor of HEAD or consistent across the artifact set. Today's tree (models at `da5e568`, fixtures at `8000f5b`, all tests green) is itself the demonstration: the R2-M2 staleness class is only partially detectable. Assert ancestry and one shared sha per evidence pass. |
| R3-m5 | `optimize/opponents.py:385` | Surviving mutant one level down from US-205's guard: hardcoding the grouping inside `_build_choices` (leaving `_event_keys` league-aware) re-merges the 2026 cross-league pools in the real fit — coefficients move (affinity 3.04→2.63) — yet all 695 tests pass, because the isolation tests call `_event_keys` themselves. Pin a coefficient or group through the call site. |
| R3-m6 | `ml/.gitignore` | The gitignore half of R2-m18 was left open: `!artifacts/2026-r*/**` still re-includes an explicitly placed `draft-session.json` inside the fixtures, and the new `./draft-session.json` default is ignored nowhere (a draft run from `ml/` leaves a committable stray). One ignore line each. |
| R3-m7 | `ml/README.md` | Two sentences made stale by this round's own stories: the entity-matching section still claims "both maps ship empty" (US-202's override now ships in `name_overrides.yaml`), and the draft-assistant section still documents the autosave default as `<artifact>/draft-session.json` (US-208 moved it to cwd). |
| R3-m8 | `cli/project.py:641` | The R2-m10 residue: standalone `oracle recommend` prints plain "fitted opponents" under default seats (affinity fully zeroed) — the fixed interactive path prints the honest three-state label for the identical state. Reuse the label. |
| R3-m9 | `cli/draft.py:664,805` | Launching `oracle draft` autosaves **before the input loop**, silently overwriting any existing `./draft-session.json` — verified: a quit-only session wipes a 2-pick log to 0 picks. Kyle's real 2026 situation (two leagues drafting the same rounds) makes the collision the *default*; a crash in league 1 becomes unresumable. Refuse to clobber, or uniquify the filename. |
| R3-m10 | `cli/draft.py:73`, `optimize/simulator.py:191` | Duplicate manager ids pass validation: `--managers ben,ben,kyle,levi` gives `oracle recommend` a misleading deep `ValueError` ("ben has no legal asset") and gives `oracle draft` a silently corrupted live session — two seats crediting one merged roster ("F (2/5)" after picks #1 and #2), verified live. One uniqueness check. |
| R3-m11 | `cli/draft.py:307` | `--eliminated` silently drops unrecognized tokens: `--eliminated MON` (Montreal is MTL) or a typo leaves the team fully draftable with no warning while the user believes it's off the board — the same silent-degradation class this round closed elsewhere. Raise on unmatched tokens. |

## Observations (info)

- The regenerated 2023-2025 report's oracle best moved 65.0 → 72.0 (model fixes, not
  tuning — config byte-identical), so the corrected league best of 65.0 now *loses* to the
  oracle rather than tying it.
- SPEC §2's "IR slots: disabled for 2026" is false for the second 2026 league — Press
  Play-offs rosters carry 11 picks with IR_F/IR_D (harmless today; worth a SPEC line).
- `unattributed_uncovered_rows` is write-only (never aggregated into `OddsResult` or the
  CLI guard line); the US-208 import-guard test would leave a stray file in the real
  fixture dir if the session default ever regressed (no cleanup).
- README's interactive examples point at `artifacts/2025-r1`, which doesn't exist —
  verbatim copy-paste of the documented draft-night commands fails; the live
  `EspnGameOddsClient` docstring overclaims that its semantics match the committed
  completion (its favorite attribution is still spread-derived).
- `dedupe_duplicate_events` now KeyErrors on minimal-column frames it previously handled
  (latent, no in-repo caller affected). The goalie-fold guard covers the consumed
  `team_row` value only incidentally via the roster pin.
- The critic's cold-path sweep verified: byte-identical recommendations across OS
  processes (same seed), graceful rejection of wrong-turn/unknown/already-drafted picks,
  forced-goalie endgame correct, `--ir` works cold, and the surprising "Quinn Hughes MIN"
  is correct per the archive (traded Dec 2025).

---

## Priority fix list

**P0 — finish the two majors (they interact; do them in this order):**
1. Apply the US-203 one-liner to the two remaining pivots (`series_sim.py:330` +
   winner-derivation at :491, `shutout.py:291`), with the same real-archive count tests;
   expect honest movement in series-sim/shutout evidence (R3-M1).
2. Then regenerate the 2026-r1..r4 fixtures at the new clean HEAD (the draft board will
   reorder — that's the fixtures becoming true, not a regression) and re-stamp; regenerate
   any model/backtest evidence R3-M1 moved (R3-M2, R3-m4's shared-sha assertion closes the
   detection gap).

**P1 — draft-night safety (one-line-class fixes, worth doing before next spring):**
3. Session-log clobber guard, duplicate-manager uniqueness check, `--eliminated` strict
   tokens, `oracle recommend` honest label (R3-m8..m11).

**P2 — hygiene:**
4. Fresh-clone skip guards on the two real-data tests + README test-prereq note (R3-m2);
   goalie-slot ownership validation (R3-m1); scoped or count-guarded name override
   (R3-m3); `_build_choices` call-site guard (R3-m5); the two gitignore lines (R3-m6);
   the two stale README sentences (R3-m7); SPEC's 2026-IR line.

---

*Round-3 review: 11 per-story fix verifiers, 3 fresh finders, completeness critic, and two
adversarial verifiers per finding (56 agents, all completed, 0 refuted-as-noise survivors).
Fix statuses were established by re-running the original round-2 failure scenarios at HEAD,
never from the story notes. The committed evidence now tells the truth end-to-end; the
remaining work is two scope-completion items and a short safety tail.*
