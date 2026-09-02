# Draft Oracle — Round-4 (Closing) Code & Data Review

- **Date:** 2026-09-02
- **Scope:** the third fix round `8ef9b13..05980f1` (5 commits, 67 files, +3189/−2280)
  implementing US-301..US-305 against `ml/CODE_REVIEW_R3.md`, including the US-305
  regeneration of the 2026-r1..r4 fixtures and all evidence the shootout fix moved.
- **HEAD reviewed:** `05980f1` on `ralph/ml-draft-optimizer`.
- **Gates at HEAD:** 736 tests pass, `ruff` clean, `mypy --strict` clean, tree clean. In a
  clean worktree with no generated data: **731 passed / 5 skipped / 0 failed** — the
  fresh-clone trap from round 3 is closed.
- **Method (deliberately lighter):** 5 fix-verification agents (one per story, each
  re-running the round-3 failure scenario), 2 fresh finders (full recomputation on the
  regenerated evidence; source-diff sweep + cold draft-night path), one adversarial verifier
  per finding. 20 agents, all completed, 0 refuted.

---

## Verdict

**Ready.** All 13 round-3 finding statuses re-verified by independent reproduction:
**13 cleanly fixed**, 0 partial, 0 regressed. The two round-3 majors are dead: the
serve-vs-train Elo skew that measured +35.8 (VGK) at the 2026 R1 freeze is now **exactly
0.0 for all 16 teams on every state primitive**, and all three game pivots return the same
14,508 decided games with identical winners; the 2026-r1..r4 fixtures now name an
ancestor-of-HEAD sha (`6f56cf8`, source-identical to HEAD) shared with all 10 model/backtest
manifests, and two reviewers independently rebuilt r1, r3 (the combined event) and r4 —
cheatsheets and slot reports byte-identical, tables to ≤7e-15. The predicted draft-board
reorder happened (r1 pick 4: G COL → D Bouchard) and was disclosed.

The honesty audit is clean for the fourth time: only metrics, `generated_at` and `git_sha`
moved in any manifest; every movement is explained by shootout inclusion (shutout universe
8958→9696 games, base rate 0.1224→0.1151, series-sim Brier 0.2308→0.2290) and the teams
that lost the most `p_series_win` (PIT, VGK, EDM) are exactly the ones round 3 measured as
most over-rated by the stale serve-path Elo. Several movements went against the tool and were
kept (the oracle strategy now loses to both greedy_vor and one_step on 2023-2025 mean points,
and the report says so). The cold draft-night path is byte-identical across processes with
real names, works offline and with `--ir`, refuses to clobber a session, rejects duplicate
seats and unknown `--eliminated` tokens, and labels degraded opponent models honestly.

**Nothing found this round affects a recommendation or the truth of committed evidence.**
What remains is nine hygiene minors, one of which matters for *process* rather than
correctness: the new provenance-ancestry test is structurally incompatible with this repo's
squash-merge workflow and will fail on `main` after merge unless adjusted (R4-m1).

---

## Round-3 fix scorecard

