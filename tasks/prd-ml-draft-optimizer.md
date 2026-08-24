# PRD: ML Draft Optimizer ("Draft Oracle")

## Introduction / Overview

Build a **standalone, offline machine-learning research tool** that helps its owner draft the best possible fantasy team under the SportsNot ruleset. The tool is a personal edge — it is **not** a SportsNot app feature, has no UI in the web app, and requires no live serving infrastructure. It runs entirely as a local Python pipeline: it ingests NHL data, trains models, and produces **precomputed batch predictions** (round-by-round player/team projections) plus an **interactive local CLI draft assistant** that consumes those precomputed predictions during a live draft.

The core problem: SportsNot's format is unusual enough that generic fantasy rankings are badly miscalibrated for it. Specifically:

1. **Full re-draft every playoff round** — season-long value is irrelevant; only expected production *within the upcoming round* matters. A superstar on a team likely to be swept in 4 games is often worth less than a good player on a team headed for a 7-game series.
2. **Goals and assists are worth the same (1 pt each)** — public rankings that weight goals higher are wrong for this league. Total point production (G+A) is the only skater signal that matters.
3. **The goalie slot is an entire NHL team's goaltending**, scored on team wins (2 pts) and shutouts (4 pts, replacing the win's 2 pts) — its value is driven almost entirely by the series-outcome distribution, not individual goalie skill in isolation.
4. **Snake draft with standings-based re-draft order (worst to best)** — optimal picking requires lookahead: what will survive until my next turn, given my slot in the snake?
5. **IR slots with retroactive point swap** — an injured star can be stashed in an IR slot and activated later, retroactively swapping points with the replaced same-position player. This creates a real, quantifiable option value that no generic tool models.

The tool decomposes into four cooperating components, all in scope for v1:

- **A. Player point projection model** — expected fantasy points (G+A) per skater for the upcoming round.
- **B. Team/series outcome model** — series win probability, expected wins, expected series length, and shutout probability per team per round. Feeds both the goalie-slot valuation and skater games-played expectations.
- **C. Draft pick optimizer** — turns projections into concrete pick recommendations using value-over-replacement, positional scarcity (5F/3D/1G), snake-order lookahead with player survival probabilities, and a simple opponent-pick model.
- **D. Injury/IR valuation** — quantifies when drafting an injured player to an IR slot beats a healthy bench-tier pick, including the retroactive point-swap mechanic.

## Glossary & Ruleset Reference (source of truth)

These rules are extracted from the SportsNot codebase and are **normative** for the tool. Any model or simulator must reproduce them exactly.

| Rule | Value | Code reference |
| --- | --- | --- |
| Goal | 1 pt | `SCORING.goal` in `packages/types/src/lib/types.ts`; `calculatePlayerPoints` in `packages/utils/src/lib/utils.ts` |
| Assist | 1 pt | `SCORING.assist`, same files |
| Team win | 2 pts | `SCORING.win`; `calculateGoalieGamePoints` |
| Team shutout win | 4 pts, **replaces** the 2-pt win (not additive) | `calculateGoaliePoints`: `(wins − shutouts) × 2 + shutouts × 4` |
| Loss / OT loss | 0 pts | `calculateGoalieGamePoints` returns 0 unless `teamScore > opponentScore` |
| Active roster | 5 Forwards (F), 3 Defensemen (D), 1 Goalie/Team (G) | `ROSTER_COMPOSITION` in `packages/types/src/lib/types.ts` |
| IR slots (when league enables them) | +1 IR Forward, +1 IR Defenseman | `getRosterComposition(allowIrSlots)` |
| Total picks per manager | 9 (no IR) or 11 (with IR) | Derived from composition |
| League size | 2–12 managers | `leagues.max_participants CHECK (BETWEEN 2 AND 12)` |
| Round 1 draft order | Randomized, snake pattern | `generateSnakeDraftOrder`, `shuffleArray` |
| Rounds 2–4 draft order | Standings **worst → best**, snake pattern | `generateReDraftOrder` (sorts points ascending) |
| Re-draft | Full re-draft between rounds; **no keepers**; all players return to the pool | `archiveRostersForRoundAdvance`; plan §Core Gameplay |
| Eliminated players/teams | Undraftable once their NHL team is eliminated | Plan note 4 |
| Goalie pick | Drafts a **team's** goaltending (a `team_id`, not a `player_id`) | `DraftPick.teamId`; plan note 5 |
| IR activation | Injured active player swaps with a same-position IR player; points are swapped **retroactively** for the round | Plan §8.2; `activatedFromIr` on `RosterSlot` |
| NHL playoff structure | 4 rounds; best-of-7 series; 16 → 8 → 4 → 2 teams | NHL format (external) |

