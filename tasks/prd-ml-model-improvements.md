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
| Opponent model | Membership 0.287/0.341/0.287 vs greedy 0.231/0.216/0.292; per-pick top-1 0.113 | Weak, but the affinity coefficient (+3.0) is real. Not the focus of this PRD (league-agnostic accuracy is). |

This PRD is a **research roadmap in two phases**. Phase 1 attacks the components whose
error dominates roster outcomes — the goalie/team slot, joint (correlated) roster valuation,
skater usage features, market and injury signal actually reaching the draft-time path — and
**first** upgrades the evaluation harness so a real improvement can be told from noise.
Phase 2 is the backlog of further methodological improvements, each gated by the same
harness. The stack is widened (Bayesian hierarchical models, gradient-boosting variants,
conformal/quantile methods, even small neural models where they earn their keep), but the
small-data discipline and the honesty rules of `ml/SPEC.md` §7 stay in force: every
"improvement" is a *challenger* measured against the frozen committed *champion*, and a
miss is reported, never tuned away.

**Owner decisions incorporated (clarifying questions):** the goal is the best possible
*calibrated, league-agnostic* projections (1B); all data sources are in scope including paid
API tiers (2C); the document is a prioritized Phase 1 plus a Phase 2 backlog (3C); success
is judged on replayed-season outcomes (4A); the pinned stack may be widened (5B).

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

## Goals

- Raise the oracle's replayed-season record from **2 of 4 wins to at least 3 of 4** on
  2024–2026 (Gemmell Cup ×3, Press Play-offs ×1), and the rounds where its best seat matches
  or beats the league's best manager from **7 of 12 to at least 9 of 12**.
- Make the goalie/team slot trustworthy: pooled team rank correlation from 0.276 to **≥ 0.50**,
  goalie-slot MAE below 2.5 points, series-winner Brier at or below the game-1 market line
  on **≥ 40 series** with purchased odds history.
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

## User Stories — Phase 1 (prioritized; implement in order)

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

### US-502: Purchased odds history — series prices and closing lines for every playoff since 2020
**Description:** As the tool owner, I want real market probabilities for enough playoff
series to train and validate the series model against them, because the market is the
sharpest public estimate and today's archive covers **zero** 2023–2025 playoff series and only
14 in 2026. The Odds API historical tier (paid) serves per-day snapshots of `h2h` game lines
and, where offered, series (`outrights`) prices.

**Acceptance Criteria:**
- [ ] `ml/data/raw/odds-archive/the-odds-api-history/` holds committed, gzipped per-day snapshots for every playoff day 2020–2026 (game `h2h` closing lines for all books available; series prices where present), fetched by a committed script with `PROVENANCE.md` documenting endpoints, cost, snapshot times, and gaps — fetched from the owner's machine (this repo's sandboxes cannot reach the API), key from `ODDS_API_KEY`, never committed
- [ ] Parser emits rows into the existing `odds_by_source.parquet` schema with `source="the_odds_api"`, de-vigged with the two-sided method (never favorite-only), consensus across books documented; `consolidate_odds` prefers it over SBR/Kaggle where both exist and records the choice
- [ ] Series prices land in a new `series_odds.parquet` (season, series id, as-of date, P(higher seed wins series) de-vigged)
- [ ] Market-aware backtest track (Track 2) now scores **≥ 40 series** (was 14) and reports the pre-series (game-1 / series-price) benchmark for each
- [ ] Coverage tables in the odds CLI and game-win report show per-season counts for the new source; all existing odds tests pass unchanged
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

### US-503: Goaltending and shot-quality data — MoneyPuck and NaturalStatTrick ingestion
**Description:** As the tool owner, I want goalie-level and shot-quality data because the
team slot is priced from team win% and box-score save% today, and "who is in net and how
good are they really" is the information the current features cannot see.