| R3 finding | Story | Status | Independently reproduced evidence |
|---|---|---|---|
| R3-M1 shootout drop in series_sim/shutout | US-301 | **fixed** | Both pivots derive winners from the `win` column; all three pivots → 14,508 rows with identical `home_win` per game; 1,024 SO games present; the 16 genuine 0-0 SO wins enter the shutout dataset as shutouts (`is_shutout` equals the archive flag on all 14,508 rows); serve-vs-train Elo divergence 0.0 for all 16 R1 teams; 330 legacy-freeze snapshots match training rows exactly; 8 new tests fail on the pre-fix tree. |
| R3-M2 stale 2026-r* fixtures | US-305 | **fixed** | All 4 run manifests + 10 evidence manifests share `6f56cf8`, `git_dirty=false`; r1/r3/r4 rebuilt at HEAD — byte-identical cheatsheets, ≤7e-15 tables; config/seed diff empty; board reorder disclosed and pinned by a regression test. |
| R3-m9 session clobber | US-302 | **fixed** | Quit-only run over a 2-pick log exits 2 with a clear refusal; file byte-identical (`cmp`). (Two sibling paths left open — R4-m2.) |
| R3-m10 duplicate managers | US-302 | **fixed** | `ben,ben,kyle,levi` and `Ben,ben` rejected at parse time in both commands, exit 2, no traceback; `DraftState.new` rejects too. |
| R3-m11 `--eliminated` typos | US-302 | **fixed** | `MON` → "unknown team abbrev(s): MON"; `CoL,XYZ` names only XYZ; lowercase valid abbrevs still remove the team. |
| R3-m8 recommend label | US-302 | **fixed** | Default seats and `Ben,Judah,Kyle,Levi` print "fitted opponents: league-average, no per-manager affinity"; mixed and plain states verified live; matches the interactive label. |
| R3-m2 fresh-clone fails | US-303 | **fixed** | Clean worktree without `data/normalized`: 731 passed / 5 skipped; README documents the four-command prerequisite. |
| R3-m4 any-40-hex provenance | US-303 | **fixed** | Non-ancestor sha fails the ancestry test; a different-but-valid ancestor on one manifest fails the shared-sha test. (But see R4-m1.) |
| R3-m5 `_build_choices` mutant | US-303 | **fixed** | Re-applied mutant → `test_build_choices_call_site_keeps_league_pools_isolated` fails (1 failed / 730 passed). (Sibling call sites still open — R4-m3.) |
| R3-m1 goalie ownership | US-303 | **fixed** | Synthetic goalie duplicate flagged; real parquet 0; the 10 legitimate 2026 cross-league goalie overlaps correctly not flagged. |
| R3-m3 global override | US-304 | **fixed** | `expected_matches: 1` guard; synthetic second bare "McDavid" → "expected 1, found 2"; removal → "found 0"; all nine "Connor McDavid" rows stay exact. |
| R3-m6 gitignore | US-304 | **fixed** | `git check-ignore -v` matches `ml/.gitignore:42` for both paths, after the re-includes. |
| R3-m7 README/SPEC staleness | US-304 | **fixed** | No "ship empty" claim; cwd autosave + refusal documented; zero `2025-r` references; SPEC §2 states the two-league IR facts; `unattributed_uncovered_rows` surfaced in `OddsResult` and the CLI guard line (6917). |

---

## New findings — minor (all adversarially confirmed; no critical, no major)