**Key derived facts the models must respect:**

- A skater's fantasy ceiling in a round is bounded by their team's series length (4–7 games). Expected skater points ≈ (expected points per game) × (expected games played in the series).
- Because every round is a fresh draft, **elimination risk beyond the current round is irrelevant** to draft value. Only in-round production counts.
- Goalie-slot expected points for a series = Σ over games of [P(win) × 2 + P(shutout win) × 2 extra]. A dominant team sweeping 4-0 (8 pts + shutout bonus) can out-earn a team that wins a 7-game slugfest (8 pts, fewer shutouts) — but a team that *loses* the series in 7 while winning 3 games still banks 6+ pts. Expected wins, not just series win probability, is the metric.
- Snake-position value asymmetry: in a 10-team league the manager picking 1st waits 19 picks until their 2nd selection; the manager picking 10th gets picks 10 and 11 back-to-back. The optimizer must reason about this explicitly.

## Goals

- Produce, for any upcoming playoff round, a projections file covering **every draft-eligible skater** (expected fantasy points with uncertainty intervals) and **every remaining team** (goalie-slot expected points, expected wins, shutout probability, series length distribution).
- Provide a **ranked cheat sheet** ordered by value-over-replacement (VOR) that accounts for the 5F/3D/1G positional structure and league size.
- Provide an **interactive CLI draft assistant**: the owner enters picks as they happen; the tool recommends the best available pick for their next turn, with lookahead to which candidates will likely survive until then.
- Quantify **IR-slot strategy**: for every injured F/D, an expected-value estimate of stashing them vs. the best available healthy alternative, including the retroactive point-swap payoff.
- **Backtest** the whole system against at least 3 historical NHL playoff years and demonstrate it beats naive baselines (see Success Metrics).
- Keep everything **offline and batch**: no servers, no Supabase writes, no app integration. Outputs are files (Parquet/CSV/Markdown) plus a local CLI.

## User Stories

### US-001: Scaffold the Python ML workspace
**Description:** As the tool owner, I want an isolated Python project inside the repo so the ML pipeline has a home without disturbing the Nx/TypeScript workspace.

**Acceptance Criteria:**
- [ ] New top-level directory `ml/` containing a `uv`-managed Python 3.12+ project (`pyproject.toml`, lockfile committed)
- [ ] Package named `draft_oracle` with subpackages: `ingest/`, `features/`, `models/`, `optimize/`, `cli/`, `backtest/`
- [ ] Dev tooling configured: `ruff` (lint + format), `mypy --strict`, `pytest`; all runnable via documented `uv run` commands
- [ ] `ml/` is excluded from Nx project graph and from yarn/ESLint/TS tooling (no Nx target breakage; `nx run-many` targets unaffected)
- [ ] `ml/README.md` documents setup, commands, and the pipeline stages
- [ ] A CI-independent smoke test exists: `uv run pytest` passes on a fresh clone
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

### US-002: Ruleset engine (Python mirror of SportsNot scoring)
**Description:** As the tool owner, I want a Python module that exactly reproduces SportsNot scoring and draft-order rules so every projection, simulation, and backtest is scored identically to the real app.

