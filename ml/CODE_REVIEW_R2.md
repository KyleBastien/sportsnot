# Draft Oracle — Round-2 Code & Data Review

- **Date:** 2026-08-31
- **Scope:** the fix round `5f5925a..7cb422c` (20 commits, 90 files, +8790/−3771) implementing
  stories US-101..US-119 against the round-1 findings in `ml/CODE_REVIEW.md`, plus the
  un-storied final commit `7cb422c`.
- **HEAD reviewed:** `7cb422c` on `ralph/ml-draft-optimizer`.
- **Gates at HEAD:** 652 tests pass, `ruff` clean, `mypy --strict` clean, tree clean.
  (The 656-vs-652 count discrepancy vs the US-117 note is fully explained: 656 was true at
  US-117; US-118 added 8, US-119 removed 20 with the sanctioned `team_series.py` deletion and
  added 8 — the Elo math those tests covered is re-tested in `test_elo.py`. Nothing protective
  was deleted.)
- **Method:** 19 fix-verification agents (one per story, each instructed to re-run the
  *original* round-1 failure scenario rather than trust the story notes), 6 fresh-regression
  finders over the diff and the regenerated artifacts, a completeness critic, and adversarial
  verification of every non-info claim. The verification pass was interrupted mid-run by an
  org spend limit; it was completed afterwards with one adversarial verifier per remaining
  distinct finding (heavily duplicated findings were folded onto their already-verified twins).
  Every finding below marked **confirmed** was independently reproduced by at least one
  adversarial verifier; nothing rests on a single reviewer's claim.

---

## Verdict

**The fix round is genuine.** All 33 round-1 findings were re-tested by independent
reproduction of the original defect: **31 are cleanly fixed** with guarding tests, **2 are
partial** (M-5, M-8 — the code fixes are real; the gaps are a stale committed artifact and
metadata-only test assertions), **0 not fixed, 0 regressed**. Both criticals are dead: the
Kaggle placeholder market is honestly gone (2024-25 now has zero historical coverage,
stated plainly), and favorite attribution now comes from the ESPN raw summaries
(595 home / 308 away favorites, independently recounted from all 903 summary files).

**Where round 2 found problems, they cluster in one layer: committed evidence and reporting,
not draft picks.** No new critical. Five new majors — the two worst being a stale pre-fix
backtest artifact committed at HEAD and a league-comparison path that pools the two 2026
leagues — plus one genuine data error in the league history (a 2024 entity-match mistake that
inflates the committed league table), one pre-existing model-input bug (shootout games
silently dropped from game-win training), and one test blind spot (the exact M-6 defect can
be reintroduced without failing a single test).

**Highlights verified clean this round** (adversarial checks that found nothing): the
regenerated 2026-r1..r4 artifacts pass every structural/computational check and reproduce at
HEAD to float-ulp precision from their manifest's commit `8000f5b` (`git_dirty: false`); the
regenerated 2023-2025 backtest report reproduces **byte-identically** at HEAD and its league
table recomputes exactly from the raw sheets + archive (IR swaps honored); the vectorized and
object rollout paths agree to 1.4e-14 across a 120-trial randomized parity sweep; the fitted
opponent model demonstrably drives `oracle draft`/`recommend` offline (2,800 fitted picks,
zero greedy, network blocked); the odds guard mesh has no false positives on the committed
archives; the leakage guard hardening produced no false positives across all 9 regenerated
rounds; and the shutout model's no-skill result remains honestly reported (shrinkage was
evaluated and honestly *not* adopted).

---

## Round-1 fix scorecard

