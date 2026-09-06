# PRD: Draft Oracle v2 — Model & Analysis Improvements

## Introduction / Overview

The Draft Oracle (`ml/`, PRD `tasks/prd-ml-draft-optimizer.md`) shipped, survived four
adversarial review rounds (`ml/CODE_REVIEW*.md`), and its committed evidence is honest and
reproducible. It is also **only modestly good**. Replaying 2024–2026, the oracle's average
seat would have won the league 2 of 4 times and finished second twice; it beat the average
manager in 10 of 12 rounds but lost to the *best* manager in 5 of 12. The reviews and the
committed model reports point at exactly where the accuracy is missing:

| Component | Where it stands today (committed reports at `main`) | Why it matters |
| --- | --- | --- |
| Skater per-game production | MAE 0.2455 vs 0.2660 for "sort by regular-season PPG"; rank ρ 0.579 vs 0.568 | The model barely out-ranks a spreadsheet. Features are box-score rates only (`features/skater.py`: G/A/P per game, last-25 form, PP share, TOI, shots, sh%, age, linemate PPG, team GF/G). |
| Round-point projection | MAE 1.376 vs 1.496 (PPG × 5.5); ρ 0.593 vs 0.580 | Same story one level up; quantile coverage is never checked. |
| Per-game win | Brier 0.2427 vs 0.25 coin flip; market adds +0.0005 on 34% coverage | Near the NHL ceiling for box-score Elo; the market is barely used. |
| Series winner | Brier 0.229 held out (30 series); the 0.40–0.60 bin predicted 0.517, observed **0.214**; 7-game series predicted 30%, observed 17% | Miscalibrated where it matters — toss-ups — and the length distribution is wrong. |
| Goalie/team slot | Team rank ρ **0.20–0.46**, MAE ~2.8–3.2 goalie points per round across the backtests | The single biggest lever in the game (Carolina's goaltending was 40 of the winning 74 points in the 2026 final) is the least accurate component. |
| Shutout | Brier 0.0923 vs 0.0921 base rate — **no skill** | Shutouts are +2 points each; the model cannot tell teams apart. |
| Draft strategy | Oracle 58.08 vs greedy-VOR 58.28 vs one-step 58.44 (2023–25); a statistical tie every time | The multi-step rollout buys nothing; and the 36-draft / 64-rollout backtest cannot detect a 1-point edge anyway. |
| Opponent model | Membership 0.287/0.341/0.287 vs greedy 0.231/0.216/0.292; per-pick top-1 0.113 | Weak, but the affinity coefficient (+3.0) is real. Relevant here only for survival probabilities (league-agnostic accuracy is the goal). |

This PRD is a **single, ordered research roadmap** of twenty stories. It starts by upgrading
the evaluation harness so a real improvement can be told from noise, then brings in the data
the current models cannot see (purchased odds history, a longer NHL archive, shot-quality and
goaltending data), then rebuilds the components whose error dominates roster outcomes — the
goalie/team slot, joint (correlated) roster valuation, skater usage features — and finally
adds the methodology and draft-night pieces (calibrated intervals, injuries and lineup signal,
a standings-aware objective, explainability, drift monitoring) before one evidence pass and a
plain-language verdict. The stack is widened (Bayesian hierarchical models, gradient-boosting
variants, conformal methods, one exploratory neural model), but the small-data discipline and
the honesty rules of `ml/SPEC.md` §7 stay in force: every "improvement" is a *challenger*
measured against the frozen committed *champion*, and a miss is reported, never tuned away.

**Owner decisions incorporated:** the goal is the best possible *calibrated, league-agnostic*
projections; all data sources are in scope including paid API tiers; every story in this
document is committed work (no deferred backlog); success is judged on replayed-season
outcomes; the pinned stack may be widened. The resolved open questions are recorded in
**Decisions** at the end.

## Glossary

- **Champion / challenger** — the committed artifacts at `main` are the champion; a story's
  model variant is the challenger. A challenger ships only if it beats the champion on the
  frozen held-out protocol with a reported confidence interval.
- **Held-out protocol** — leave-future-out: train through season *t−1*, test on *t*, for
  every *t* in the last four seasons (2023–2026); pooled metrics with per-season breakdown.
- **Paired bootstrap** — resample *drafts* (not picks) with replacement, recompute the metric
  difference between two strategies on the same draws, report the 95% interval.
- **Decision regret** — for one draft, hindsight-optimal roster points (the best legal roster
  from the players actually available at each of the owner's turns, scored on actuals) minus
  the drafted roster's actual points. Lower is better; it isolates drafting skill from
  season-level scoring variance.
- **Joint roster simulation** — sampling every series outcome once per Monte Carlo draw and
  deriving all players' games and points from that shared draw, so players on the same team
  (and the goalie slot) are correlated the way they are in reality.
- **GSAx, xG** — goals saved above expected (goalie), expected goals (shot quality); both
  published free by MoneyPuck.
- **Pre-series market benchmark** — the game-1 moneyline of a series, de-vigged and pushed
  through the best-of-7 simulator to a series probability. The Odds API exposes no
  per-series "to win series" market (its `outrights` are Stanley Cup futures), so this is the
  market benchmark throughout.

## Goals

- Raise the oracle's replayed-season record from **2 of 4 wins to at least 3 of 4** on
  2024–2026 (Gemmell Cup ×3, Press Play-offs ×1), and the rounds where its best seat matches
  or beats the league's best manager from **7 of 12 to at least 9 of 12**.
- Make the goalie/team slot trustworthy: pooled team rank correlation from 0.276 to **≥ 0.50**,
  goalie-slot MAE below 2.5 points, series-winner Brier at or below the pre-series market
  benchmark on **≥ 90 series** (every postseason 2020–2026 with purchased odds history).
- Make skater projections meaningfully better than the PPG spreadsheet: production MAE
  improvement of **≥ 10%** over the PPG baseline (today 8%), round-point rank ρ **≥ 0.65**,
  and p10/p90 intervals whose empirical coverage is within ±5 points of nominal.
- Give the strategy layer an objective that can actually beat greedy-VOR: joint,
  correlation-aware roster valuation with a variance term informed by standings position.
- Build the evaluation machinery to *prove* all of the above with confidence intervals, and
  to reject changes that don't — before any modeling story lands.
- Keep everything reproducible and honest: frozen champion reports, seeds, manifests,
  `EVIDENCE_PASS.json` provenance, reported misses.

---

## User Stories (prioritized; implement in order)

### US-501: Champion/challenger evaluation harness with statistical power
**Description:** As the tool owner, I want every proposed model change measured against the
frozen committed baseline with confidence intervals and decision-level metrics, so that "it
got better" is a fact, not an impression. Today's 2023–25 backtest (36 drafts, 64 rollouts,
1 draft per slot) cannot distinguish a 1-point edge; oracle vs greedy-VOR differs by 0.2
points with no interval reported.

**Acceptance Criteria:**
- [ ] `oracle evaluate --challenger <artifact-or-config> --champion <committed-run>` replays the same seasons/rounds/seats with **paired** seeds and reports, for every metric, the difference and a 95% paired-bootstrap interval (resampling drafts)
- [ ] Backtest power raised to ≥ 8 drafts per (round, slot) and ≥ 200 rollouts per pick for the evaluation profile (a documented `--profile quick|evidence` switch keeps the fast path)
- [ ] New decision-level metrics per draft: **decision regret** vs the hindsight-optimal legal roster, and **rank of the oracle roster among the four seats**; both appear in `report.md` with intervals
- [ ] New league-outcome metric: for each replayed season-league, whether the oracle's mean seat wins the season (sum of rounds) and whether its best seat ≥ league best per round — reported as the fractions this PRD's goals cite (today 2/4 and 7/12), so improvements are measured in the owner's units
- [ ] Champion reports are frozen: the harness reads the committed run's manifest sha and refuses to compare against a dirty or unpinned champion
- [ ] Skater/team quantile calibration report: empirical coverage of p10/p90 and reliability curves for `p_series_win`, added to every projection evaluation
- [ ] Documented in `ml/README.md`; the honesty rule (SPEC §7) restated: a challenger that loses is reported with its interval and not adopted
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

### US-502: Purchased odds history — closing lines for every playoff game since the 2020 bubble
**Description:** As the tool owner, I want real market probabilities for every playoff game
The Odds API can serve, because the market is the sharpest public estimate and today's
archive covers **zero** 2023–2025 playoff series and only 14 in 2026. Decision (see
Decisions §1): The Odds API historical endpoint, featured markets only (`h2h`, `spreads`,
`totals`), regions `us` + `eu` (the latter for Pinnacle's sharp line), one snapshot per
distinct game start time, postseasons 2020 (the August–September bubble, inside the June 6,
2020 history floor) through 2026. No series-winner market exists on the API, so the
pre-series benchmark stays the game-1 line through the simulator.

**Acceptance Criteria:**
- [ ] A committed fetch script `ml/data/raw/odds-archive/the-odds-api-history/fetch_odds_history.py` reads game start times from the committed NHL archive, requests the historical snapshot immediately preceding each playoff game start (2020–2026), and stores each raw response gzipped with its snapshot timestamp; `PROVENANCE.md` documents endpoint, parameters, plan used, credits spent (formula: 10 × markets × regions per snapshot), and any gaps — run from the owner's machine (sandboxes cannot reach the API); key from `ODDS_API_KEY`, never committed
- [ ] **Encrypted at rest (terms compliance).** The Odds API's terms forbid redistributing its data as downloadable files, and this repo is public, so no Odds API data is ever committed in the clear: raw snapshots, the index and the flat lines extraction are bundled per season and encrypted with AES-256-GCM (Python `cryptography`, 32-byte key, random 12-byte nonce prefixed to each ciphertext) into `<season>.tar.enc`; only ciphertext, `PROVENANCE.md` (with sha256 of each ciphertext and of the plaintext tarball), and a README explaining why the files are opaque are committed. A directory `.gitignore` blocks `plain/`, `*.json.gz`, `*.csv.gz` so plaintext can never be committed by accident
- [ ] Key contract: the key lives in `ml/.env` as `ODDS_ARCHIVE_KEY` (urlsafe-base64 of 32 bytes), in the owner's password manager, and as an environment secret of the Claude Code environment that runs Ralph and evidence regeneration; `oracle odds` decrypts in memory when the key is present and otherwise runs the stat-only path exactly as today (SPEC §5); a missing or wrong key produces one clear message, never a traceback. Tests use synthetic fixtures only — no real Odds API data appears in `ml/tests/`
- [ ] Regular-season coverage for the same seasons: one `h2h`-only snapshot per game day (taken 60 minutes before that day's first game, regions `us,eu`) so the game-win model's market feature has lines for 2020-21..2025-26 instead of only the SBR 2017-2022 and ESPN 2025-26 windows; stored and indexed the same way as the playoff snapshots
- [ ] A **probe step** runs first (one request per market type for one game) and writes the observed market list to PROVENANCE so the absence of a series market is recorded as observed, not assumed
- [ ] Budget guard: the script computes the credit estimate before fetching and refuses to exceed a `--max-credits` argument (default 90,000, sized to the 100K plan)
- [ ] Parser emits rows into the existing `odds_by_source.parquet` schema with `source="the_odds_api"` and per-book columns preserved; de-vigged with the two-sided method (never favorite-only); a documented consensus (median across books, Pinnacle-preferred when present); `consolidate_odds` prefers it over SBR/Kaggle where both exist and records the choice
- [ ] Market-aware backtest track (Track 2) now scores every 2020–2026 series (**≥ 90**, was 14) against the pre-series benchmark
- [ ] Coverage tables in the odds CLI and game-win report show per-season counts for the new source; all existing odds tests pass unchanged
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

### US-503: Extend the NHL archive back to 2007-08 (with era guardrails)
**Description:** As the tool owner, I want more playoff series in training (today 11 seasons ≈
165 series) because the series model's held-out sample is what makes its calibration noisy.
The NHL stats REST API serves seasons back to 2007-08 with the same schema, and MoneyPuck shot
data (US-504) begins in 2007-08 too, so the shot-quality features cover the whole span. Decision (Decisions §4): fetch to 2007-08, add an era indicator, define seeding by
regular-season points, and ablate.

**Acceptance Criteria:**
- [ ] `fetch_nhl.py` `SEASONS` extended to 2007-08; new team/skater/bios files and brackets committed with provenance; `normalize` handles the older rows (team relocations/renames — ATL→WPG, PHX→ARI→UTA — mapped via `resolve_team_id`)
- [ ] "Higher seed" is defined by regular-season points (tie-broken by regulation wins) everywhere, not by bracket position, so the 2013-14 bracket-format change does not change the feature's meaning; a test covers a pre-2014 and a post-2014 series
- [ ] A season-level `era` indicator and per-season goals-per-game normalization are available as features
- [ ] Ablation under US-501: series model trained with vs without 2007–2013; the report shows held-out calibration and Brier for both and states which is adopted (older seasons are dropped if they hurt, and the report says so)
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

### US-504: Goaltending, shot-quality and deployment data — MoneyPuck and NHL shift/TOI ingestion
**Description:** As the tool owner, I want goalie-level and shot-quality data because the
team slot is priced from team win% and box-score save% today, and "who is in net and how
good are they really" is the information the current features cannot see.

**Acceptance Criteria:**
- [ ] MoneyPuck season summaries (skaters, goalies, teams, lines; regular and playoffs; 2008-09 onward) AND the raw per-season shot archives (`shots_<year>.zip`, 2007-08 onward, committed as the original downloaded bytes with sha256 recorded — plain git, no LFS; any file over 45 MB is split into gzipped parts with reassembly documented) live under `ml/data/raw/moneypuck/` with `PROVENANCE.md` (source URLs, fetch date, attribution note, checksums); a committed `aggregate_shots.py` derives per-game team xG for/against, per-game skater ixG, and per-game goalie shots-faced / xG-faced / GSAx / starter-flag tables from the shots files, and the pipeline normalizes those into `data/normalized/{skater_xg,goalie_xg,team_xg}.parquet` keyed on NHL ids via `entity_match`
- [ ] A test recomputes the sha256 of each committed shots archive against PROVENANCE and re-derives one season's aggregates from it, proving the committed aggregates are reproducible from the committed raw bytes
- [ ] Deployment data comes from the NHL API, not NaturalStatTrick (Decisions §7): per-game skater TOI by strength (`skater/timeonice` and `skater/powerplay` REST reports, 2007-08 onward) committed under `ml/data/raw/nhl-archive/`, and per-game shift charts (`shiftcharts` REST endpoint; the HTML TOI reports for seasons it does not serve) committed under `ml/data/raw/nhl-shifts/` with a committed `derive_deployment.py` producing per-game forward-line / D-pair 5v5 TOI, PP-unit membership and TOI (PP1 = the five skaters with the most PP TOI that game), and per-skater 5v5 / PP / PK TOI; on-ice xG per skater comes from joining shifts to MoneyPuck shots by game clock; the pipeline normalizes these into `data/normalized/{skater_toi,lines,pp_units,skater_onice_xg}.parquet`; a test re-derives one season's tables from the committed shifts and checks byte identity; seasons the API does not serve are listed in PROVENANCE, never imputed; shift-derived per-skater TOI is reconciled against the REST `skater-toi` totals for the same (gameId, playerId): rows differing by more than 60 s carry a `toi_conflict` flag, per-skater TOI features take the REST value, and shifts supply composition only (the 2019-20 REST shift charts contain corrupt over-long shifts for a few skaters per affected game, and a handful of 2007-08 REST totals are exactly half the HTML report); the 2007-08..2009-10 HTML seasons must include regular-season overtime (`OT`-labelled) and playoff periods beyond 5 before this story starts
- [ ] Starting-goalie identity per game derived from the NHL archive (the goalie who faced the first shot / played ≥ 30 min), giving each team a **starter GSAx / sv%** and **backup GSAx / sv%** time series with as-of discipline
- [ ] Leakage tests extended: every new table has a `game_date`/`as_of_date` and `features/leakage.py` checks it against round cutoffs
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

### US-505: Team-strength and goalie-slot model overhaul
**Description:** As the tool owner, I want the team/goalie slot — the round's largest single
lever — priced from a model that beats the market's pre-series line, replacing today's
box-score Elo logistic (Brier 0.2427; toss-up bin observed 0.214 vs predicted 0.517) and
no-skill shutout model.

**Acceptance Criteria:**
- [ ] A **goals model** replaces the separate win/shutout classifiers as a challenger: per-game expected goals for/against via a regularized bivariate-Poisson or Dixon–Coles-style model with team attack/defence strengths (xG-informed from US-504), starting-goalie GSAx, home ice, rest days, and playoff indicator; P(win), P(shutout win) and margin all derive from the same score distribution, so they are coherent by construction
- [ ] Team strength carries a **hierarchical prior across seasons** (last season's rating shrunk toward the mean) and an xG-based Elo variant is evaluated against the current goals-based Elo; the better one on the held-out protocol is kept, both reported
- [ ] Series-winner probabilities are **post-hoc calibrated** on held-out seasons (isotonic or Platt, fit on validation years only) and the 0.40–0.60 reliability bin must land within ±0.10 of observed; the series-length distribution's 7-game share must be within ±5 points of observed on held-out seasons
- [ ] Market as a feature: when US-502 lines exist for a series' game 1, the model may consume the de-vigged consensus as a feature with a documented shrinkage weight fit on validation years; the stat-only path remains first-class and is reported alongside
- [ ] Held-out targets (reported honestly whether met or not): series Brier ≤ the pre-series market benchmark on the US-502 set; pooled team goalie-slot rank ρ ≥ 0.50 (today 0.276); shutout Brier strictly below the base rate
- [ ] `p_series_win`, `E[wins]`, `E[shutout wins]` and `e_goalie_points` in the projection artifact come from the adopted model; the committed 2026-r* fixtures and both backtests are regenerated in one evidence pass (US-406 pattern) with the champion/challenger report attached
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

### US-506: Joint Monte Carlo roster valuation (correlated outcomes)
**Description:** As the tool owner, I want roster value computed from **one shared simulation
of the playoff round** rather than independent per-player draws, because a roster stacked
on one team lives and dies with that team's series — exactly the effect that made Carolina's
skaters plus Carolina's goalie slot worth 74 points in the 2026 final while the oracle's
diversified roster scored 33. Land this only after US-505 has shipped and been evaluated on
its own, so a goalie-model improvement is never confounded with an optimizer change.

**Acceptance Criteria:**
- [ ] The projection artifact ships, alongside the marginal `skaters`/`teams` tables, a seeded **scenario tensor**: for N ≥ 2,000 draws of every live series (length, winner, per-game winners/shutouts, each skater's games played and points), stored compactly (Parquet/NumPy) with the manifest recording N and seed; artifact size stays under 50 MB per round
- [ ] `optimize/` values any roster as the empirical distribution of its total points over the shared draws (mean, p10, p90, P(beats a given total)); the rules engine scores each draw; the marginal `expected_points` of a single player is unchanged (regression test to 1e-6)
- [ ] VOR, greedy-VOR, and the rollout recommender consume roster-level values from the tensor; `recommend` shows for each candidate the change in roster mean **and** in roster p10/p90
- [ ] Combined R3+R4 event handled inside the same draws (advance-or-not per team), replacing the `p_advance × e_goalie_r4` fold with the exact simulated fold; a test shows the two agree in expectation to 1e-3
- [ ] Backtest strategy `oracle_joint` (roster-mean objective on the tensor) is evaluated against `oracle`, `greedy_vor`, `one_step` under US-501 with intervals; the report states which wins
- [ ] Draft-time `recommend` still completes in under 10 s at full depth on the 2026-r1 fixture
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

### US-507: Skater production model — usage, quality, matchup, and multi-season priors
**Description:** As the tool owner, I want the skater model to know how a player is
*deployed* and *against whom*, not just his box score, because its 8% edge over "sort by
PPG" is the sign of a model that has learned almost nothing beyond the rate it was given.

**Acceptance Criteria:**
- [ ] New as-of features from US-504: ixG/60, on-ice xGF%, PP1 share and PP TOI/60, even-strength TOI/60 trend (last 10 vs season), line assignment, shooting-talent shrinkage (career sh% vs league), plus **matchup** features for the upcoming series: opponent xGA/60, opponent penalty rate, opponent starting-goalie GSAx
- [ ] **Multi-season player prior**: shrinkage toward the player's own previous seasons (weighted) before the position+team mean, replacing the single-season `n/(n+10)` shrink; the shrink strength is fit on validation years
- [ ] Model family search under one harness: current LightGBM, CatBoost, a Bayesian hierarchical Poisson/negative-binomial rate model (player, team, opponent effects), and a small MLP; each evaluated on the held-out protocol with the same features; the champion is chosen on validation, reported on test, and the report shows all rows
- [ ] Per-game distribution: a negative-binomial (over-dispersed) alternative to the current Poisson is evaluated for the quantile Monte Carlo; p10/p90 empirical coverage must be within ±5 points of nominal
- [ ] Held-out targets (honest): production MAE ≥ 10% better than the PPG baseline; round-point rank ρ ≥ 0.65; both per-season rows shown
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

### US-508: Nested temporal cross-validation and hyper-parameter search
**Description:** As the tool owner, I want model hyper-parameters chosen by rolling-origin
validation across several seasons rather than a single validation year, so the family
choices made in US-505 and US-507 are not fit to 2024's idiosyncrasies.

**Acceptance Criteria:**
- [ ] A `tuning/` module runs rolling-origin CV (train ≤ t−2, validate t−1, for t across four seasons) for every model with a bounded search budget and a fixed seed; the chosen configuration and the full search table are written to the model manifest
- [ ] Test-season metrics are computed once, after selection, and never used for selection (guarded by a test that the tuner cannot see test rows)
- [ ] US-505 and US-507 champions are re-selected under the nested protocol; the report states whether the choice changed
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

### US-509: Conformal prediction intervals for skater round points
**Description:** As the tool owner, I want distribution-free intervals with guaranteed
coverage on held-out data, replacing Monte-Carlo quantiles whose coverage was never verified
before US-501.

**Acceptance Criteria:**
- [ ] Split-conformal (or conformalized quantile regression) intervals fit on validation years; held-out p10/p90 coverage within ±3 points of nominal, reported per season; the cheat sheet shows the conformal band
- [ ] A test asserts the calibrator never sees test-season rows
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

### US-510: Skater availability inside a round from absence spells and lineup data
**Description:** As the tool owner, I want the probability a skater dresses for each game of
the series (healthy scratch, in-series injury) modeled from the archive's absence spells and
the per-game dressed lineups in the NHL shift charts (US-504), not assumed to be 1.0.

**Acceptance Criteria:**
- [ ] Per-skater per-game dress probability estimated as-of the round; held-out calibration reported; feeds the US-506 tensor
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

### US-511: Rest, travel, and schedule effects
**Description:** As the tool owner, I want per-game features for days of rest, back-to-back
games, time-zone travel, and series-start rest differential, which are known small but real
effects the model currently ignores.

**Acceptance Criteria:**
- [ ] Features derived from the archive schedule; ablation under US-501 reported; kept only if the held-out Brier improves
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

### US-512: In-series dynamics — goalie changes, injuries during the series, venue reality
**Description:** As the tool owner, I want the series simulator to model what changes inside a
series (a pulled starter, an injured star, the actual home/away schedule from the bracket)
instead of a fixed per-game probability.

**Acceptance Criteria:**
- [ ] Per-game win probability conditions on the actual game venue and rest days; goalie-change hazard estimated from the archive (starter replaced after N goals or losses); evaluated on held-out series length and winner metrics against the static model
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

### US-513: Injuries and starting-goalie probability in the live path, validated on labeled data
**Description:** As the tool owner, I want the one information edge humans on a phone don't
have — structured injury status, expected return, and the likely starting goalie — to
demonstrably move draft-night projections and to be calibrated on real labels. Today the
backtests run with the injury haircut as a no-op and the return-time model is calibrated on
absence spells, not labeled injuries. Decision (Decisions §2): starters are **modeled as a
probability** with the manual override as final authority; the NHL API's own pre-game lineup
is read when it has posted; DailyFaceoff is **not** scraped.

**Acceptance Criteria:**
- [ ] The Dec 2025–Jun 2026 as-of-game `injuries` blocks already committed under `odds-archive/espn-2025-26-completion/raw/summary/` become the **labeled validation slice** for the return-time model: predicted vs observed P(available for game k) reported per status, and the status→mean-absence map refit on it (documented before/after)
- [ ] A **starter probability model** per team per game 1: share of starts over the last 20 games, playoff-start history, back-to-back pattern, and ESPN injury status, yielding P(starter = A) and a blended starter GSAx for US-505; calibration reported on the archive's observed starters
- [ ] When the NHL API's pre-game lineup (gamecenter landing/boxscore) has posted for game 1 at artifact-build time, it pins the starter; otherwise the cheat sheet flags "starter unconfirmed" with the modeled probability; the injuries override YAML can pin a starter (`starting_goalie:` entry) as final authority
- [ ] The 2026 backtest replays with **as-of injury statuses** reconstructed from the labeled slice (leakage-guarded by date), so the injury haircut and IR valuation are exercised in evidence for the first time; the report states the marginal effect on oracle points
- [ ] `oracle project` prints an injury-impact summary (players discounted, expected points removed, unresolved ids, starter status per team) and the cheat sheet's Status column shows return-game expectations
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

### US-514: Standings-aware objective — variance as a lever in rounds 2–4
**Description:** As the tool owner, I want the recommender to choose *how much variance to
take* based on my standing, because rounds 2–4 draft worst-to-best and the season is won on
cumulative points: a manager trailing by 20 should prefer high-ceiling stacks; a manager
leading should protect the floor. Today every seat maximizes expected points. Decision
(Decisions §3): round 1 always uses `mean`; for rounds 2–4 a variance-aware objective becomes
the default only if its paired-bootstrap interval on season wins excludes zero, otherwise
`mean` stays default with the alternative's pick shown.

**Acceptance Criteria:**
- [ ] The recommender accepts the current cumulative standings (`--standings ben=120,judah=104,...` or from the session log) and an objective among `mean`, `p_win_season` (probability the owner finishes first over the remaining rounds, estimated on the US-506 scenario tensor), and `mean_minus_lambda_var`
- [ ] Backtest strategies `oracle_pwin` and `oracle_meanvar` replayed with the real standings entering each round; US-501 reports season-win fraction and decision regret against `oracle` and `greedy_vor` with intervals
- [ ] Default rule implemented and tested: round 1 → `mean`; rounds 2–4 → the variance-aware objective only if its adoption is recorded in the evidence report with an interval excluding zero, else `mean`
- [ ] `recommend` always shows, for each candidate, the roster mean/p10/p90 change **and** the P(win season) change, and names the objective in use, so the owner can override consciously
- [ ] If no variance-aware objective beats `mean` on season wins with the interval excluding zero, the report says so and `mean` stays default (honesty rule)
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

### US-515: Ensembling and stacking across model families
**Description:** As the tool owner, I want the per-game and skater production predictions to
combine the best families found in US-505/US-507 (stat-only, market-aware, Bayesian,
boosted) with weights fit on validation years.

**Acceptance Criteria:**
- [ ] Stacked models evaluated under the held-out protocol; adopted only if the interval excludes zero; weights and component metrics recorded in the manifest
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

### US-516: Opponent model refresh (survival probabilities, not league exploitation)
**Description:** As the tool owner, I want survival probabilities (P(player still available at
my next pick)) to be accurate, which needs a better opponent model even though exploiting
specific managers is not this PRD's goal.

**Acceptance Criteria:**
- [ ] Features added: position-run detection (recent picks at a position), roster need, public ADP-style rank from the cheat sheet, app-era true pick order weighted higher; leave-one-season-out membership accuracy and per-pick top-3 reported; adopted only if they improve on the committed 0.287/0.341/0.287 and 0.208
- [ ] Survival calibration: predicted vs observed P(available at next turn) on replayed drafts within ±5 points
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

### US-517: Explainability in the cheat sheet
**Description:** As the tool owner, I want to see *why* a player is ranked where he is (top
feature contributions, matchup, deployment) so I can sanity-check in a 60-second pick window.

**Acceptance Criteria:**
- [ ] SHAP (or exact contributions for linear/Bayesian models) computed at artifact build time; the cheat sheet and `recommend` show the top three drivers per player as short phrases; no draft-time model dependency (values precomputed into the artifact; the US-208 import guard still passes)
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

### US-518: Small neural sequence model for per-game production (exploratory)
**Description:** As the tool owner, I want to know whether a compact sequence model over a
skater's game log beats the tabular models, since the stack now allows one. With ~350
skater-rounds per season this is the story most likely to produce an honest negative
result; that result is still worth recording.

**Acceptance Criteria:**
- [ ] A CPU-trainable GRU/temporal-conv model over the last 40 games per skater, trained under the same protocol and seeds; adopted only if it beats the US-507 champion with the interval excluding zero; otherwise the report records the negative result and the model is not shipped
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

### US-519: Drift monitoring and season-start retrain command
**Description:** As the tool owner, I want a single command that refreshes all data, retrains
every model, regenerates evidence, and diffs every metric against last season's champion,
so the tool is re-validated each April in minutes.

**Acceptance Criteria:**
- [ ] `oracle season-start --season YYYY` runs the fetches (with clear instructions for the owner-machine steps the sandbox cannot do), normalize, train, evaluate, and writes a drift report (feature distributions, metric deltas vs the champion) to `ml/artifacts/drift/`
- [ ] `DRAFT_NIGHT.md`'s "once per season" section is replaced by this command
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

### US-520: Final evidence pass and v2 verdict
**Description:** As the tool owner, I want one regenerated set of committed evidence at a
clean HEAD after everything above lands, with a plain-language verdict against this PRD's
goals, so I know before next spring whether v2 is a real step up.

**Acceptance Criteria:**
- [ ] All model reports, both backtests, the 2026-r* fixtures and `EVIDENCE_PASS.json` regenerated in one pass at a clean HEAD (US-406 pattern), with the champion/challenger comparison to the pre-v2 `main` artifacts embedded in each report
- [ ] `ml/EVALUATION.md` (new) summarizes: replayed season-league wins (target ≥ 3/4), best-seat ≥ league-best rounds (target ≥ 9/12), team ρ, series Brier vs market, skater MAE/ρ, quantile coverage — each with the interval and a met / not-met verdict, misses stated plainly
- [ ] `DRAFT_NIGHT.md` and `README.md` updated for the new artifact contents (scenario tensor, objectives, injury and starter summary, drivers) and the "Honest expectations" section rewritten from the new numbers
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

---

## Functional Requirements

### Evaluation (applies to every story)
- FR-1: Every model change must be evaluated as a challenger against the frozen committed champion using the leave-future-out protocol over 2023–2026 with per-season rows and pooled metrics.
- FR-2: Every reported difference between strategies or models must carry a 95% paired-bootstrap interval; a change is adopted only if the interval excludes zero in the intended direction, or the story explicitly documents adoption for another reason.
- FR-3: Backtests used as evidence must run ≥ 8 drafts per (round, slot) and ≥ 200 rollouts per pick; the quick profile may run less and must say so in its report.
- FR-4: Reports must include decision regret, seat rank, season-win fraction, and best-seat-vs-league-best fraction alongside mean points and win rate.
- FR-5: Quantile outputs (p10/p50/p90) must have their empirical coverage reported on held-out data.
- FR-6: Misses are reported with the honest number; baselines, splits, seeds and held-out sets are never changed to manufacture a pass (SPEC §7 unchanged).

### Data
- FR-7: New external sources (The Odds API history, the extended NHL archive incl. shift charts and TOI reports, MoneyPuck, NHL pre-game lineups) are fetched by committed scripts run from the owner's machine, committed as snapshots with `PROVENANCE.md`, and parsed by tested code; the pipeline never depends on live availability of these sites.
- FR-8: Every new table carries an as-of date and is covered by the leakage tests.
- FR-9: Paid API keys live in `ml/.env` (gitignored); fetch scripts fail loudly without them; fetch cost per run is estimated before fetching, capped by argument, and recorded in PROVENANCE.
- FR-9a: Data whose license forbids redistribution (The Odds API) is committed only as AES-256-GCM ciphertext; the decryption key is never committed, the pipeline degrades to stat-only without it, and derived per-game market probabilities are likewise not committed in the clear.
- FR-10: The pre-series market benchmark is the game-1 de-vigged consensus line pushed through the series simulator; no series-winner market is assumed to exist.

### Models
- FR-11: The team-strength model must produce P(win), P(shutout win) and expected margin from one coherent score distribution.
- FR-12: Series-winner probabilities must be calibrated post hoc on validation years; reliability bins are reported for every held-out set.
- FR-13: Skater projections must decompose into rate × games as today, with the rate model informed by usage, shot quality, matchup and multi-season priors.
- FR-14: Roster value must be computable from a shared scenario tensor so correlated outcomes are priced; marginal player projections remain available and unchanged.
- FR-15: Any wider-stack model (Bayesian, neural, CatBoost) must be CPU-trainable within the 15-minute batch budget on the owner's machine and seeded; GPUs are optional, never required.
- FR-16: Starting goalies are modeled as probabilities and pinned only by a posted NHL lineup or the override file; no third-party lineup site is scraped.

### Optimizer and CLI
- FR-17: The recommender supports `mean`, `p_win_season`, and `mean_minus_lambda_var` objectives with standings input; round 1 uses `mean`; rounds 2–4 default per the evidence rule in US-514.
- FR-18: `recommend` shows roster mean and p10/p90 change and P(win season) change per candidate, and the top drivers behind each projection.
- FR-19: Draft-time commands remain offline and under the existing latency budgets (10 s full depth, 5 s depth 1) with the scenario tensor loaded, and import none of the training stack.

### Outputs
- FR-20: One evidence pass regenerates all committed artifacts together with shared provenance (`EVIDENCE_PASS.json`) after each story that changes committed evidence, and once more at the end (US-520).
- FR-21: `ml/EVALUATION.md` states the PRD's success metrics with intervals and met/not-met verdicts.

## Non-Goals (Out of Scope)

- **No league-specific exploitation as a goal.** Opponent tendencies matter only for survival probabilities (US-516); we do not tune projections to beat ben, judah, kyle or levi specifically.
- **No app integration, no serving, no UI** — the tool stays an offline batch pipeline plus local CLI.
- **No in-round roster management** beyond IR draft valuation (mid-round activation alerts remain a future idea).
- **No trading of honesty for headline numbers.** If a target is missed, it stays unmet in the evidence.
- **No live scraping at draft time.** Everything the CLI needs is in the artifact; live sources are used only when building it.
- **No Odds API data in the clear, ever** — raw snapshots, indexes, flat lines, and derived per-game market probabilities are encrypted or not committed; only aggregate metrics in reports are public.
- **No scraping of DailyFaceoff or similar lineup sites.** Starters are modeled, read from the NHL API when posted, or pinned by hand.
- **No hand-maintained feature spreadsheets.** Every feature has a scripted, reproducible source.

## Design Considerations

- The scenario tensor is the new contract between projection and optimization; keep the marginal tables so the cheat sheet and existing tests stay valid.
- Cheat sheet additions (drivers, bands, injury/starter status) must stay readable on a phone; one extra column at most, details in `recommend`.
- The champion/challenger report is the *first* thing a reader sees in every model report — the verdict, the interval, then the tables.

## Technical Considerations

- **Small data is still small data.** Bayesian hierarchical models and multi-season priors exist precisely because ~165 series (≈255 after US-503) and ~350 skater-rounds per season overfit anything flexible; every flexible model must be beaten by (or beat) the regularized baseline on held-out years, and the report says which.
- **Stack widening** (SPEC §3 amendment): add `catboost`, a probabilistic-programming library (`numpyro` or `pymc`), `mapie` (conformal), and optionally `torch` (CPU) as extras; keep the `uv` lockfile, seeds, `mypy --strict`, ruff; the draft-time CLI must still import none of them (US-208 guard extended).
- **Sandbox limits.** The repo's cloud sandboxes cannot reach the NHL API, ESPN, MoneyPuck or The Odds API (confirmed again while writing this PRD); every fetch story specifies the owner-machine steps and commits snapshots, as the v1 data foundation did.
- **Odds cost model.** The Odds API bills historical snapshots at 10 × (markets × regions) credits each; a snapshot per playoff game start (≈ 630 games, 2020–2026) with `h2h,spreads,totals` over `us,eu` is ≈ 630 × 10 × 3 × 2 ≈ 38,000 credits — inside the 100K plan (~$59 for one month) with headroom for the probe and one re-pull. Data exists from June 6, 2020, which includes the 2020 bubble playoffs; additional (period/prop) markets only from May 2023 and are not needed.
- **Encrypted archive mechanics.** One tiny module (`ingest/sealed.py`) wraps `cryptography.hazmat.primitives.ciphers.aead.AESGCM`: `seal(bytes, key) -> nonce || ciphertext` and `open(blob, key)`; per-season tarballs keep file counts small and diffs reviewable (a re-fetch changes one file). Chosen over `age` because every machine that builds artifacts (the owner's Windows box, the cloud sandbox, CI) must decrypt in-process without installing a binary; `cryptography` ships wheels for all of them. Add `cryptography` to `ml/pyproject.toml` in US-502.
- **Correlation vs speed.** A 2,000-draw tensor over ~450 skaters × 7 games is ~6M cells per round; store as compact integers/float16 and precompute per-player cumulative points per draw so `recommend` reduces to sums over selected columns.
- **Calibration set discipline.** Post-hoc calibrators (isotonic/Platt/conformal) fit on validation years only; a test asserts they never see test rows.
- **Era handling.** Pre-2014 seasons used 1–8 conference seeding; defining "higher seed" by regular-season points keeps the feature stable across formats. Playoff overtime has always been 5-on-5 and shootouts never occur in the playoffs, so the 2015 regular-season OT change is irrelevant here.
- **Provenance.** Continue the `git_sha`/`git_dirty`/`EVIDENCE_PASS.json` pattern; the champion is identified by that sha.

## Success Metrics

Measured by US-501 on 2023–2026, challenger (post-v2 HEAD) vs champion (`main` at this PRD's
merge), 95% paired-bootstrap intervals; each row is met/not-met in `ml/EVALUATION.md`.

| Metric | Champion today | Target |
| --- | --- | --- |
| Replayed season-leagues won by the oracle's mean seat | 2 of 4 | ≥ 3 of 4 |
| Rounds where the oracle's best seat ≥ league best | 7 of 12 | ≥ 9 of 12 |
| Oracle vs greedy-VOR mean points | −0.20 (no interval) | > 0 with interval excluding zero, or an honest "tie" |
| Pooled team goalie-slot rank ρ | 0.276 | ≥ 0.50 |
| Goalie-slot MAE (points/round) | 2.8–3.2 | < 2.5 |
| Series Brier vs pre-series market, 2020–2026 (≥ 90 series) | model 0.224 vs market 0.234 on 14 | ≤ market |
| Series 0.40–0.60 reliability bin (pred vs obs) | 0.517 vs 0.214 | within ±0.10 |
| Shutout Brier vs base rate | 0.0923 vs 0.0921 (no skill) | strictly below base rate |
| Skater production MAE gain over PPG baseline | 8% | ≥ 10% |
| Skater round-point rank ρ | 0.593 | ≥ 0.65 |
| p10/p90 empirical coverage | unmeasured | within ±5 points of nominal |

## Decisions (resolved open questions)

1. **Odds history — what to buy and how far back.** The Odds API's historical endpoint has
   featured markets (`h2h`, `spreads`, `totals`) from June 6, 2020, and additional markets
   only from May 2023; its `outrights` are Stanley Cup futures — there is **no NHL
   series-winner market**, so the pre-series benchmark remains the game-1 line through the
   simulator (already implemented). Decision: one month of the **100K plan**, regions
   `us,eu`, markets `h2h,spreads,totals`, one snapshot per playoff game start, postseasons
   2020–2026, with a probe step and a credit cap (US-502).
2. **Starting-goalie confirmations.** Confirmations post hours before game 1 — after the
   draft in practice — and scraping DailyFaceoff is fragile and terms-questionable.
   Decision: model the starter as a probability, read the NHL API's pre-game lineup when it
   has posted, and let the override YAML pin a starter the owner sees announced (US-513).
   No third-party lineup scraping.
3. **Objective default.** Round 1 uses `mean` (no standings exist). For rounds 2–4,
   `p_win_season` (or `mean_minus_lambda_var`) becomes the default only if its
   paired-bootstrap interval on replayed season wins excludes zero; otherwise `mean` stays
   default and `recommend` shows the alternative's pick and P(win season) delta (US-514).
4. **Archive depth.** Extend to 2007-08 (the floor of MoneyPuck shot data), add
   an era indicator, define seeding by regular-season points, and ablate 2007–2013 under the
   harness; drop them if they hurt and say so (US-503).
5. **Odds API data at rest.** The Odds API's terms prohibit redistributing its data as downloadable files and this repo is public, so the archive is committed only as AES-256-GCM ciphertext (Python `cryptography`; key `ODDS_ARCHIVE_KEY` held by the owner and injected as an environment secret where Ralph runs). The owner will confirm the arrangement with The Odds API by email; the stat-only path remains first-class so the tool works without the key.
6. **Scope.** Everything is committed work in one ordered list; there is no deferred
   backlog. Data acquisition stories (US-502..US-504) sit early because every model story
   downstream consumes them; US-506 (joint tensor) deliberately follows US-505 so the goalie
   model and the optimizer change are evaluated separately.
7. **NaturalStatTrick dropped.** The first compliant request (project User-Agent, 5 s
   spacing) received a Cloudflare challenge (HTTP 403; see
   `ml/data/raw/naturalstattrick/FETCH_FAILURE_REPORT.md`). The site owner has chosen to
   block non-browser clients, and we do not impersonate browsers, solve challenges or rotate
   IPs to get around that. Decision: every deployment feature NST would have supplied (line
   combinations, PP-unit membership, TOI by strength, on-ice xG) is derived instead from the
   NHL API's own shift charts and TOI reports joined to MoneyPuck shots, the primary data NST
   itself is built from (US-504). The failure report stays committed as the record; no NST
   data is used anywhere.