**Acceptance Criteria:**
- [ ] `draft_oracle.rules` implements: `player_points(goals, assists)`, `goalie_series_points(wins, shutouts)`, `goalie_game_points(team_score, opp_score)`, `snake_order(participants, total_picks)`, `redraft_order(standings, total_picks)`, `roster_composition(allow_ir_slots)`
- [ ] Outputs are property-tested against the TypeScript reference behavior: shutout replaces win (a 1-0 win = 4 pts, not 6); losses = 0; snake reversal on odd rounds; re-draft sorts points ascending (worst first)
- [ ] Golden-value test vectors are copied from `packages/utils/src/lib/utils.test.ts` cases so a rules drift in either language is caught
- [ ] Roster validator: rejects rosters violating 5F/3D/1G(+1 IR_F/+1 IR_D), duplicate players, or eliminated-team players
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

### US-003: NHL data ingestion — skaters, teams, schedules
**Description:** As the tool owner, I want reproducible ingestion of NHL regular-season and playoff data so models can be trained and fresh projections generated each round.

**Acceptance Criteria:**
- [ ] Ingestion client for the NHL API (`api-web.nhle.com`) with typed response models, request caching to disk, and polite rate limiting (configurable delay, retries with backoff)
- [ ] Fetches per season: skater game logs (regular season + playoffs), team game results with scores, playoff bracket/series metadata, current rosters, player positions, injury/status flags where exposed
- [ ] Historical coverage: at minimum the 10 most recent completed seasons' playoffs plus their regular seasons
- [ ] All raw responses land in `ml/data/raw/` (gitignored); normalized tables land in `ml/data/` as Parquet with a documented schema (`skater_games`, `team_games`, `series`, `players`, `teams`)
- [ ] Every ingestion run is idempotent and incremental (re-running only fetches missing/changed data); a `snapshot` command freezes a dated copy of normalized tables for reproducible training
- [ ] Position mapping collapses NHL position codes to SportsNot positions: C/L/R → F, D → D; goalies are excluded from the skater pool (goalie value is team-level)
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

### US-004: Feature engineering pipeline
**Description:** As the tool owner, I want a deterministic feature pipeline that turns normalized data into model-ready training matrices for both the skater and series models.

**Acceptance Criteria:**
- [ ] Skater features (per player, per playoff round, as-of the round start — **no leakage from the round being predicted**): regular-season G/A/P per game, last-25-games rates, power-play time share, average time on ice, shots/game, individual shooting %, age, position, teammate quality proxy (linemate P/GP), team offensive rates
- [ ] Series/team features (per series, as-of series start): regular-season goal differential, goals for/against per game, special-teams percentages, head-to-head record, home-ice advantage, rest days, goaltender save % (season and last 15 starts), Elo-style team rating maintained across seasons
- [ ] Round-context features: round number (1–4), expected opponent strength, days between games
- [ ] Every feature has a unit-tested computation and a docstring defining its as-of semantics; a leakage test asserts no feature for round N uses any game played in round N or later
- [ ] Pipeline emits versioned training matrices to `ml/data/features/` keyed by a feature-set version string
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

### US-005: Team/series outcome model
**Description:** As the tool owner, I want a model of each playoff series that outputs the win probability, the distribution over series outcomes (4-0 through 4-3 either way), expected wins for each team, and per-game shutout probability — because this drives goalie-slot value and every skater's expected games played.

**Acceptance Criteria:**
- [ ] Per-game win model: probability team A beats team B in a single game (home/away aware), trained on historical playoff + regular-season games (gradient-boosted trees or logistic regression on team features — selection justified by validation results)
- [ ] Per-game shutout model: P(win is a shutout | win, teams) calibrated on historical playoff shutout rates
- [ ] Series simulator: composes per-game probabilities into a best-of-7 with correct home-ice pattern (2-2-1-1-1) and outputs the full outcome distribution: P(win series), P(each of 4/5/6/7 games), E[wins], E[games], E[goalie slot points] via the rules engine
- [ ] Calibration report on held-out seasons: reliability curve and Brier score for series winners; predicted vs. actual series-length distribution; predicted vs. actual shutouts per round
- [ ] Beats baselines on held-out seasons: (a) coin flip, (b) higher regular-season points wins, measured by Brier score
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

### US-006: Skater point projection model
**Description:** As the tool owner, I want per-skater expected fantasy points for the upcoming round, with uncertainty, so the draft optimizer has a value estimate for every pick.