| R1 finding | Story | Status | Evidence (independently reproduced) |
|---|---|---|---|
| C-1 Kaggle favorite semantics | US-102/105 | **fixed** | Spread-based attribution removed: 0 covered Kaggle rows (all 29,417 two-row games have identical spreads on both rows → unattributed). ESPN completion reads `homeTeamOdds.favorite` from raw summaries: 903 covered, 595 home / 308 away favorites — recounted from the raw `.json.gz` files, matches the parser exactly. Real-file tests pin it. |
| C-2 placeholder −105 as coverage | US-101/105 | **fixed** | Per-season guard rejects all 20,260 placeholder rows (2004-2018 whole-season, 2019 modal 98.7%, 2025, pre-Dec-11 2026). 2024-25 honestly has zero market coverage. SBR 2017-2023 passes through 1:1; ESPN 2026 survives (902 rows). `xval_delta` genuinely gates at 0.15. Six tests incl. two real-archive tests. |
| M-1 pre-round artifact impossible | US-112 | **fixed** | Built a 2024 round-2 artifact from a round-1-only archive at cutoff 2024-05-06 (day after R1's last game) with the correct 8-team bracket; also a pre-playoffs R1 artifact. Fails loudly without a bracket. Shares the cutoff function with the normal path (no fork). |
| M-2 UTC date join drops ~2/3 odds | US-103 | **fixed** | Attach rate re-measured: 33.8% (no-snap control, reproducing the defect) → 99.98% of covered odds for consumable games (8,837/8,839). No join fan-out, zero duplicate keys. Test pins ≥95% with a no-normalization control. |
| M-3 opponent double-count / pooled leagues | US-106 | **fixed** (in `opponents.py`) | Hand-recounted from the parquet: ben/judah/levi 87, kyle 120 (87 Gemmell + 33 Press) — matches the refit committed manifest; pools are league-isolated (36 single-league pools). Committed artifact reproduces byte-for-byte on refit. **But the same pooling bug survives in `_league_comparisons` — see R2-M1.** |
| M-4 April-window playoff mislabels | US-104 | **fixed** | `is_playoff` now from archive `gameTypeId`: 0 mislabels in either direction over all 8,839 covered rows (control run without the archive index reproduces 998 mislabels). 2020 Aug-Sep and 2021 May-Jul windows label perfectly. |
| M-5 mid-series market Brier | US-109 | **partial** | Code fixed and tested: `_market_series_prob` uses only the series' game-1 pre-series line (hand-recomputed BUF-BOS 2026: −166 → 0.5972 → 0.7047, exact match); the 2023-2025 report carries the truthful relabel. **Partial because the committed 2026-combined report still publishes the old mid-series number — see R2-M2.** |
| M-6 stale backtest report / R3-only grading | US-111 | **fixed** | The committed 2023-2025 report scores R3_4 across rounds 3+4 and reproduces **byte-identically** on a HEAD rerun; every league cell recomputes exactly from raw sheets + archive (2024 mean 58.75 / levi 78, 2025 mean 59.75). **But see R2-M4: the 78 itself embeds a 2024 entity-match error, and R2-m16: this leg has no regression test.** |
| M-7 IR swap violated in league scoring | US-107 | **fixed** | Re-ran the review's scenario at HEAD: 10.0, not 13.0 (no-swap control still 13.0). Reproduced on real 2025 rosters (levi R1 56→59, matching the sheet's own points column); all 24 recomputed 2024/2025 league cells match the committed report. 2026 has zero `ir_activated` flags, so non-IR scoring is untouched. |
| M-8 no round-2..4 / combined e2e tests | US-108 | **partial** | Five real e2e tests run rounds 2, 3, and combined R3_4 (16→8→4 narrowing, `scored_rounds==[3,4]`, leakage over the R3\|R4 union). **Partial because the combined-event assertions are metadata-only — see R2-M5.** |
| M-9 CLI never uses fitted opponents | US-113 | **fixed** | `--opponents {greedy,fitted,auto}` (auto → fitted when the committed artifact exists) + `--managers`. Instrumented live run against `artifacts/2026-r1` with sockets blocked: 2,800 `FittedOpponentModel.pick` calls, zero greedy; manifest-only load; 6.3s at 500 rollouts; end-to-end test asserts fitted use. |
| M-10 snapshot pinning hollow | US-115 | **fixed** | `create_snapshot` freezes league picks/odds/injuries with a completeness manifest; both pinned entry points call `_require_complete_snapshot` and read every input from the snapshot dir. Seven attack scenarios on /tmp copies all fail loudly; a complete pinned run demonstrably consumes only frozen inputs. |
| M-11 ESPN ids vs NHL ids no-op join | US-114 | **fixed** | ESPN athlete ids resolve via name+team+position through `entity_match`: 61/62 injured skaters (98.4%) from the 903 real summaries resolve into the 8.4M+ NHL range; the injured flag and IR stash demonstrably fire on mapped ids; unresolved ids are kept and loudly reported. |
| m-1..m-4, m-6..m-18, m-20 | US-110/116/117/118 | **fixed** | Each re-verified at its fix site with a guarding test — including the leakage-guard desync catch (m-2), round-cutoff snapshot freezes verified to 1e-12 against an independent Elo replay (m-3), historical replays with `injuries=None` (m-4), the 2020 round-robin exclusion on real data (m-6), exact vectorized/object parity incl. the dry-pool raise (m-7..m-9), honest slot labels (m-10), `team_id=None` fail-safe (m-11), the conftest socket guard (m-16), 2026-r* regenerated at clean `8000f5b` (m-14/m-18), and deterministic reports (m-20). |
| m-5 de-vig inversion | US-102 | **fixed** | `devig_favorite_only` floors at 0.5 across the whole (−100, −110) band; unit + Hypothesis property tests. |
| m-19 CLI imports training stack | US-117 | **fixed in letter, not in spirit** | The CLI *root* is lazy, and a subprocess test blocks lightgbm/sklearn/httpx — but only for `--help`. A real `oracle draft` run still imports all three via `optimize/__init__`'s eager re-exports. See R2-m9. |

