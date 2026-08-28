# Draft Oracle (`ml/`)

An isolated, [uv](https://docs.astral.sh/uv/)-managed Python project that builds an ML
draft optimizer for the SportsNot NHL playoff fantasy league. It lives entirely inside
`ml/` and is **not** part of the Nx/TypeScript workspace — it has no `package.json`, is
skipped by ESLint/Prettier/`tsc`, and does not appear in the Nx project graph. Running
`yarn nx ...` targets is unaffected by anything here.

## ⚠️ Read the contract first

**[`SPEC.md`](./SPEC.md) is the binding implementation contract** — the league ruleset,
pinned technology stack, data contracts, and the leakage/honesty rules. Read it in full
before changing any code under `ml/`. Where `SPEC.md` is silent, the PRD
(`tasks/prd-ml-draft-optimizer.md`) governs.

## Requirements

- Python **3.12+**
- [`uv`](https://docs.astral.sh/uv/getting-started/installation/)

## Setup

```bash
cd ml
uv sync            # creates .venv and installs runtime + dev dependencies from uv.lock
```

Secrets (optional; every stage runs without them) go in a gitignored `ml/.env`:

```dotenv
ODDS_API_KEY=...   # The Odds API free tier (live odds only; use --no-odds to skip)
```

## Commands

All commands run from the `ml/` directory.

| Task            | Command                                  |
| --------------- | ---------------------------------------- |
| Install deps    | `uv sync`                                |
| Run tests       | `uv run pytest`                          |
| Lint            | `uv run ruff check .`                     |
| Format          | `uv run ruff format .`                    |
| Format check    | `uv run ruff format --check .`            |
| Type check      | `uv run mypy`                             |
| CLI entry point | `uv run oracle version`                  |

## Package layout

The `draft_oracle` package (under `src/`) is organized by pipeline stage. Each
subpackage maps to the stories called out in `SPEC.md §4`:

```
src/draft_oracle/
  rules.py       scoring, snake/re-draft order, roster validation (US-002)
  ingest/        NHL API, odds, league drafts, entity match, injuries (US-003..008)
  features/      skater + team/series feature engineering, leakage guard (US-009/010)
  models/        win, shutout, series sim, skater rate, returns, projections (US-011..016)
  optimize/      VOR, draft simulator, opponents, recommend, IR value (US-018..023)
  cli/           batch projection + interactive draft assistant (US-017/024)
  backtest/      replay engine + reporting (US-025/026)
```

## Pipeline stages

1. **Rules engine** (`rules.py`) — mirrors the app's scoring and draft order exactly.
   Public API: `player_points`, `goalie_series_points`, `goalie_game_points`,
   `snake_order`, `redraft_order`, `roster_composition`, and `validate_roster`
   (with `RosterSlot` / `RosterValidation`). These are the byte-for-byte mirror of
   `packages/utils/src/lib/utils.ts`; golden vectors in `tests/test_rules.py` are
   copied from `utils.test.ts` to catch cross-language drift.
2. **Ingest** — pull and normalize NHL stats, betting odds, injuries, and league draft
   history into dated snapshots. Committed raw sources live under `data/raw/`; live
   pulls are cached and gitignored. The NHL client is documented below.
3. **Features** — build as-of feature matrices with automated leakage guards.
4. **Models** — per-game win/shutout models compose into a best-of-7 series simulator;
   skater rate + return-time models produce per-round point projections.
5. **Optimize** — value over replacement, positional scarcity, a rules-enforcing draft
   simulator, an opponent model, and a multi-step pick recommender.
6. **Backtest** — replay past playoffs with a strict leakage guard and report against
   baselines and the league's real drafts.

## NHL API client (`ingest/nhl_api.py`)

`NHLApiClient` is the **only** place NHL URLs live (SPEC §5). It fetches politely
(configurable delay), retries with exponential backoff, validates every response with
pydantic, and caches raw JSON under `data/raw/nhl-api/` keyed by endpoint + params — a
cache hit skips the network entirely, so ingestion is repeatable and tests never touch
the wire (inject an `httpx.MockTransport` + fixtures).

Typed adapter methods (hosts: `api-web.nhle.com/v1` and `api.nhle.com/stats/rest/en`):

| Method | Endpoint | Returns |
| --- | --- | --- |
| `player_game_log(id, season, gameType)` | `/player/{id}/game-log/{season}/{gameType}` | `PlayerGameLog` |
| `player_info(id)` | `/player/{id}/landing` | `PlayerLanding` (position, status) |
| `team_roster(abbrev, season)` | `/roster/{abbrev}/{season}` | `TeamRoster` |
| `club_schedule_season(abbrev, season)` | `/club-schedule-season/{abbrev}/{season}` | `ClubScheduleSeason` (results + scores) |
| `scores_by_date(date)` | `/score/{YYYY-MM-DD}` | `DailyScores` |
| `playoff_bracket(year)` | `/playoff-bracket/{year}` | `PlayoffBracket` (series metadata) |
| `skater_summary(season, gameType)` | stats-rest `/skater/summary` | `SkaterSummaryResponse` (bulk; 10k row cap) |

`season` is the concatenated form (e.g. `20252026`); `gameType` is `2` (regular) or `3`
(playoffs). The client is a context manager and owns its `httpx.Client` unless one is
injected. Endpoint knowledge must never leak outside this module.

## Data & artifacts

- `data/raw/` — gitignored **except** the committed `league-drafts/`, `odds-archive/`,
  and `nhl-archive/` snapshots described in `SPEC.md §5`.
- `data/features/` — generated feature matrices (gitignored).
- `data/overrides/` — hand-maintained YAML overrides (injuries, name/alias maps).
- `artifacts/` — model artifacts (gitignored) except committed backtest
  `report.md` files and manifests under `artifacts/backtests/`.

## Determinism

Every stochastic component takes an explicit seed and records it in its artifact
manifest. `oracle` entry points must be deterministic given `(snapshot, seed)`.