**Acceptance Criteria:**
- [ ] Two-part structure: (1) per-game production model predicting E[G+A per game] for the round (regularized gradient boosting or Poisson/negative-binomial regression on US-004 skater features), (2) games-played distribution taken from the series model's E[games] for the player's team (plus an availability haircut for injury status)
- [ ] Output per skater per round: `expected_points` (mean), `p10`/`p50`/`p90` quantiles (via quantile models or Monte Carlo over the series-length distribution and per-game scoring variance), plus the decomposition (`pts_per_game`, `expected_games`)
- [ ] Trained with strict temporal cross-validation: predict each historical round using only data available before that round; no test-season leakage into training
- [ ] Beats baselines on held-out seasons by MAE and Spearman rank correlation against actual round fantasy points: (a) regular-season points-per-game × 5.5 games, (b) previous-round fantasy points
- [ ] Handles cold cases sanely: rookies/low-sample players shrink toward position-team priors; players who didn't play in the regular season get a flagged low-confidence projection, not a crash
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

### US-007: Batch projection runs and artifact format
**Description:** As the tool owner, I want a single command that produces the complete precomputed prediction set for an upcoming round so drafting never depends on live model inference.

**Acceptance Criteria:**
- [ ] `uv run oracle project --season 2026 --round 2` runs ingest-refresh → features → inference and writes one self-contained artifact directory `ml/artifacts/<season>-r<round>/`
- [ ] Artifact contains: `skaters.parquet` + `skaters.csv` (id, name, team, position F/D, expected_points, quantiles, decomposition, injury flag), `teams.parquet` + `teams.csv` (goalie-slot expected points, E[wins], E[games], P(series win), shutout expectations), `cheatsheet.md` (human-readable ranked sheet), and `run_manifest.json` (data snapshot id, model versions, feature version, git SHA, timestamp)
- [ ] Only draft-eligible entries appear (eliminated teams and their players are excluded automatically from bracket state)
- [ ] Re-running with the same snapshot reproduces byte-identical Parquet outputs (fixed seeds, deterministic ordering)
- [ ] Completes in under 10 minutes on a laptop given an up-to-date data cache
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

### US-008: Value-over-replacement and scarcity rankings
**Description:** As the tool owner, I want raw projections converted to draft value so that positional scarcity (5F/3D/1G across N managers) is priced into every ranking.

**Acceptance Criteria:**
- [ ] Replacement level per position computed from league size: for N managers, replacement F = the (5N+1)-th ranked F, replacement D = the (3N+1)-th D, replacement G/team = the (N+1)-th team (with sensible handling when fewer teams remain than managers)
- [ ] `VOR = expected_points − replacement_level_points` computed for every skater and team; cheat sheet sorted by VOR with position, projection, quantiles, and injury flags displayed
- [ ] League size and IR-enabled flag are CLI parameters (`--managers 10 --ir/--no-ir`) that change replacement levels and sheet layout
- [ ] Unit tests cover scarcity edge cases: 2-manager league, 12-manager league, final round with only 2 teams alive (goalie slot scarcity extreme)
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

### US-009: Draft simulator and opponent model
**Description:** As the tool owner, I want a faithful snake-draft simulator with a model of how opponents pick, so pick recommendations can account for who will still be available at my next turn.

**Acceptance Criteria:**
- [ ] Simulator enforces the full ruleset via `draft_oracle.rules`: snake order, per-position roster limits (a manager with 5 F must pick D or G), IR slots pickable only when enabled, no duplicates, eliminated players unavailable
- [ ] Opponent model v1: opponents pick greedily by a public-perception ranking (regular-season points) with softmax noise (temperature configurable) and positional-need awareness; documented as replaceable
- [ ] Survival estimation: for any draft state and any candidate, Monte Carlo over opponent picks yields P(candidate survives until my next pick) with ≥1,000 rollouts completing in <5 seconds
- [ ] Deterministic under a fixed seed; simulator round-trips a full 10-manager, 11-pick draft in a unit test producing a valid roster for every manager
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

### US-010: Pick recommendation engine
**Description:** As the tool owner, I want the optimizer to tell me the best pick right now — not just the highest-VOR player — by weighing what I can still get later in the snake.

