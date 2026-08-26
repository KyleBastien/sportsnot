# Draft Oracle — Implementation Contract (SPEC)

**Read this file in full before implementing any Ralph story.** It is the binding
contract for the `ml/` pipeline: the league ruleset, pinned technology choices, data
contracts, and honesty rules. The full PRD is `tasks/prd-ml-draft-optimizer.md`; where
this SPEC is silent, the PRD governs. Where both are silent, prefer the simplest thing
that satisfies the story's acceptance criteria.

---

## 1. The ruleset (normative — every simulation and score must match)

Mirrors the app code (`packages/utils/src/lib/utils.ts`,
`packages/types/src/lib/types.ts`). Golden test vectors live in
`packages/utils/src/lib/utils.test.ts`.

| Rule | Value |
| --- | --- |
| Goal / Assist | 1 pt each (equal weight) |
| Team win | 2 pts |
| Team shutout win | 4 pts, **replaces** the win's 2 (a 1-0 win = 4 pts, never 6) |
| Loss (any kind) | 0 pts |
| Goalie series points | `(wins − shutouts) × 2 + shutouts × 4` |
| Active roster | 5 F, 3 D, 1 G (the G slot is an entire NHL **team's** goaltending) |
| IR slots (if league enables) | +1 IR_F, +1 IR_D → 11 picks total, else 9 |
| League size | 2–12 managers (this league has 4: ben, judah, kyle, levi) |
| Round 1 order | randomized, snake |
| Rounds 2–4 order | standings **worst → best**, snake (points ascending) |
| Re-draft | full re-draft every round, no keepers |
| Eliminated teams | team + its players undraftable |
| IR activation | injured starter ↔ same-position IR player, points swap **retroactively** for the whole round |
| Playoffs | 4 rounds, best-of-7, home-ice pattern 2-2-1-1-1, 16→8→4→2 teams |

**NOT a rule:** replacing an eliminated player mid-round (the 2024 Trouba→Kulikov swap
in the sheets was a one-time favor). The simulator and optimizer must never assume it.

## 2. League facts

- Managers (canonical ids): `ben`, `judah`, `kyle`, `levi`. Alias: `evi` = `levi`.
- Champions: 2018 ben, 2019–2022 levi, 2023 kyle, 2024 levi, 2025 levi, 2026 ben.
- Sheet-era seasons (2024, 2025, 2026 drafts) have **three draft events**: R1, R2, and
  R3+4 combined. The app era has four. Sheet rows are **not** in pick order —
  `pick_number` exists only in the 2026 app export.
- IR slots: used in 2025, disabled for 2026.
- All sheet-era source data, its schema, and every known data correction live in
  `ml/data/raw/league-drafts/` (`SCHEMA.md`, `OPEN_QUESTIONS.md`, `APP_EXPORT.md`).
  Read those before touching parsing code (story US-006/US-007).

## 3. Pinned stack (do not relitigate)

- Python **3.12+**, managed with **uv** (lockfile committed). Package: `draft_oracle`
  under `ml/src/`.
- DataFrames: **pandas** (+ pyarrow for Parquet). Not polars.
- Models: **scikit-learn** + **LightGBM**. No neural nets, no GPUs.
- HTTP: **httpx**; response typing: **pydantic v2**.
- CLI: **typer**; terminal rendering: **rich**.
- Tests: **pytest** + **hypothesis**; lint/format **ruff**; types **mypy --strict**.
- Config/overrides: YAML via **pyyaml**.
- Seeds: every stochastic component takes an explicit seed; artifact manifests record
  them. `oracle` entry points must be deterministic given (snapshot, seed).

## 4. Directory contract

```
ml/
  SPEC.md                    ← this file
  README.md                  ← setup, commands, endpoint docs (grows per story)
  pyproject.toml, uv.lock
  src/draft_oracle/
    rules.py                 ← US-002 (scoring, snake/redraft order, roster validation)
    ingest/                  ← US-003..008 (nhl_api.py, normalize.py, odds.py,
                                league_drafts.py, entity_match.py, injuries.py)
    features/                ← US-009/010 (skater.py, team_series.py, leakage.py)
    models/                  ← US-011..016 (game_win.py, shutout.py, series_sim.py,
                                skater_rate.py, returns.py, projections.py)
    optimize/                ← US-018..023 (vor.py, simulator.py, opponents.py,
                                recommend.py, ir_value.py, slot_strategies.py)
    cli/                     ← US-017/024 (project.py, draft.py)
    backtest/                ← US-025/026 (replay.py, report.py)
  data/
    raw/                     ← gitignored EXCEPT league-drafts/
    raw/league-drafts/       ← committed sheet snapshots + app exports + docs
    features/                ← versioned matrices (gitignored)
    overrides/               ← injuries.yaml, name_overrides.yaml, manager_aliases.yaml
  artifacts/                 ← gitignored except backtests/*/report.md and manifests
```

## 5. External data sources (decided — do not re-evaluate)

**NHL API** — base `https://api-web.nhle.com`. Known endpoints (verify shapes at
implementation; isolate all URLs in `ingest/nhl_api.py`):
- Player game log: `/v1/player/{playerId}/game-log/{season}/{gameType}` (season like
  `20252026`; gameType 2 = regular season, 3 = playoffs)
- Team roster: `/v1/roster/{teamAbbrev}/{season}`
- Team season schedule/results: `/v1/club-schedule-season/{teamAbbrev}/{season}`
- Scores by date: `/v1/score/{YYYY-MM-DD}`; standings: `/v1/standings/{YYYY-MM-DD}`
- Playoff bracket: `/v1/playoff-bracket/{year}`
- Bulk skater stats (separate host): `https://api.nhle.com/stats/rest/en/skater/summary`
  with `cayenneExp=seasonId=20252026 and gameTypeId=3` — prefer this for bulk pulls.

**Odds** — The Odds API (`https://api.the-odds-api.com/v4`), free tier. Sport key
`icehockey_nhl`; historical via `/v4/historical/...` as quota allows. Key from
`ODDS_API_KEY` env var (gitignored `ml/.env`). Everything must run with `--no-odds`.

**Injuries** — ESPN public JSON:
`https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/injuries` (player detail via
ESPN core API as needed). Final authority: `ml/data/overrides/injuries.yaml`.

## 6. As-of & leakage rules (hard requirements)

- A feature for playoff round N may use ONLY games played before round N started.
- Training/evaluation splits are temporal: a held-out season contributes nothing to
  the models evaluated on it.
- Automated leakage tests (features/leakage.py) must fail the build on violation.
- Backtest inputs for round N must be re-derivable without round-N data; the harness
  asserts this.

## 7. Honesty rules (non-negotiable)

- Metric targets (beat a baseline, calibration within ±25%, ≥98% match rate) are
  **goals to attempt, then report truthfully** — a miss is reported in the committed
  report with the honest number, never forced. Do NOT weaken baselines, change splits,
  reroll seeds, relabel data, or reinterpret a criterion to manufacture a pass.
- If a story's metric target is missed after a genuine attempt: write the honest
  report, note the miss and one plausible improvement in progress.txt, and move on.
  A missed metric target with an honest report satisfies the story; a fabricated pass
  never does.
- Network calls in tests are forbidden — fixtures only. Ingestion code paths must
  degrade loudly (clear errors), never silently.

## 8. Modeling constraints worth remembering

- Small data: ~150 series and ~350 skater-round rows per season. Prefer regularized,
  shrunken, simple models; compose per-game models rather than learning per-series.
- Opponent model: sheet-era seasons expose final rosters + snake order only (no pick
  sequence); the 2026 app export has true `pick_number`. Fit accordingly.
- Only in-round production matters (full re-draft): no cross-round elimination risk.
- The goalie slot is valued by expected wins + shutout upside via the series-outcome
  distribution, through the rules engine — never by direct "goalie fantasy points".