| # | Location | Finding |
|---|----------|---------|
| R4-m1 | `tests/test_committed_model_evidence.py` | **The ancestry guard is incompatible with this repo's workflow.** `main` has 0 merge commits (PRs land as squash commits), so once this branch is squash-merged the recorded sha `6f56cf8` is no longer an ancestor of `main` HEAD and all 14 parametrized tests fail permanently until every artifact is regenerated on `main`. A `--depth 1` clone also hard-fails (exit 128 "Not a valid commit name" is asserted as non-ancestry rather than skipped). ml tests aren't in `.github/workflows` yet, so this bites locally today and on `main` tomorrow. Fix options: skip on exit 128; assert the sha is *reachable from the branch that produced it or recorded in a pinned evidence-pass file* rather than ancestry of HEAD; or plan one regeneration commit directly on `main` post-merge. |
| R4-m2 | `cli/draft.py:799`, `_run_loop` | The R3-m9 clobber guard covers only the new-session branch. Two sibling paths still silently overwrite: `--resume A --session B` when B exists (verified: 2-pick log → 0 picks), and the in-loop `resume <path>` command, which autosaves the resumed session over the *launch* log (verified: league1.json ends up holding league2's picks). Same two-league scenario, same class. |
| R4-m3 | `optimize/opponents.py:899,954` | The R3-m5 call-site guard covers `_build_choices` only; hardcoding league-blind keys at `_membership_for_season` or `_per_pick_accuracy` passes the full suite while moving the committed opponent evidence (2026 membership events 6→3, accuracy 0.2875→0.1845; per-pick picks 240→143). |
| R4-m4 | `ingest/entity_match.py:196` | `expected_matches` on a `teams:` override is parsed, validated, then silently discarded — a future goalie/team override would *appear* guarded and never be. Enforce or reject the key. |
| R4-m5 | `ingest/entity_match.py:210` | The override count-guard counts by *raw* name while the override is applied to `corrected_name` when present. Verified: adding `corrected_name='Connor McDavid'` to the 2024 row silently bypasses the Draisaitl override with the guard still passing. `corrected_name` is in real use (row 104 Makar→Bouchard). Count on the same key the override consumes. |
| R4-m6 | `ingest/odds.py:1800` | The *live* ESPN summary client reads the per-side favorite flag to pick the moneyline, then discards it and sets `favorite_side` from the spread — defaulting to `'away'` when the spread is missing/blank, covered=True. The offline completion parser already does this right (returns unattributed). Future-refresh only. |
| R4-m7 | `models/series_sim.py:770` | The regenerated series-sim report's honesty note hard-codes "~40 playoff series held out" while the same report and manifest say `series_scored: 30`. Derive the sentence from the count. |
| R4-m8 | `artifacts/2026-r3/teams.csv`, `projection_artifact.py:362` | `_apply_combined_valuation` folds R4 into `e_goalie_points` only, leaving `e_wins`/`e_games`/`e_shutout_wins` as R3-only values, so the SPEC identity `e_goalie_points == 2E[wins] + 2E[shutouts]` fails by up to 4.73 on the r3 table (holds to 1e-15 on r1/r2/r4). The fold is correct and guarded (US-204), but the column contract doesn't say so and a consumer recomputing from `e_wins` gets the R3-only number. Document the fold in the README column list (or emit `e_wins_combined`). |
| R4-m9 | `models/game_win.py:225`, `series_sim.py:305`, `shutout.py:264` | R3-M1 happened because one of three near-identical pivots was fixed; the fix round patched the other two in place rather than consolidating, so train/serve consistency is enforced by tests, not by construction. Verified behavior-identical → a shared helper would be a pure refactor. |

### Uncertain (recorded honestly, not confirmed)

- **`one_step` baseline row 58.44 (committed) vs 58.31 (reproduced at HEAD on Linux)** in
  the 2023-2025 backtest report. Every other number in both backtests reproduces exactly;
  two Linux one-step runs are byte-identical to each other; the config diff is empty. The
  evidence was generated on Windows, so the likely cause is a platform-dependent float
  tie-break in the depth-1 owner-fill argmax flipping one pick — not nondeterminism, not
  tuning. The verifier's own full reproduction didn't finish in time, so this stays
  uncertain. Impact: none on conclusions (the row's win rate and the report's verdict are
  unchanged); worth a note in the manifest that fixtures reproduce to float-ULP across
  platforms, not byte-for-byte.

## Observations (info)

- Round-cutoff freezes intentionally differ from training-row Elo when a prior series
  outlasts the next round's cutoff (by design). Related: MTL's R1 game 7 is excluded from
  its R2 snapshot while eligibility uses the post-cutoff outcome — a documented consequence
  of freezing at round start.
- Run manifests don't record generating CLI flags; the committed r4 was evidently built with
  `--no-slot-strategies`, which a default rebuild can't tell from the manifest.
- The opponent membership evaluation silently drops 2025 R1 (no snake order in the sheet);
  the report doesn't disclose it.
- SPEC §5 and PROVENANCE still describe the Kaggle/ESPN 2022-23…2025-26 favorite prices as
  usable; the pipeline (correctly) carries them 100% `covered=False`.
- `--eliminated` reports a real NHL abbrev that's merely absent from the artifact pool as
  "unknown team abbrev"; the honest opponent label in `oracle recommend` prints only after
  the rollouts finish; the US-305 progress note under-discloses that the oracle strategy now
  loses to both baselines (the *report* discloses it).
- Verified clean: no double-counted or excluded decided game in any pivot; no loser
  mis-credit on 0-0 SO games; the goalie-ownership validator has no false positives on the
  two-league 2026 season; the override loader stays backward compatible with bare-int
  entries; the cold path is byte-identical across processes.

---

## Recommendation

Merge-ready from a correctness standpoint. Before (or as part of) the merge to `main`:

1. **R4-m1** — make the ancestry guard survive squash-merge and shallow clones (skip on
   exit 128; compare against a pinned evidence-pass sha list rather than ancestry of HEAD),
   or budget one regeneration commit directly on `main`. Without this, the ml suite goes
   red on `main` the moment the PR lands.
2. **R4-m2** — extend the clobber refusal to `--resume … --session` and the in-loop
   `resume` command (same three-line check).
3. **R4-m5 / R4-m4** — key the count-guard on the name the override actually consumes;
   enforce or reject `expected_matches` on team entries.

Everything else is optional polish. These are small enough to land as one short story or a
direct commit; a fifth review round is not warranted — a spot-check of the three items above
is sufficient.

---

*Round-4 closing review: 5 per-story fix verifiers, 2 fresh finders, one adversarial
verifier per finding (20 agents, all completed). Across four rounds, 71 findings were
raised and adversarially confirmed; 69 are now verified fixed, 2 folded into their
successors. The committed evidence tells the truth, and the tool is deterministic and
honest end-to-end.*