**Acceptance Criteria:**
- [ ] Recommendation = argmax over available candidates of expected final-roster points, estimated by: value now + expected value of remaining slots filled at future picks, using survival probabilities from US-009 (one-step lookahead minimum; deeper rollout behind a `--depth` flag)
- [ ] Explanations included: for the top 5 recommendations, show VOR, P(survives to next pick), and the positional-need reasoning (e.g., "only 3 above-replacement D remain; F depth survives 12 more picks")
- [ ] Correctly handles forced picks (roster slots nearly full) and the goalie-slot timing decision (when to take a team vs. another skater)
- [ ] In simulated drafts against 9 greedy opponents over ≥200 seeded drafts, the engine's average final roster projects higher total points than a pure greedy-VOR strategy drafting from the same slot
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

### US-011: Injury and IR-slot valuation
**Description:** As the tool owner, I want injured players valued correctly for IR slots — including the retroactive point-swap on activation — so I know when stashing an injured star beats a healthy depth pick.

**Acceptance Criteria:**
- [ ] Injury status ingested per player (out/day-to-day/healthy) with a manually-editable override file `ml/data/overrides/injuries.yaml` for information the API lacks (expected return timelines)
- [ ] Return-time model: P(returns by game k of the round) per injured player — a simple calibrated mapping from status + report keywords is acceptable for v1, documented as such
- [ ] IR stash EV: E[points if stashed and activated optimally] using the retroactive swap rule — on activation, the IR player's full round points replace the swapped same-position active player's points from the start of the round (mirror of SportsNot's retroactive mechanic; matching position F↔F, D↔D enforced)
- [ ] Cheat sheet gains an IR section ranking injured F/D by stash EV vs. the healthy replacement-level alternative, with a clear "stash" / "avoid" verdict
- [ ] Optimizer (US-010) treats IR_F/IR_D as distinct slots valued by stash EV when `--ir` is set
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

### US-012: Interactive CLI draft assistant
**Description:** As the tool owner, I want a terminal UI I run during the live draft: I record every pick as it happens and instantly see my best options for my next turn.

**Acceptance Criteria:**
- [ ] `uv run oracle draft --artifact ml/artifacts/2026-r2 --managers 10 --slot 7 --ir` starts a session; all valuation comes from the precomputed artifact (no network, no model inference at draft time)
- [ ] Commands: record any manager's pick by fuzzy player/team name (`pick 3 kucherov`), undo, show board (remaining by position), show my roster, `recommend` (top 5 with explanations from US-010), save/resume session to a JSON file
- [ ] Illegal actions are rejected with the reason (position full, already drafted, eliminated)
- [ ] `recommend` returns in under 5 seconds at any draft state
- [ ] Session log written so the draft can be replayed for post-hoc analysis
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

### US-013: Backtesting harness
**Description:** As the tool owner, I want end-to-end historical backtests so I can trust (or distrust) the system before using it in a real draft.

**Acceptance Criteria:**
- [ ] `uv run oracle backtest --seasons 2023,2024,2025` replays every playoff round of each season: builds as-of projections, runs simulated drafts (oracle in each snake slot vs. greedy opponents), scores all resulting rosters with **actual** historical results via the rules engine
- [ ] Reports per season and aggregate: projection MAE and rank correlation (skaters and teams), series-model Brier score, oracle roster's actual points vs. greedy-VOR baseline and vs. random-legal-draft baseline, win rate across snake slots
- [ ] Strict as-of discipline verified by an automated leakage check (backtest for round N fails loudly if any input artifact contains round-N data)
- [ ] Results written to `ml/artifacts/backtests/<run-id>/report.md` with tables per round and per snake slot
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

## Functional Requirements

### Data & ruleset
- FR-1: The system must mirror SportsNot scoring exactly: goal = 1, assist = 1, team win = 2, shutout win = 4 replacing the win points (never 6 for one game), losses = 0.
- FR-2: The system must mirror roster composition (5F/3D/1G; +1 IR_F/+1 IR_D when IR is enabled) and enforce it in every simulation and recommendation.
- FR-3: The system must implement snake draft order and standings-based re-draft order (points ascending, worst first) identically to `generateSnakeDraftOrder`/`generateReDraftOrder`.
- FR-4: The system must ingest NHL regular-season and playoff data for ≥10 historical seasons plus the current season, normalized to a documented Parquet schema, with idempotent incremental refresh and dated snapshots.
- FR-5: The system must map NHL positions to SportsNot positions (C/L/R → F; D → D) and exclude individual goalies from the skater pool.
- FR-6: The system must automatically exclude eliminated teams and their players from any round's draft pool using bracket state.

### Models
- FR-7: The series model must output, for every live series: P(win series) per team, the distribution over series lengths, E[wins] per team, E[games], and expected goalie-slot fantasy points computed through the rules engine.
- FR-8: The shutout component must be explicitly modeled and calibrated against historical playoff shutout frequency (roughly 1 in 8–10 playoff games historically; the model must be within ±25% of observed frequency on held-out seasons).
- FR-9: The skater model must decompose expected round points into per-game production × expected games played, and expose both components in outputs.
- FR-10: All model outputs must carry uncertainty (p10/p50/p90) derived from quantile modeling or Monte Carlo simulation.
- FR-11: All training and evaluation must use strict as-of temporal splits; an automated leakage test must fail the build if violated.
- FR-12: Every prediction artifact must be reproducible: fixed seeds, pinned dependency lockfile, and a manifest recording data snapshot, feature version, model version, and git SHA.

### Optimizer
- FR-13: Replacement level must be computed per position from league size N (F: rank 5N+1, D: rank 3N+1, G/team: rank N+1) and drive VOR rankings.
- FR-14: The recommendation engine must incorporate snake lookahead: candidate survival probabilities to the user's next pick, estimated by Monte Carlo over an opponent model, and must outperform greedy-VOR in simulation (US-010 criterion).
- FR-15: The opponent model must be a pluggable interface; v1 ships greedy-by-public-ranking with softmax noise and positional need.
- FR-16: IR_F/IR_D slots must be valued via stash EV that models the retroactive point swap: activation replaces the same-position active player's points from the start of the round with the activated player's points.
- FR-17: The CLI draft assistant must operate entirely from a precomputed artifact with no network access and respond to `recommend` in <5 s.

### Outputs & evaluation
- FR-18: Each projection run must emit machine-readable (Parquet/CSV) and human-readable (Markdown cheat sheet) artifacts as specified in US-007.
- FR-19: The backtest harness must replay ≥3 historical postseasons end-to-end and report the metrics in US-013 against actual results.
- FR-20: The system must degrade gracefully on missing data: flagged low-confidence projections and prior-based fallbacks, never silent zeros or crashes.

## Non-Goals (Out of Scope)

- **No SportsNot app integration**: no web UI, no Supabase reads/writes, no edge functions, no changes to `packages/*` runtime code. The only repo footprint is the new `ml/` directory (and this PRD).
- **No live inference service**: no API server, no scheduled jobs, no cloud deployment. Everything is batch + local CLI.
- **No multi-user product concerns**: no auth, no sharing, no fairness considerations for other league members.
- **No in-round roster management beyond IR draft valuation**: mid-round IR activation timing alerts, lineup notifications, etc. are out of scope (a post-v1 idea).
- **No paid/scraped data sources**: v1 uses the public NHL API only (plus manual override files). MoneyPuck/NaturalStatTrick enrichment is a noted future option, not a requirement.
- **No deep-learning stack**: v1 is tabular ML (gradient boosting / GLMs / Monte Carlo). No GPUs, no neural nets, no LLMs.
- **No trade or waiver tooling**: the SportsNot format has none; the tool models drafting only.
- **No betting-odds ingestion** in v1 (flagged as an open question — odds are a strong series-outcome signal but add a dependency).

## Design Considerations

- **CLI-first, files as the interface.** Cheat sheets are Markdown tables readable on a phone during a draft; Parquet/CSV serve notebook exploration. The interactive assistant is a plain terminal REPL (e.g., `rich`-rendered tables) — no TUI framework required for v1.
- **Explanations over black boxes.** Every recommendation shows its decomposition (projection, VOR, survival %, positional reasoning). During a 60-second pick window, the owner needs to sanity-check the model at a glance.
- **Artifacts are the contract** between the batch pipeline and the draft-time CLI. The CLI must never need the training stack installed to run — projections + optimizer logic only.

## Technical Considerations

- **Language/stack:** Python 3.12+, `uv` for env/deps, `polars` or `pandas` for frames, `scikit-learn` + `xgboost`/`lightgbm` for models, `pydantic` for API response typing, `pytest` + `hypothesis` for tests, `ruff` + `mypy --strict`.
- **Repo placement:** top-level `ml/` directory, excluded from the Nx graph (add to `.nxignore`/ESLint ignore as needed) so `yarn nx affected` and existing CI are untouched. Raw data and artifacts are gitignored except backtest reports and manifests.
- **NHL API risk:** the API is undocumented and can change; ingestion isolates all endpoint knowledge in `draft_oracle.ingest` behind typed adapters, caches raw JSON to disk, and supports a manual CSV drop-in path as a fallback (mirrors the app's own risk-mitigation stance in `plans/sportsnot-plan.md`).
- **Small-data reality:** each season contributes only ~15 series and ~300–400 skater-round rows. Ten seasons ≈ 150 series — regularization, shrinkage toward priors, and simple models will beat complex ones. This is why the series model composes a per-*game* model (thousands of training rows) rather than learning series outcomes directly.
- **Rules drift:** the golden-vector tests in US-002 tie the Python rules engine to `packages/utils/src/lib/utils.test.ts`. If SportsNot's scoring ever changes, the mirrored vectors must be updated deliberately.
- **Determinism:** all stochastic components (Monte Carlo, simulators, model training) take explicit seeds; artifact manifests record them.
- **Testing note:** the mandatory repo-wide gates (typecheck, lint, unit, Playwright) apply to the existing TS workspace and must remain green since `ml/` is isolated from it; Python-side quality gates (`ruff`, `mypy`, `pytest`) are additional, not replacements.

## Success Metrics

- **Projection quality (held-out seasons):** skater round-points Spearman rank correlation beats the PPG×5.5 baseline by ≥0.05; MAE beats both baselines in US-006.
- **Series model quality:** Brier score for series winners beats the "better regular-season record wins" baseline on every held-out season; series-length distribution passes a calibration eyeball test in the report.
- **Draft value:** in backtested simulated drafts across ≥3 seasons and all snake slots, the oracle's rosters score more **actual** points than greedy-VOR rosters on average, and beat random-legal rosters by a wide margin (sanity floor).
- **Usability under fire:** during a live draft, recording a pick + getting a recommendation takes <10 seconds of owner effort; `recommend` computes in <5 s.
- **Reproducibility:** any artifact can be regenerated byte-identically from its manifest.
- **The fun one:** the owner's team wins (or at least finishes top-3 in) the league. Not formally verifiable — the backtest metrics are the proxy.

## Open Questions

1. **Betting odds as a feature:** series/moneyline odds would likely dominate hand-built team features for the series model. Worth adding a (free-tier) odds source in v1.1, or keep the tool fully self-contained?
2. **Opponent model realism:** should the opponent model be fit to the actual league's historical draft logs (SportsNot stores `draft_picks`) instead of a generic greedy model? That data exists in the owner's own leagues and would sharpen survival estimates — but adds a Supabase read dependency the current scope excludes.
3. **Injury data quality:** the NHL API's injury signal is thin. Is the manual `injuries.yaml` override workflow acceptable for v1, or is a scraped injury-report source worth the fragility?
4. **Lookahead depth:** is one-step survival lookahead enough, or should v1 include full multi-round rollout (slower, possibly better)? Proposed: ship one-step as default, `--depth` flag experimental, decide after backtests.
5. **Round-1 draft-order uncertainty:** round 1 order is randomized and only known shortly before the draft. Should the cheat sheet include per-slot pre-computed strategies for all N slots (cheap to add given the simulator)?
6. **Goalie-slot tie-in to actual starting goalies:** the slot scores on team wins/shutouts regardless of which goalie plays, so v1 models teams. Should backup-goalie risk (starter injury mid-series) still be a feature of the shutout model?