---

## New findings — major

None of these change draft recommendations. R2-M3 affects model training inputs; the rest
live in the committed-evidence and league-history layer.

### R2-M1 · `_league_comparisons` pools both 2026 leagues — the committed 2026 league table scores rosters that never existed
`ml/src/draft_oracle/backtest/replay.py:1034` — **confirmed** (reproduced by two independent verifiers)

The M-3 fix (dedupe + league-aware pooling) landed only in `optimize/opponents.py`.
`_league_comparisons` still scopes on `(season, draft_event)` and groups by `manager` alone —
no `league_name`, no `dedupe_duplicate_events`. For 2026, where kyle plays in both The Gemmell
Cup and Press Play-offs, his 29 R1 rows (11 Press + 9 Gemmell app + 9 Gemmell sheet) merge into
one 15-skater/2-goalie chimera scoring **72.0** — exactly the committed report's number — while
his real per-league rosters score 50.0 (Press) and 37.0 (Gemmell). The committed
`2026-combined-r500` report's league table lists 7 managers from two different 4-manager
leagues against a 4-manager oracle replay, and its "League best 72.00/77.00/74.00" headlines
are built on the merged rosters. Secondary fragility: an exclusion flag is honored only if
*every* duplicate row carries it (ben's Alex Tuch is `points_excluded` in the sheet copy but
not the app copy). 2023-2025 is unaffected (single league). Fix: apply
`dedupe_duplicate_events` and group by `(league_name, manager)` (or reuse `_event_keys`),
add a 2026 regression test, then regenerate the 2026 report.

### R2-M2 · The committed 2026-combined backtest artifact is stale pre-fix output published at HEAD
`ml/artifacts/backtests/2026-combined-r500-seed20260827/` — **confirmed** (two verifiers, clock-independent proof)

The artifact's `generated_at` is 2026-08-29T12:47Z — roughly **seven hours before the first
fix commit** (US-101, 19:41Z) — yet it was committed at HEAD in the catch-all commit
`7cb422c`, against the fix round's own progress-log instruction not to commit it. Its Track-2
wording is byte-identical to the *pre*-US-109 report template, so HEAD's code cannot have
produced it. Its market-aware Brier (0.2080) was computed on the corrupted round-1 odds layer
with the condemned mid-series semantics; recomputed at HEAD over the same 14 series, the
honest game-1 benchmark gives **0.2339 — worse than the model's 0.2179, flipping the
"market beats model" conclusion**. Its opponents were fit on the un-deduped pick table, and
its manifest carries no git provenance to reveal any of this. Fix: rerun
`ml/scripts/run_2026_backtest.py` at HEAD (after R2-M1) and recommit, or delete the artifact.

### R2-M3 · `_pivot_games` silently drops all shootout games (~5–7% of every season)
`ml/src/draft_oracle/models/game_win.py:253` — **confirmed** (pre-existing at 5f5925a, not a fix-round regression; missed by round 1)

`games.loc[games["home_goals"] != games["away_goals"]]` assumes tied totals mean an undecided
game, but the NHL archive records shootout games with *equal* `goals_for` on both sides (the
SO deciding goal is not counted) while the same rows carry the true decision in `win` /
`wins_in_shootout`. Every shootout game is therefore excluded from game-win training/eval,
from Elo state updates, and from the market-join target — 65/952 games in 2020-21, 77/1,398
in 2024-25, 5.5–8.5% across all 11 seasons — decided games with known winners and real market
prices, biasing the training universe toward decisive games. (This is also the sole cause of
the last unattached covered 2021 odds rows after the M-2 fix.) Fix: derive `home_win` from
the `win` column instead of goal comparison.