**Acceptance Criteria:**
- [ ] MoneyPuck season/game CSVs (skaters, goalies, teams: xG for/against, GSAx, high-danger shares, ixG per skater) for all archive seasons are fetched by a committed script into `ml/data/raw/moneypuck/` with `PROVENANCE.md` (license note, fetch date, checksums); normalized into `data/normalized/{skater_xg,goalie_xg,team_xg}.parquet` keyed on NHL ids via `entity_match`
- [ ] NaturalStatTrick line/PP-unit deployment (TOI share by line and PP1/PP2) ingested for the seasons where the site serves it, with a polite rate limit and cached raw HTML/CSV; unmatched players reported loudly, never guessed
- [ ] Starting-goalie identity per game derived from the NHL archive (the goalie who faced the first shot / played ≥ 30 min), giving each team a **starter GSAx / sv%** and **backup GSAx / sv%** time series with as-of discipline
- [ ] Leakage tests extended: every new table has a `game_date`/`as_of_date` and `features/leakage.py` checks it against round cutoffs
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

### US-504: Team-strength and goalie-slot model overhaul
**Description:** As the tool owner, I want the team/goalie slot — the round's largest single
lever — priced from a model that beats the market's pre-series line, replacing today's
box-score Elo logistic (Brier 0.2427; toss-up bin observed 0.214 vs predicted 0.517) and
no-skill shutout model.