### R2-M4 · 2024 entity-match error: levi's R3_4 "McDavid" is provably Draisaitl — committed league table inflated by 14 points
`ml/src/draft_oracle/ingest/entity_match.py` (lastname path) / `ml/data/normalized/league_draft_picks.parquet` row 99 — **confirmed** (triple-exact reproduction)

The 2024 R3_4 sheet row "McDavid" for levi was lastname-matched (confidence 0.9,
`needs_review=False`) to Connor McDavid — who judah *also* owns in the same event, an
impossible duplicate under full re-draft rules. The sheet's own point columns identify the
player as Leon Draisaitl (points_when_drafted 24 / points_for_round 7 / current_total 31 —
Draisaitl's archive splits exactly; McDavid's 21/21/42 match judah's row exactly; the R1/R2
sheets confirm judah owned Draisaitl and levi owned McDavid through R2 and they swapped at the
re-draft). Corrected, the committed 2023-2025 report's 2024 R3_4 cells become levi **64** (not
78), league mean **55.25** (not 58.75), and "League best 78.00" becomes 65.00 — which *ties*
the oracle best rather than beating it. Round 1's hand-checked ground truth embedded the same
error, so US-111's reconciliation passed while the number was wrong. Nothing guards against
two managers owning the same `player_id` within one `(league, season, draft_event)`. Fix: a
name override for this row, a duplicate-ownership validation in the parser, and regeneration
of the 2023-2025 report.

### R2-M5 · Combined R3_4 scoring has no numeric test guard — M-6's exact defect can return without failing a single test
`ml/tests/test_backtest.py:466` / `ml/src/draft_oracle/backtest/replay.py:241` — **confirmed by mutation testing (twice, independently)**

The new combined-event e2e tests assert only metadata (`scored_rounds==[3,4]`, team sets,
leakage flags). Mutating the roster scorer to sum only the first scored round — the literal
M-6 defect — leaves every combined-event number wrong (seat-1 oracle points drop 101.0→63.0)
yet **all 652 tests pass**. The same holds for the goalie-side fold (deleting the
`p_advance * e_goalie_r4` term passes the suite, R2-m7) and for the league-comparison leg
(R2-m16). Fix: assert one concrete cross-round total on the deterministic four-round fixture.

---

## New findings — minor (all adversarially confirmed)