**Acceptance Criteria:**
- [ ] A **goals model** replaces the separate win/shutout classifiers as a challenger: per-game expected goals for/against via a regularized bivariate-Poisson or Dixon–Coles-style model with team attack/defence strengths (xG-informed from US-503), starting-goalie GSAx, home ice, rest days, and playoff indicator; P(win), P(shutout win) and margin all derive from the same score distribution, so they are coherent by construction
- [ ] Team strength carries a **hierarchical prior across seasons** (last season's rating shrunk toward the mean) and an xG-based Elo variant is evaluated against the current goals-based Elo; the better one on the held-out protocol is kept, both reported
- [ ] Series-winner probabilities are **post-hoc calibrated** on held-out seasons (isotonic or Platt, fit on validation years only) and the 0.40–0.60 reliability bin must land within ±0.10 of observed; the series-length distribution's 7-game share must be within ±5 points of observed on held-out seasons
- [ ] Market as a feature: when US-502 lines exist for a series' game 1 (or a series price), the model may consume them as a feature with a documented shrinkage weight fit on validation years; the stat-only path remains first-class and is reported alongside
- [ ] Held-out targets (reported honestly whether met or not): series Brier ≤ the pre-series market benchmark on the US-502 set; pooled team goalie-slot rank ρ ≥ 0.50 (today 0.276); shutout Brier strictly below the base rate
- [ ] `p_series_win`, `E[wins]`, `E[shutout wins]` and `e_goalie_points` in the projection artifact come from the adopted model; the committed 2026-r* fixtures and both backtests are regenerated in one evidence pass (US-406 pattern) with the champion/challenger report attached
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

### US-505: Joint Monte Carlo roster valuation (correlated outcomes)
**Description:** As the tool owner, I want roster value computed from **one shared simulation
of the playoff round** rather than independent per-player draws, because a roster stacked
on one team lives and dies with that team's series — exactly the effect that made Carolina's
skaters plus Carolina's goalie slot worth 74 points in the 2026 final while the oracle's
diversified roster scored 33.

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

### US-506: Skater production model — usage, quality, matchup, and multi-season priors
**Description:** As the tool owner, I want the skater model to know how a player is
*deployed* and *against whom*, not just his box score, because its 8% edge over "sort by
PPG" is the sign of a model that has learned almost nothing beyond the rate it was given.

**Acceptance Criteria:**
- [ ] New as-of features from US-503: ixG/60, on-ice xGF%, PP1 share and PP TOI/60, even-strength TOI/60 trend (last 10 vs season), line assignment, shooting-talent shrinkage (career sh% vs league), plus **matchup** features for the upcoming series: opponent xGA/60, opponent penalty rate, opponent starting-goalie GSAx
- [ ] **Multi-season player prior**: shrinkage toward the player's own previous seasons (weighted) before the position+team mean, replacing the single-season `n/(n+10)` shrink; the shrink strength is fit on validation years
- [ ] Model family search under one harness: current LightGBM, CatBoost, a Bayesian hierarchical Poisson/negative-binomial rate model (player, team, opponent effects), and a small MLP; each evaluated on the held-out protocol with the same features; the champion is chosen on validation, reported on test, and the report shows all rows
- [ ] Per-game distribution: a negative-binomial (over-dispersed) alternative to the current Poisson is evaluated for the quantile Monte Carlo; p10/p90 empirical coverage must be within ±5 points of nominal
- [ ] Held-out targets (honest): production MAE ≥ 10% better than the PPG baseline; round-point rank ρ ≥ 0.65; both per-season rows shown
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

### US-507: Injuries and lineup confirmation in the live path, validated on labeled data
**Description:** As the tool owner, I want the one information edge humans on a phone don't
have — structured injury status, expected return, and confirmed starting goalies — to
demonstrably move draft-night projections and to be calibrated on real labels. Today the
backtests run with the injury haircut as a no-op and the return-time model is calibrated on
absence spells, not labeled injuries.

**Acceptance Criteria:**
- [ ] The Dec 2025–Jun 2026 as-of-game `injuries` blocks already committed under `odds-archive/espn-2025-26-completion/raw/summary/` become the **labeled validation slice** for the return-time model: predicted vs observed P(available for game k) reported per status, and the status→mean-absence map refit on it (documented before/after)
- [ ] A **starting-goalie confirmation** source (NHL API gamecenter/pre-game lineup, DailyFaceoff as documented fallback) feeds the team slot's starter/backup GSAx choice for game 1, with the manual override YAML as final authority and a loud "unconfirmed" flag otherwise
- [ ] The 2026 backtest replays with **as-of injury statuses** reconstructed from the labeled slice (leakage-guarded by date), so the injury haircut and IR valuation are exercised in evidence for the first time; the report states the marginal effect on oracle points
- [ ] `oracle project` prints an injury-impact summary (players discounted, expected points removed, unresolved ids) and the cheat sheet's Status column shows return-game expectations
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

### US-508: Standings-aware objective — variance as a lever in rounds 2–4
**Description:** As the tool owner, I want the recommender to choose *how much variance to
take* based on my standing, because rounds 2–4 draft worst-to-best and the season is won on
cumulative points: a manager trailing by 20 should prefer high-ceiling stacks; a manager
leading should protect the floor. Today every seat maximizes expected points.

**Acceptance Criteria:**
- [ ] The recommender accepts the current cumulative standings (`--standings ben=120,judah=104,...` or from the session log) and an objective among `mean`, `p_win_season` (probability the owner finishes first over the remaining rounds, estimated on the US-505 scenario tensor), and `mean_minus_lambda_var`; default remains `mean` until the backtest shows a winner
- [ ] Backtest strategies `oracle_pwin` and `oracle_meanvar` replayed with the real standings entering each round; US-501 reports season-win fraction and decision regret against `oracle` and `greedy_vor` with intervals
- [ ] `recommend` explains the objective in use and, under `p_win_season`, shows each candidate's effect on P(win season) and on the roster's p10/p90
- [ ] If no variance-aware objective beats `mean` on season wins with the interval excluding zero, the report says so and `mean` stays default (honesty rule)
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

### US-509: Phase 1 evidence pass and v2 verdict
**Description:** As the tool owner, I want one regenerated set of committed evidence at a
clean HEAD after Phase 1 lands, with a plain-language verdict against this PRD's goals, so I
know before next spring whether v2 is a real step up.

**Acceptance Criteria:**
- [ ] All model reports, both backtests, the 2026-r* fixtures and `EVIDENCE_PASS.json` regenerated in one pass at a clean HEAD (US-406 pattern), with the champion/challenger comparison to the pre-Phase-1 `main` artifacts embedded in each report
- [ ] `ml/EVALUATION.md` (new) summarizes: replayed season-league wins (target ≥ 3/4), best-seat ≥ league-best rounds (target ≥ 9/12), team ρ, series Brier vs market, skater MAE/ρ, quantile coverage — each with the interval and a met / not-met verdict, misses stated plainly
- [ ] `DRAFT_NIGHT.md` and `README.md` updated for the new artifact contents (scenario tensor, objectives, injury summary) and the "Honest expectations" section rewritten from the new numbers
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

---

## User Stories — Phase 2 (backlog; each gated by US-501 and adopted only if it wins)

### US-601: Extend the NHL archive to 2007-08 onward
**Description:** As the tool owner, I want more playoff series in training (today 11 seasons ≈
165 series) because the series model's held-out sample of 30 is what makes its calibration
noisy. The NHL stats REST API serves seasons back to 2007-08 with the same schema.
**Acceptance Criteria:**
- [ ] `fetch_nhl.py` `SEASONS` extended to 2007-08; new team/skater/bios files and brackets committed with provenance; `normalize` handles the older rows (team relocations/renames mapped via `resolve_team_id`)
- [ ] Series model retrained with the longer history under the held-out protocol; report shows whether the added seasons help (they may not — rule changes; say so)
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

### US-602: Nested temporal cross-validation and hyper-parameter search
**Description:** As the tool owner, I want model hyper-parameters chosen by rolling-origin
validation across several seasons rather than a single validation year, so choices are not
fit to 2024's idiosyncrasies.
**Acceptance Criteria:**
- [ ] A `tuning/` module runs rolling-origin CV (train ≤ t−2, validate t−1, for t across four seasons) for every model with a bounded search budget and a fixed seed; the chosen configuration and the full search table are written to the model manifest
- [ ] Test-season metrics are computed once, after selection, and never used for selection (guarded by a test that the tuner cannot see test rows)
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

### US-603: Conformal prediction intervals for skater round points
**Description:** As the tool owner, I want distribution-free intervals with guaranteed
coverage on held-out data, replacing Monte-Carlo quantiles whose coverage is unverified.
**Acceptance Criteria:**
- [ ] Split-conformal (or CQR) intervals fit on validation years; held-out p10/p90 coverage within ±3 points of nominal, reported per season; cheat sheet shows the conformal band
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

### US-604: In-series dynamics — goalie changes, injuries during the series, home-ice reality
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

### US-605: Skater availability inside a round from absence spells and lineup data
**Description:** As the tool owner, I want the probability a skater dresses for each game of
the series (healthy scratch, in-series injury) modeled from the archive's absence spells and
NaturalStatTrick lineups, not assumed to be 1.0.
**Acceptance Criteria:**
- [ ] Per-skater per-game dress probability estimated as-of the round; held-out calibration reported; feeds the US-505 tensor
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

### US-606: Ensembling and stacking across model families
**Description:** As the tool owner, I want the per-game win and skater production predictions
to combine the best families found in US-504/US-506 (stat-only, market-aware, Bayesian,
boosted) with weights fit on validation years.
**Acceptance Criteria:**
- [ ] Stacked models evaluated under the held-out protocol; adopted only if the interval excludes zero; weights and component metrics recorded in the manifest
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

### US-607: Explainability in the cheat sheet
**Description:** As the tool owner, I want to see *why* a player is ranked where he is (top
feature contributions, matchup, deployment) so I can sanity-check in a 60-second pick window.
**Acceptance Criteria:**
- [ ] SHAP (or exact contributions for linear/Bayesian models) computed at artifact build time; the cheat sheet and `recommend` show the top three drivers per player as short phrases; no draft-time model dependency (values precomputed into the artifact)
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

### US-608: Opponent model refresh (survival probabilities, not league exploitation)
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

### US-609: Rest, travel, and schedule effects
**Description:** As the tool owner, I want per-game features for days of rest, back-to-back
games, time-zone travel, and series-start rest differential, which are known small but real
effects the model currently ignores.
**Acceptance Criteria:**
- [ ] Features derived from the archive schedule; ablation reported; kept only if the held-out Brier improves
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

### US-610: Drift monitoring and season-start retrain checklist
**Description:** As the tool owner, I want a single command that refreshes all data, retrains
every model, regenerates evidence, and diffs every metric against last season's champion,
so the tool is re-validated each April in minutes.
**Acceptance Criteria:**
- [ ] `oracle season-start --season YYYY` runs the fetches (with clear instructions for the owner-machine steps the sandbox cannot do), normalize, train, evaluate, and writes a drift report (feature distributions, metric deltas) to `ml/artifacts/drift/`
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

### US-611: Small neural sequence model for per-game production (exploratory)
**Description:** As the tool owner, I want to know whether a compact sequence model over a
skater's game log beats the tabular models, since the stack is now allowed to include one.
**Acceptance Criteria:**
- [ ] A CPU-trainable GRU/temporal-conv model over the last 40 games per skater, trained under the same protocol and seeds; adopted only if it beats the US-506 champion with the interval excluding zero; otherwise the report records the negative result and the model is not shipped
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
- FR-7: New external sources (The Odds API history, MoneyPuck, NaturalStatTrick, starting-goalie confirmations) are fetched by committed scripts run from the owner's machine, committed as snapshots with `PROVENANCE.md`, and parsed by tested code; the pipeline never depends on live availability of these sites.
- FR-8: Every new table carries an as-of date and is covered by the leakage tests.
- FR-9: Paid API keys live in `ml/.env` (gitignored); fetch scripts fail loudly without them; fetch cost per run is documented.

### Models
- FR-10: The team-strength model must produce P(win), P(shutout win) and expected margin from one coherent score distribution.
- FR-11: Series-winner probabilities must be calibrated post hoc on validation years; reliability bins are reported for every held-out set.
- FR-12: Skater projections must decompose into rate × games as today, with the rate model informed by usage, shot quality, matchup and multi-season priors.
- FR-13: Roster value must be computable from a shared scenario tensor so correlated outcomes are priced; marginal player projections remain available and unchanged.
- FR-14: Any wider-stack model (Bayesian, neural, CatBoost) must be CPU-trainable within the 15-minute batch budget on the owner's machine and seeded; GPUs are optional, never required.

### Optimizer and CLI
- FR-15: The recommender supports `mean`, `p_win_season`, and `mean_minus_lambda_var` objectives with standings input; `mean` stays default until evidence changes it.
- FR-16: `recommend` shows roster mean and p10/p90 change per candidate and the top drivers behind each projection.
- FR-17: Draft-time commands remain offline and under the existing latency budgets (10 s full depth, 5 s depth 1) with the scenario tensor loaded.

### Outputs
- FR-18: One evidence pass regenerates all committed artifacts together with shared provenance (`EVIDENCE_PASS.json`) after Phase 1 and after each adopted Phase 2 story.
- FR-19: `ml/EVALUATION.md` states the PRD's success metrics with intervals and met/not-met verdicts.

## Non-Goals (Out of Scope)

- **No league-specific exploitation as a goal.** Opponent tendencies matter only for survival probabilities (US-608); we do not tune projections to beat ben, judah, kyle or levi specifically.
- **No app integration, no serving, no UI** — the tool stays an offline batch pipeline plus local CLI.
- **No in-round roster management** beyond IR draft valuation (mid-round activation alerts remain a future idea).
- **No trading of honesty for headline numbers.** If Phase 1 fails to reach a target, the target stays unmet in the evidence.
- **No live scraping at draft time.** Everything the CLI needs is in the artifact; live sources are used only when building it.
- **No hand-maintained feature spreadsheets.** Every feature has a scripted, reproducible source.

## Design Considerations

- The scenario tensor is the new contract between projection and optimization; keep the marginal tables so the cheat sheet and existing tests stay valid.
- Cheat sheet additions (drivers, bands, injury status) must stay readable on a phone; one extra column at most, details in `recommend`.
- The champion/challenger report is the *first* thing a reader sees in every model report — the verdict, the interval, then the tables.

## Technical Considerations

- **Small data is still small data.** Bayesian hierarchical models and multi-season priors exist precisely because ~165 series and ~350 skater-rounds per season overfit anything flexible; every flexible model must be beaten by (or beat) the regularized baseline on held-out years, and the report says which.
- **Stack widening** (SPEC §3 amendment): add `catboost`, a probabilistic-programming library (`numpyro` or `pymc`), `mapie` (conformal), and optionally `torch` (CPU) as extras; keep `uv` lockfile, seeds, `mypy --strict`, ruff; draft-time CLI must still import none of them (US-208 guard extended).
- **Sandbox limits.** The repo's cloud sandboxes cannot reach the NHL API, ESPN, MoneyPuck, NaturalStatTrick or The Odds API; every fetch story specifies the owner-machine steps and commits snapshots, as the v1 data foundation did.
- **Cost.** The Odds API historical tier is metered per request; the fetch plan (per-day playoff snapshots 2020–2026, ~600 days) should be costed before running and recorded in PROVENANCE.
- **Correlation vs speed.** A 2,000-draw tensor over ~450 skaters × 7 games is ~6M cells per round; store as compact integers/float16 and precompute per-player cumulative points per draw so `recommend` reduces to sums over selected columns.
- **Calibration set discipline.** Post-hoc calibrators (isotonic/Platt/conformal) fit on validation years only; a test asserts they never see test rows.
- **Provenance.** Continue the `git_sha`/`git_dirty`/`EVIDENCE_PASS.json` pattern; the champion is identified by that sha.

## Success Metrics

Measured by US-501 on 2023–2026, challenger (post-Phase 1 HEAD) vs champion (`main` at
this PRD's merge), 95% paired-bootstrap intervals; each row is met/not-met in `ml/EVALUATION.md`.

| Metric | Champion today | Phase 1 target |
| --- | --- | --- |
| Replayed season-leagues won by the oracle's mean seat | 2 of 4 | ≥ 3 of 4 |
| Rounds where the oracle's best seat ≥ league best | 7 of 12 | ≥ 9 of 12 |
| Oracle vs greedy-VOR mean points | −0.20 (no interval) | > 0 with interval excluding zero, or an honest "tie" |
| Pooled team goalie-slot rank ρ | 0.276 | ≥ 0.50 |
| Goalie-slot MAE (points/round) | 2.8–3.2 | < 2.5 |
| Series Brier vs pre-series market, ≥ 40 series | model 0.224 vs market 0.234 on 14 | ≤ market on ≥ 40 |
| Series 0.40–0.60 reliability bin (pred vs obs) | 0.517 vs 0.214 | within ±0.10 |
| Shutout Brier vs base rate | 0.0923 vs 0.0921 (no skill) | strictly below base rate |
| Skater production MAE gain over PPG baseline | 8% | ≥ 10% |
| Skater round-point rank ρ | 0.593 | ≥ 0.65 |
| p10/p90 empirical coverage | unmeasured | within ±5 points of nominal |

## Open Questions

1. **Which Odds API plan and how far back?** Series (`outrights`) prices may only exist for recent seasons; if 2020–2022 lack them, is game-1 `h2h` alone acceptable as the benchmark for those years?
2. **Starting-goalie confirmations** are published hours before game 1, typically *after* the round-1 draft. Should US-507 model the *probability* of each starter rather than assume confirmation, and is DailyFaceoff scraping acceptable given its terms?
3. **Objective default.** If `p_win_season` wins the 2024–2026 replays but only narrowly, do you want it as the draft-night default, or `mean` with the alternative shown?
4. **Archive depth.** Pre-2013 seasons had different playoff formats and rules (e.g., no 3-on-3 OT, different divisions); include them for the series model with an era indicator, or stop at 2013-14?
5. **Budget for Phase 2.** Which of US-601…US-611 should be promoted into Phase 1 if Phase 1's targets are met early — the archive extension (more series) or the neural exploration?