| # | Location | Finding |
|---|----------|---------|
| R2-m1 | `ingest/odds.py` (~1078) | The xval gate compares each source's *favorite* probability, so two sources naming **opposite** favorites at similar magnitude pass with delta ≈ 0 while true home-prob disagreement is ~0.2. Latent (covered sources never overlap today). |
| R2-m2 | `ingest/odds.py:995` | `parse_espn_completion`'s fallback resolver returns `"away"` (covered=True) when both the summary favorite flag and the home spread are missing, instead of emitting unattributed — the exact guess C-1 banned for Kaggle. Never fires on committed data (903/903 summaries have the flag); would fabricate attributions on a future refresh. |
| R2-m3 | `tests/test_opponents.py` | The league-isolation half of the M-3 fix has no regression test: reverting `_event_keys` to `['season','draft_event']` (re-merging the 2026 cross-league pools, 36→27) passes the **entire 652-test suite**. |
| R2-m4 | `optimize/opponents.py:245` | App-preferred dedupe discards the sheet copy's resolved `team_id`s (app fill 11% vs sheet 92%), starving the team-affinity feature — the model's dominant coefficient (β=2.85) — of ~15 team-bearing picks per manager for 2026 Gemmell. Merging sheet `team_id`s into the kept app rows (identical player sets, verified) recovers the signal. |
| R2-m5 | `ml/artifacts/models/*/manifest.json`, `backtests/*/manifest.json` | No committed model or backtest manifest carries `git_sha`/`git_dirty` — all were generated before US-117 added stamping and never restamped (only the 2026-r* run manifests have it). The R2-M2 staleness was undetectable from the artifact itself — the same gap round 1 flagged as m-14. A HEAD rerun writes the stamps. |
| R2-m6 | `ml/artifacts/models/game-win/` | US-105's "manifests record the new coverage per season" is unmet: only the aggregate `test_market_coverage` (0.343) is recorded; no committed artifact states that the entire 2025 test half is uncovered (2024 0/1449, 2025 0/1439, 2026 902/1415). |
| R2-m7 | `projection_artifact.py:362` | The goalie-side combined-event fold has no fresh-run numeric test: deleting the `p_advance * e_goalie_r4` term passes all 652 tests (the only numeric check validates the *committed* r3 manifest's self-consistency, which a code mutation cannot perturb). |
| R2-m8 | `ml/artifacts/models/skater-production/`, `series-sim/`, `skater-projection/` | US-110's promised evidence-regen pass never ran: these three committed reports embed the pre-fix 2020 labels/snapshots and are unreproducible at HEAD (skater-production train rows 5157→4837; 2020 matchups 30→15). Metric drift is small and conclusions hold, but the committed evidence doesn't match HEAD's own pipeline. |
| R2-m9 | `optimize/__init__.py` / `tests/test_cli.py:42` | m-19 residual: a real `oracle draft` run still imports lightgbm/sklearn/httpx via `optimize/__init__` → `ir_value` → `models.projections` (and `models.returns` → `nhl_api`). The US-117 subprocess guard only exercises `--help`, so it asserts a weaker property than the story's criterion. |
| R2-m10 | `cli/draft.py` | Default `--managers 4` seats (`seat1..seatN`) match no fitted per-manager coefficients, so the "fitted opponents"-labeled model runs with its dominant affinity signal entirely zeroed — silent degradation under the default invocation (seat1 ranks McDavid first where ben's real model ranks affinity picks first). Warn or fall back explicitly. |
| R2-m11 | `optimize/recommend.py:667` | `_vectorized_fitted_expected` collapses per-manager `need_weight` to the last-iterated manager's value (scalar overwritten in the loop), diverging from the object path when managers differ. Latent — production wiring gives every manager the same weight, and the parity test uses uniform weights. |
| R2-m12 | `ingest/nhl_api.py:408` | The skater_summary 10k-cap guard checks `response.total` only when present; a response omitting `total` with exactly-capped data passes silently. Add a `len(data)` fallback. |
| R2-m13 | `tests/test_committed_projection_artifacts.py` | The committed-artifact regression tests read only the parquet files and manifests, never the committed CSVs: truncating `artifacts/2026-r1/skaters.csv` to 200 bytes passes all 652 tests. A csv-vs-parquet equality check closes it. |
| R2-m14 | `ingest/odds.py` | The documented orientation-flipped SBR pair (2020-01-17 PIT/DET, PROVENANCE §5) passes the gameTypeId match (which indexes both orientations) but can never date-snap or market-join (single true orientation) — covered-but-unjoinable, uncounted by the unmatched-row accounting. |
| R2-m15 | `optimize/recommend.py:584,751` | Fast paths tie-break by projection-then-key; object paths by `rank_value`-then-key. On exact opponent-score ties (real pools contain them) the paths pick different assets — demonstrated divergence up to 12 pts/candidate. No parity test uses tied values. |
| R2-m16 | `backtest/replay.py:1033` | The M-6 *league-comparison* leg has no regression test: mutating `_league_comparisons` back to R3-only grading passes the full suite. The combined league grading is guarded only by the committed report itself. |
| R2-m17 | `ml/README.md` | README is stale against the fix round in four places: (1) quotes the pre-US-106 double-counted opponent validation numbers (.269/.261/.180, top-1 .126 vs .112) that the committed artifact now contradicts (.222/.273/.308, .113 vs .104); (2) the Betting-odds section still documents date-window playoff tagging, the September-only preseason drop, and Kaggle as a usable price source (the pre-C-1/C-2/M-2/M-4 pipeline); (3) the injuries schema still defines `player_id` as the ESPN athlete id — the exact semantics US-114 removed — and omits the new `espn_id` column; (4) the features/ directory line still describes the deleted team/series matrix (the deletion is correctly documented at line 434). |
| R2-m18 | `cli/draft.py:786` + `ml/.gitignore` | `oracle draft` autosaves `draft-session.json` into the artifact directory by default; combined with the blanket `!artifacts/2026-r*/**` re-include, a live draft session plants a mutable, committable file inside the committed reproducibility fixtures — one catch-all commit (the pattern `7cb422c` itself just exercised) away from contaminating them. |

## Refuted / downgraded (recorded for honesty)

- **Surname-fallback mis-map (injuries)** — refuted. No mis-mapped real entry exists anywhere
  in the repo; the committed fixture resolves cleanly (exact matches; goalies deliberately
  unresolved; `unresolved_espn_ids=[]`). The fallback does accept a unique surname without
  first-name/team confirmation (a fabricated "Zeke Draisaitl" resolves to Leon), but that is a
  hypothetical requiring a skater absent from the 2,156-player dimension — and mirrors the
  codebase-wide lastname policy. Worth a first-initial check someday; not a defect today.
- **`fef5484` "deleted a snapshot guard test"** — refuted. The `pytest.raises(FileNotFoundError)`
  assertion survives verbatim (absorbed into the tail of the new completeness test, and it
  executes); the freeze-time guard for required tables is intact, and the pinned-run layer has
  its own loud-failure test. The only blemish is cosmetic (an anonymous assertion appended to
  an unrelated test).

## Observations (info)

- The xval_delta gate is structurally vacuous on today's committed archives — no two sources
  ever co-cover a game. It fires only in synthetic tests; it is a forward-looking safeguard.
- Series-sim calibration still evaluates under legacy per-matchup freezes while production
  drafts from round-cutoff freezes (5/165 real snapshots differ) — divergence undocumented.
- `playoff_round_cutoffs` fabricates a phantom next-round cutoff for completed seasons
  (harmless today).
- Opponent-artifact auto-detection is cwd-relative: running outside `ml/` silently degrades
  auto → greedy.
- The import diet duplicated a dozen default-path constants into the CLI with no drift guard;
  `recommend`/`draft` label output "fitted opponents" even when seat ids prevent per-manager
  models from attaching (see R2-m10).
- The live ESPN summary path still derives `favorite_side` from the spread while taking the
  price from per-side flags — pre-existing, now inconsistent with the C-1 resolver.
- `rules.py`'s module docstring still says the golden vectors are "copied from" `utils.test.ts`
  (they are equivalent, not copied); `_row_seed` still masks `player_id` to 16 bits.
- `apply_overrides`' docstring states a stale matching precedence (espn_id first) contradicting
  the implemented player_id-first order.
- Commit `7cb422c`'s non-artifact contents are ralph-harness tooling; no ml gate was weakened
  (98 tests added vs 21 removed, all within the sanctioned US-119 deletion; no skips/xfails).

---

## Priority fix list

**P0 — the committed evidence should tell the truth (none of these change picks):**
1. Fix `_league_comparisons`: apply `dedupe_duplicate_events`, group by `(league_name,
   manager)`, honor exclusion flags across duplicates, and add a 2026 two-league regression
   test (R2-M1, R2-m16, R2-m3).
2. Add a `name_overrides.yaml` entry for levi's 2024 R3_4 Draisaitl row and a
   duplicate-ownership validation; regenerate the 2023-2025 report (R2-M4).
3. Regenerate (or delete) the 2026-combined-r500 backtest at HEAD — after items 1–2 —
   and restamp all committed model/backtest manifests with git provenance (R2-M2, R2-m5).

**P1 — model correctness and guardrails:**
4. Derive `home_win` from the archive's `win` column in `_pivot_games`; retrain/regenerate
   the game-win report (R2-M3).
5. Add numeric combined-event assertions to the four-round fixture: a cross-round roster
   total, the goalie `p_advance` fold, and the league leg (R2-M5, R2-m7, R2-m16).
6. Run the US-110 evidence-regen pass that never happened: skater-production, series-sim,
   skater-projection (R2-m8).

**P2 — hygiene:**
7. Merge sheet `team_id`s into deduped app rows to recover the 2026 affinity signal (R2-m4).
8. README refresh for the four stale sections (R2-m17); return `None` from the ESPN completion
   fallback (R2-m2); `len(data)` fallback in the skater_summary guard (R2-m12); csv-vs-parquet
   check in the committed-artifact tests (R2-m13); move the default draft-session autosave out
   of the artifact dir (R2-m18); warn on seatN fitted degradation (R2-m10); align fast-path
   tie-breaks or add a tied-value parity test (R2-m15); per-manager `need_weight` array in the
   fitted kernel (R2-m11).

---

*Round-2 review conducted with 19 per-story fix-verification agents, 6 fresh-regression
finders, a completeness critic, and adversarial verification of every non-info finding
(two verifiers where the budget allowed, one for the post-interruption remainder; duplicate
findings folded onto verified twins). Fix statuses were established by re-running the original
round-1 failure scenarios against HEAD, never from the story notes.*
