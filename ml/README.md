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
| Normalize data  | `uv run oracle normalize`                |
| Freeze snapshot | `uv run oracle snapshot`                 |
| List snapshots  | `uv run oracle snapshot --list`          |
| Build odds      | `uv run oracle odds`                     |
| Skip odds       | `uv run oracle odds --no-odds`           |
| League drafts   | `uv run oracle league-drafts`            |
| Match drafts    | `uv run oracle match-drafts`             |
| Build injuries  | `uv run oracle injuries`                 |
| Injuries offline| `uv run oracle injuries --no-fetch`      |
| Train win model | `uv run oracle train-game-win`           |
| Win model (stat)| `uv run oracle train-game-win --no-odds` |
| Train shutout   | `uv run oracle train-shutout`            |
| Eval series sim | `uv run oracle eval-series-sim`          |
| Return-time     | `uv run oracle train-return-time`        |
| Project skaters | `uv run oracle project-skaters`          |
| Batch projection| `uv run oracle project --season 2026 --round 1` |
| Projection + IR | `uv run oracle project --season 2026 --round 1 --managers 4 --ir` |

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

## Normalized tables (`ingest/normalize.py`)

Raw NHL responses fold into five documented Parquet tables under `data/normalized/`
(gitignored, regenerated). Historical seasons **2015-16 … 2025-26** load from the
committed archive in `data/raw/nhl-archive/` (read its `PROVENANCE.md` first); the live
NHL API is reserved for the current season and gaps. Position codes collapse per SPEC §1:
`C`/`L`/`R` → `F`, `D` → `D`, and goalies (`G`) are excluded from the skater pool.

```
uv run oracle normalize            # build/refresh data/normalized/*.parquet (idempotent)
uv run oracle normalize --force    # rebuild even when sources are unchanged
uv run oracle snapshot             # freeze a dated copy under snapshots/<id>/
uv run oracle snapshot --list      # list frozen snapshot ids
```

Ingestion is **idempotent and incremental**: a `_manifest.json` records each source
file's size, so a re-run with unchanged sources is a no-op, and every table dedups on
its natural key (below). A **snapshot** copies the current tables into
`data/normalized/snapshots/<snapshot_id>/` (id defaults to a UTC timestamp) so
downstream stages can pin reproducible data.

### `skater_games` — one row per skater-game (key: `game_id` + `player_id`)

`season_id`, `game_type_id`, `game_id`, `game_date`, `player_id`, `player_name`,
`position_code` (raw NHL code), `position` (`F`/`D`), `shoots_catches`, `team_abbrev`,
`opponent_team_abbrev`, `home_road`, `goals`, `assists`, `points`, `shots`,
`toi_seconds` (time on ice, **seconds**), `pp_goals`, `pp_points`, `sh_goals`,
`sh_points`, `ev_goals`, `ev_points`, `plus_minus`, `penalty_minutes`,
`game_winning_goals`, `ot_goals`, `shooting_pct`, `faceoff_win_pct`. Goalies excluded.

### `team_games` — one row per team-game (key: `game_id` + `team_id`)

`season_id`, `game_type_id`, `game_id`, `game_date`, `team_id`, `team_abbrev`,
`team_full_name`, `opponent_team_abbrev`, `home_road`, `goals_for`, `goals_against`,
`wins`, `losses`, `ot_losses`, `regulation_and_ot_wins`, `wins_in_regulation`,
`wins_in_shootout`, `points`, `team_shutouts`, `win` (derived), `shutout_win` (derived:
a win with `goals_against == 0`). The archive names a row's own team by `team_id` but the
opponent by abbreviation (PROVENANCE §2), so `team_abbrev` is derived by pairing each
game's two mirror rows.

### `series` — one row per playoff series (key: `year` + `series_letter`)

`year` (season ending year), `season_id`, `series_letter`, `series_abbrev`,
`playoff_round`, `top_seed_team_id`, `top_seed_abbrev`, `top_seed_wins`,
`bottom_seed_team_id`, `bottom_seed_abbrev`, `bottom_seed_wins`, `winning_team_id`,
`losing_team_id`. Parsed from the committed `bracket-<year>.json` files.

### `players` — one row per skater (key: `player_id`)

`player_id`, `player_name`, `last_name`, `birth_date`, `position_code`, `position`,
`shoots_catches`, `height`, `weight`, `birth_country_code`, `nationality_code`,
`draft_year`, `draft_round`, `draft_overall`, `current_team_abbrev`, `last_season_id`.
Goalies excluded; each player keeps the row from their most recent season.

### `teams` — one row per team (key: `team_id`)

`team_id`, `team_abbrev`, `team_full_name` (carries diacritics, e.g. `Montréal
Canadiens`). Built from `team_games` (latest full name per id).

## Betting odds (`ingest/odds.py`)

Turns raw moneylines into de-vigged implied win probabilities in an `odds`
table keyed to games. Read `data/raw/odds-archive/PROVENANCE.md` in full before
touching the parsers — it documents every trap handled here.

```bash
uv run oracle odds              # build data/normalized/odds*.parquet from committed archives
uv run oracle odds --no-odds    # skip odds entirely; the stat-only path is unaffected
```

**Sources** (all committed, offline; `build_odds_table` never hits the network):

| Source (`source` col) | Coverage | Prices |
| --- | --- | --- |
| `sbr_close` (SBR workbooks) | 2016-17 – 2021-22 complete, 2022-23 partial | both-side Open/Close — **preferred** |
| `kaggle_espn` (Kaggle/ESPN) | 2004 – Dec 2025 | favorite-side only |
| `espn_completion` (ESPN API) | Dec 2025 – Jun 2026 incl. 2026 playoffs | favorite-side only |

**De-vigging** (`SPEC.md §5`):

- Two-sided prices (SBR) use the **proportional** method: each raw implied
  probability (`1/decimal`) is divided by their sum (the overround), so fair
  probabilities sum to 1 while preserving their ratio.
- Favorite-only prices remove a documented **standard two-way overround**
  (`STANDARD_OVERROUND = 1.045`, ~4.5% hold) from the favorite's raw implied
  probability; the underdog is the complement. **No underdog American price is
  ever fabricated** — only probabilities are produced.

**Playoffs** are tagged by the real per-season windows (PROVENANCE §5), not a
fixed April–June rule (the 2020 bubble ran Aug–Sep; 2021 ran May–Jul). The 2021
window still overlaps a few regular-season days — a documented limitation of
date-window tagging. September games outside a playoff window are treated as
preseason and dropped.

**Consolidation** collapses the per-source rows to one best row per game
(`odds.parquet`); every source row is also kept in `odds_by_source.parquet`.
Sources are matched on (season, away id, home id) with a ±1 day tolerance
(Kaggle/ESPN dates are UTC, one calendar day ahead of SBR's local dates), at
most one row per source per game so adjacent same-matchup games never merge. SBR
Close wins ties; the de-vigged favorite probability of every covering source is
cross-validated into `xval_delta`. Games present but priceless are flagged
(`covered = False`), never imputed.

**Key columns:** `source`, `season_end_year`, `game_date`, `is_playoff`,
`neutral_site`, `away_team_id`/`home_team_id`, `away_ml`/`home_ml` (favorite-only
sources leave the underdog `null`), `favorite_side`, `both_sides`, `covered`,
`away_implied`/`home_implied` (sum to 1 when covered), `devig_method`,
`overround`, `game_key`, plus `xval_delta` and `source_count` on `odds.parquet`.

**Live / future odds** (never used for training; future games only):

- `OddsApiClient` — The Odds API free tier (`icehockey_nhl`), current/upcoming
  game moneylines (`h2h`) and series/outright markets where offered. The key is
  read from `ODDS_API_KEY` (gitignored `ml/.env`) and never committed; the paid
  historical endpoints are never called. The free tier is quota-capped (commonly
  500 requests/month); each response's `x-requests-remaining` / `x-requests-used`
  headers are captured on the client. Caching + rate-limiting mirror the NHL API
  client, so repeated calls reuse the on-disk cache.
- `EspnGameOddsClient` — ESPN's public `summary` endpoint (`pickcenter` block,
  favorite-only) for individual future games; the same source as the committed
  2025-26 completion, so semantics match. ESPN 403s browser-like User-Agents, so
  the default httpx UA is used.

## League drafts (`ingest/league_drafts.py`)

Parses the committed league draft-history snapshots in
`data/raw/league-drafts/` into two Parquet tables. **Read that directory's
`SCHEMA.md` and `OPEN_QUESTIONS.md` in full before touching the parsers** — all
interpretation of the raw sheets lives there.

```bash
uv run oracle league-drafts    # build data/normalized/league_{picks,champions}.parquet
```

**Sources** (all committed, offline):

- Three Google-Sheet exports (`sheet1/2/3__*.csv`) — the 2026 / 2025 / 2024
  seasons. Sheet-era seasons have **three** draft events (`R1`, `R2`, `R3_4`);
  playoff rounds 3 and 4 were drafted together. `sheet1__round-3-4.csv` is a
  stale 2025 duplicate and is deliberately **excluded** (SCHEMA §4.3).
- `app-export-2026__*.csv` — the Supabase export of the in-app 2026 season (two
  leagues: The Gemmell Cup + Press Play-offs). Preserves the true `pick_number`.
  If absent, parsing proceeds on the sheets alone and the report says so.

**`league_picks` table** — one row per drafted roster slot. Key columns:
`season`, `source` (`sheet`/`app`), `league_name`, `draft_event`, `manager`
(canonical id), `snake_slot` (1–4 from each tab's order list; null where a tab
records none), `pick_number` (app only — sheets are **not** in pick order),
`position` (F/D/G/IR_F/IR_D), `slot_label`, `player_or_team_name`,
`corrected_name`, `points_for_round`/`points_when_drafted`/`current_total_points`,
`status` (Dropped/Activated/Not playing), `points_excluded`, `ir_activated`,
`swap_partner`, `note`, `is_scored` (false for the unscored 2026 sheet rosters).

**Documented corrections applied** (OPEN_QUESTIONS.md):

- The `Makar`/`Oilers` row (Levi, 2024 R3+4) is Evan Bouchard → `corrected_name`.
- The Trouba→Kulikov row is parsed **as recorded** (Kulikov, +3 in `note`); the
  simulator/optimizer must never model mid-round substitution as a mechanic.
- The two formula-only IR swaps in `sheet2__round-3-4.csv` (Ben Reinhart→Verhaeghe,
  Judah Hyman→Brown) are flagged `points_excluded` / `ir_activated` despite
  carrying no text flag.
- `Dropped` / `Not playing` starters are points-excluded and paired with the
  same-position `Activated` IR row in the same block (`swap_partner`).
- `Evi` folds to `levi`; app usernames map to canonical ids
  (`nuttguy`=kyle, `bentunigold`=ben, `judah18`=judah, `gemmell.levi`=levi).

**`league_champions` table** — `year`, `champion` for 2018–2026 (2026 Ben is
owner-confirmed, scored in the app, not a sheet).

Parsers **fail loudly** (`ValueError`) if a committed file's header, block count,
or slot labels do not match `SCHEMA.md`.


## Entity matching (`ingest/entity_match.py`)

Resolves every parsed `league_picks` row to a stable NHL id and emits the final
`league_draft_picks` table. Depends on both `oracle league-drafts` (for
`league_picks.parquet`) and `oracle normalize` (for `players.parquet` /
`teams.parquet`).

```bash
uv run oracle match-drafts     # build data/normalized/league_draft_picks.parquet + match-rate report
```

**How ids are assigned:**

- **Skater slots** (`F`/`D`/`IR_F`/`IR_D`) → NHL `player_id` from
  `players.parquet` via normalized fuzzy name matching. `normalize_name` strips
  accents (`Montréal`→`montreal`), folds case, and drops punctuation so initials
  align (`J.T. Miller`=`JT Miller`). Match order: manual override → exact →
  high-confidence fuzzy (`difflib` ratio ≥ `HIGH_CONFIDENCE`=0.88) → unique
  last-name fallback (bare `McDavid`) → low-confidence fuzzy (≥0.80, flagged for
  review) → unresolved. Same-name collisions (there are two `Sebastian Aho`s)
  are disambiguated by the pick's roster position.
- **Goalie / team slots** (`G`) → NHL `team_id` from `teams.parquet` — a goalie
  pick is a bet on a team's goalie situation, so the id is the team. Resolution
  extends `odds.resolve_team_id` (city / full name / abbrev) with a nickname
  fallback (`Panthers Goalie`→FLA, `Maple Leafs`→TOR).
- **Managers** fold to a canonical id across seasons via
  `data/overrides/manager_aliases.yaml` (`evi`=`levi`, app usernames → canonical).

**Overrides (`data/overrides/`, committed):**

- `manager_aliases.yaml` — canonical id → alias list; the binding manager map.
- `name_overrides.yaml` — `players`/`teams` maps of raw name → id for anything
  the matcher misses. Overrides take precedence. Per the honesty rule (SPEC §7),
  gaps are closed by **adding overrides, never by dropping rows or lowering the
  bar**. The committed 2024–2026 snapshots match at **100%** via fuzzy matching,
  so both maps ship empty.

**`league_draft_picks` table** — the `league_picks` provenance (season, source,
draft_event, manager, snake_slot, pick_number, position, slot_label, points
fields, status flag) plus `matched_name`, `player_id` (skaters), `team_id`
(goalie/team; also best-effort associated team for skaters), and match
diagnostics (`match_method`, `match_confidence`, `needs_review`).

The command prints a **per-season match-rate report** (matched/unmatched/review
counts). Low-confidence or unresolved picks are written to
`league_draft_picks_review.csv` for human review.

## Injuries (`ingest/injuries.py`)

Per-player injury status from ESPN's public NHL JSON, with a manual override
file as the final authority (SPEC §5). Current status only — historical injury
pulls are forbidden (ESPN resolves old `injuries` blocks against today's
rosters; return-time calibration is derived from absence spells in US-015).

```bash
uv run oracle injuries              # fetch ESPN feed -> data/normalized/injuries.parquet
uv run oracle injuries --no-fetch   # offline: last-known table + overrides only
```

**Source** — `EspnInjuriesClient` (cache + retry + injectable `httpx.Client`,
mirrors `NHLApiClient`; no key, default httpx UA since ESPN 403s browser UAs):

- **Injuries feed** —
  `https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/injuries`. Shape:
  `{"injuries": [ {team group} ]}`; each team group has `id` / `displayName` /
  `abbreviation` and a nested `injuries` list. Each injury entry carries
  `status` (`"Out"` / `"Day-To-Day"` / `"Injured Reserve"`), `date`, an
  `athlete` block (`id` / `fullName` / `position.abbreviation`), a `type`
  object (`name` like `INJURY_STATUS_OUT`), and `details` (`type` body-part +
  `returnDate`).
- **Core athlete detail** —
  `https://sports.core.api.espn.com/v2/sports/hockey/leagues/nhl/athletes/{id}`,
  fetched only to fill a rare position/name gap (`client.core_athlete(id)`).

**`injuries` table** — one row per player: `player_id` (ESPN athlete id),
`player_name`, `position`, `team_id` (stable NHL id via `resolve_team_id`),
`team_abbrev`, normalized `status` (`out` / `ir` / `day_to_day` / `healthy`),
`status_raw`, `return_date`, `detail`, `as_of_date`, `source`
(`espn` / `override` / `last_known`).

**Overrides — final authority** — `data/overrides/injuries.yaml` merges *over*
the source. Each `overrides:` entry matches by `espn_id` (exact) else `player`
name (accent/punctuation-insensitive); a match rewrites status / return date /
detail, `remove: true` deletes the row, and an unmatched entry is injected as a
new row. Ships empty.

**Graceful degradation** — a source failure (or `--no-fetch`) reuses the
last-known `injuries.parquet` plus overrides and emits a warning instead of
crashing (`InjuriesResult.degraded` / `.warnings`).

## Skater features (`features/skater.py`, `features/leakage.py`)

As-of skater feature engineering for the projection model (US-009). One row per
skater per playoff round, computed **as of the round start** so no feature ever
reads a game the model is about to project.

```python
from draft_oracle.features import build_round_feature_matrix, write_feature_matrix

matrix = build_round_feature_matrix(
    skater_games,
    players,
    team_games,
    season_id=20232024,
    round_start_dates={1: "2024-04-20", 2: "2024-05-05", 3: "2024-06-01", 4: "2024-06-08"},
)
write_feature_matrix(matrix)  # -> data/features/skater-v1/skater_features.parquet
```

**Leakage guard (SPEC §6, hard requirement)** — every game input funnels through
`features/leakage.py`: `as_of(df, cutoff)` keeps only games *strictly before* the
round start (the cutoff is exclusive — a game on the start date belongs to the
round) and `assert_no_leakage` raises `LeakageError` on any game at/after the
cutoff, failing the build. `test_features.py` asserts a future high-scoring game
never moves an as-of rate.

**Feature columns** (`FEATURE_COLUMNS`, keyed by feature-set version
`skater-v1`): regular-season `goals/assists/points_per_game`, last-25-game rates
(`*_l25`), `pp_points_per_game` + `pp_point_share`, `avg_toi_seconds`,
`shots_per_game`, `shooting_pct`, `age_years`, `linemate_ppg` (leave-one-out
teammate quality), and `team_goals_for_per_game`. Each is a unit-tested pure
function with a docstring stating its as-of semantics.

**Documented proxies** — the committed archive has no power-play *time* column,
so "power-play time share" is proxied by power-play *production* (`pp_point_share`
= PP points / total points). Regular-season aggregates use only
`game_type_id == 2` games; the last-N window uses the most recent games of any
type within the season before the cutoff.

## Team/series features (`features/team_series.py`)

As-of team/series feature engineering for the per-game win model and series
simulator (US-010). One row per team, computed **as of a playoff-round (series)
start**, sharing the same leakage guard as the skater features.

```python
from draft_oracle.features import build_team_series_features, EloConfig

matrix = build_team_series_features(
    team_games,
    season_id=20232024,
    as_of_date="2024-04-20",
    playoff_round=1,
    matchups=matchups,  # optional: opponent_team_abbrev, home_ice, series price
    odds=odds,  # optional: normalized odds table for market features
    injuries=injuries,  # optional (CURRENT round only — never historical)
)
```

**Feature groups** (`TEAM_FEATURE_COLUMNS`, keyed by `team-series-v1`): team form
(`goal_differential_per_game`, `goals_for/against_per_game`, game-averaged
`power_play_pct` / `penalty_kill_pct`, `shots_for/against_per_game`, `rest_days`,
`days_between_games`), `elo_rating` (cross-season, unit-tested `expected_score` /
`update_rating` + season regression), goaltender situation
(`starter_save_pct_season` / `_l15`, `team_shutout_rate`,
`starter_unavailability_risk`), market (`market_implied_win_prob` +
`market_available`, `series_implied_win_prob` + `series_market_available`), and
round-context/matchup (`opponent_team_abbrev`, `home_ice_advantage`,
`head_to_head_win_pct`, `expected_opponent_strength`, each with a `*_available`
missing-flag).

**Documented proxies (honesty, SPEC §7)** — the committed archive has **no
goalie-level game rows**, so per-goalie save % cannot be computed. The league's
goalie slot is a whole *team's* goaltending (SPEC §1), so save % is a **team-level
proxy** `1 - GA / shots-against`; `backup_save_pct` is left missing +
`goalie_split_available == False`, never fabricated. `power_play_pct` /
`penalty_kill_pct` are **game-averaged** single-game rates, not opportunity
weighted. The injuries table is **current-only**, so
`starter_unavailability_risk` is meaningful for the upcoming round only. Elo is
replayed game-by-game across seasons (`compute_elo_ratings`) with a between-season
regression toward the mean; the market join maps `season_id % 10000` to the odds
table's `season_end_year`.

## Per-game win model (`models/game_win.py`)

Calibrated single-game `P(home beats away)` model (US-011), home/away aware,
trained on historical regular-season **and** playoff games. It is the sharpest
per-game estimate the series simulator (US-013) rests on.

```python
from draft_oracle.models import train_game_win_model

result = train_game_win_model(team_games, odds=odds)  # odds optional (stat-only)
p = result.model.predict_matchup(home_snapshot, away_snapshot, is_playoff=True)
```

```bash
uv run oracle train-game-win            # train + write report.md/manifest.json
uv run oracle train-game-win --no-odds  # stat-only (drop the market feature)
```

**Features** are home-minus-away differences (`STAT_FEATURE_COLUMNS`): a
cross-season `elo_diff` (reusing `team_series` Elo), in-season regular-season
`goal_diff`/`goals_for`/`goals_against`/`win_pct`/`points_per_game` diffs, and an
`is_playoff` flag. The market variant (`MARKET_FEATURE_COLUMNS`) adds the
de-vigged `market_home_prob` + a `market_available` flag; a missing price imputes
a neutral `0.5` and clears the flag, so the model **runs correctly in stat-only
mode**. Pre-game state is accumulated in a single chronological pass, so a game
can never read its own (or a later) result — leakage-free by construction.

**Selection + evaluation** — logistic regression vs. LightGBM, chosen by
**validation Brier**; the winner is refit on train+validation and scored on the
**held-out latest seasons** against two fixed baselines (coin flip; higher
regular-season points wins). Splits are strictly temporal (SPEC §6) and the seed
is fixed. The committed report at `artifacts/models/game-win/report.md` (+
`manifest.json`) prints the held-out Brier, the market-vs-stats **ablation**, and
the baseline comparison **honestly** — a missed target is reported, never forced
(SPEC §7).

## Best-of-7 series simulator (`models/series_sim.py`)

Composes the per-game win model (US-011) and shutout model (US-012) into a full
best-of-7 series-outcome distribution (US-013). Every playoff round uses the
**2-2-1-1-1** home-ice pattern (`HOME_ICE_PATTERN`): the higher seed hosts games
1, 2, 5, 7; the lower seed hosts 3, 4, 6. The distribution is enumerated
**exactly** over all series paths (`2**7` outcomes) — deterministic, no seed;
a seeded `simulate_series_monte_carlo` exists only to cross-check the enumeration.

```python
from draft_oracle.models import simulate_series

outcome = simulate_series(p_a_home=0.62, p_a_away=0.48, shutout_prob_a=0.12, shutout_prob_b=0.09)
outcome.p_a_win_series  # P(higher seed wins the series)
outcome.length_probs  # {4:.., 5:.., 6:.., 7:..}, sums to 1
outcome.e_wins_a  # E[wins] for the higher seed
outcome.e_goalie_points_a  # E[goalie-slot points] through the rules engine
```

```bash
uv run oracle eval-series-sim   # calibrate on held-out seasons + write report/manifest
```

Per series it yields `P(win series)` per team, the 4/5/6/7-game length
distribution, `E[wins]`, `E[games]`, and `E[goalie-slot points]`. Goalie points
are scored **through the rules engine** (`expected_goalie_points`): a win is worth
`WIN_POINTS` and a shutout win *replaces* it with `SHUTOUT_POINTS`, so
`E[pts] = E[wins] * (2 + 2 * P(shutout | win))` — exactly the mean of
`rules.goalie_series_points`.

**Calibration** (`evaluate_series_sim_from_normalized`) fits the win + shutout
models on the seasons **before** the held-out set (test-season series never touch
training, SPEC §6), replays each historical series (`series.parquet`) through the
simulator, and writes `artifacts/models/series-sim/report.md` (+ `manifest.json`):
a reliability curve + Brier for series winners (vs. higher-seed and coin-flip
baselines), the predicted-vs-actual series-length distribution, and
predicted-vs-actual shutouts per round. Pre-series team snapshots are frozen in a
single leakage-free chronological pass at each matchup's first playoff game.
Metrics are reported **honestly** — the held-out sample is small (~30-40 series),
so numbers are printed as measured (SPEC §7).

## Injury return-time model (`models/returns.py`)

Prices **availability** for injured skaters — `P(available for game k)`, k=1..7 of
the upcoming best-of-7 round (US-015). ESPN cannot supply *historical* injuries
(old game summaries resolve `injuries` against today's rosters — leakage, SPEC §5),
so the model is calibrated on **absence spells** derived from the committed NHL
archive: for each established skater, a maximal bookended run of consecutive team
games missed *between two appearances* is one real missed-game spell.

```python
from draft_oracle.models import derive_absence_spells, fit_return_time_model, project_availability

spells = derive_absence_spells(skater_games, team_games)  # 10k+ real spells, 11 seasons
model = fit_return_time_model(spells)
model.availability_curve("out")  # [P(avail g1), ..., P(avail g7)], non-decreasing
model.availability_multiplier("ir")  # haircut in [0,1] applied to expected games played
```

```bash
uv run oracle train-return-time   # calibrate on archive spells + write report/manifest
```

The archive supplies the return-timing **shape**; a documented status map
(`STATUS_MEAN_GAMES`: day-to-day≈1, out≈3, IR≈8 games) supplies the **location**
(the archive has no status label — an explicit assumption, SPEC §7). Healthy-scratch
noise is filtered with documented guards (min spell length, min appearances, min
median TOI). Calibration holds out the newest seasons and reports predicted-vs-observed
spell survival honestly. An `injuries.yaml` entry may pin `return_game` to override the
model curve. `project_availability` yields per-player `p_available_g1..g7`,
`expected_games_available`, and the `availability_multiplier` haircut.

## Skater round-point projections (`models/projections.py`)

Composes the per-game production rate (US-014), the best-of-7 series-length
distribution (US-013), and the availability haircut (US-015) into a per-skater,
per-round fantasy-point projection with an uncertainty band (US-016). Quantiles come
from a **seeded Monte Carlo**: draw a series length from the team's length
distribution, then per game draw availability (Bernoulli on the US-015 curve) and,
when available, per-game points from `Poisson(pts_per_game)`.

```python
from draft_oracle.models import project_skater_round

proj = project_skater_round(
    pts_per_game=0.8,
    length_probs={4: 0.1, 5: 0.3, 6: 0.35, 7: 0.25},  # from the series simulator
    availability_curve=[0.0, 0.5, 1.0, 1.0, 1.0, 1.0, 1.0],  # optional US-015 haircut
    seed=20260827,
)
proj.expected_points, proj.p10, proj.p50, proj.p90
proj.pts_per_game, proj.expected_games  # decomposition
```

```bash
uv run oracle project-skaters   # evaluate on held-out seasons + write report/manifest
```

Each projection is reproducible from `(seed, season, round, player)` because the
per-skater RNG is seeded deterministically from those keys. The committed report
holds out the newest seasons, trains the sub-models only on earlier seasons
(leakage-free, SPEC §6), and reports MAE + Spearman of the projected round points vs.
actual against two fixed baselines: (a) reg-season points/game x 5.5 games and (b)
the player's previous-round fantasy points. Misses are printed honestly (SPEC §7).
Historical rounds have no injury feed, so the availability haircut is a no-op (1.0)
in the backtest; it only bites at live projection time.

## Batch projection artifact (`projection_artifact.py`)

Produces a self-contained, **precomputed** prediction artifact for one upcoming
round so drafting never depends on live inference (US-017). The bracket is read from
the normalized `series` table, so eliminated teams (and their players) are excluded
automatically. Sub-models (per-game win, shutout, skater production) train only on
games strictly **before** the round start; leakage-free pre-series team snapshots are
frozen at the round start.

```bash
uv run oracle project --season 2026 --round 1
# writes artifacts/2026-r1/{skaters,teams}.{parquet,csv} + cheatsheet.md + run_manifest.json
uv run oracle project --season 2026 --round 1 --managers 4 --ir   # IR-slot league
```

- `skaters.{parquet,csv}` — `player_id, player_name, team_abbrev, position (F/D),
  expected_points, p10/p50/p90, pts_per_game, expected_games,
  availability_multiplier, injured, low_confidence`.
- `teams.{parquet,csv}` — `team_id, team_abbrev, opponent_abbrev, is_top_seed,
  playoff_round, p_series_win, e_wins, e_games, e_goalie_points (goalie slot),
  e_shutout_wins` (goalie slot = a whole team's goaltending, SPEC §1).
- `cheatsheet.md` — the VOR draft board (US-018): every skater and team priced by
  value over replacement, sorted descending. See below.
- `run_manifest.json` — snapshot id, every sub-model version, feature version, git
  SHA, seeds, the VOR scarcity summary, and a UTC timestamp.

The wall-clock timestamp and git SHA live **only** in `run_manifest.json`; the
Parquet payload is byte-identical across reruns on the same snapshot (fixed seeds +
deterministic ordering). `--no-refresh` skips the idempotent ingest step (offline);
`--snapshot <id>` pins a frozen snapshot under `data/normalized/snapshots/`.

## VOR, positional scarcity & cheat sheet (`optimize/vor.py`)

Projections rank players *within* a position; VOR (value over replacement) puts a
forward, a defenseman, and a goalie/team slot on one comparable axis so the draft
board is cross-position (US-018). Replacement level is a pure function of league
size `N` and the roster shape (SPEC §1 — `5F/3D/1G` active, `+1 IR_F/+1 IR_D` with
IR):

- Forwards: the `(5N + 1)`-th ranked F (`(6N + 1)`-th with `--ir`).
- Defensemen: the `(3N + 1)`-th ranked D (`(4N + 1)`-th with `--ir`).
- Goalie/team slot: the `(N + 1)`-th ranked team (IR adds no goalie slot).

When demand exceeds supply (e.g. the final round with only two teams alive, or a
tiny pool), there is no free replacement, so the level falls back to `0.0` and every
asset prices at its full projection. `VOR = expected_points − replacement_level`.
`--managers` (2–12) and `--ir/--no-ir` set the replacement levels and change the
`cheatsheet.md` layout (injured skaters are tagged `IR?` with IR, `OUT` without).

## Draft simulator & fallback opponent (`optimize/simulator.py`)

The optimizer needs an engine to roll out on: a faithful re-draft that lookahead
can push picks through (US-019). `DraftState` enforces the full ruleset via
`draft_oracle.rules` — snake order from `snake_order`, per-position limits
(`5F/3D/1G`, `+1 IR_F/+1 IR_D` only when IR is enabled, so a manager with 5 F must
take D or G), no duplicate assets, and eliminated teams (plus their skaters) removed
from the pool up front with **no** mid-round substitution (SPEC §1). A `DraftAsset`
is a skater (F/D, carries `player_id`) or a team's goaltending (G, carries
`team_id`); `rank_value` is the public-perception score (regular-season points).

`GreedyOpponentModel` is the pluggable fallback behind the `OpponentModel`
interface: it drafts greedily by `rank_value` with softmax noise (a configurable
`temperature`; `0` = deterministic argmax) and positional-need awareness (a
still-open position gets a `need_weight × urgency` bump where
`urgency = open_slots / limit`). `run_draft` plays a state to completion through a
single seeded RNG; `validate_draft` checks every finished roster through the rules
engine. `survival_probability(state, candidate, manager, model, rollouts, seed)`
Monte-Carlos the opponents' picks between now and a manager's next turn and returns
`P(candidate survives)` — ≥1000 rollouts run well under 5 s and are deterministic
given `(state, seed)`.

## Data & artifact layout

- `data/raw/` — gitignored **except** the committed `league-drafts/`, `odds-archive/`,
  and `nhl-archive/` snapshots described in `SPEC.md §5`.
- `data/normalized/` — normalized Parquet tables + dated snapshots (gitignored).
- `data/features/` — generated feature matrices (gitignored).
- `data/overrides/` — hand-maintained YAML overrides (injuries, name/alias maps).
- `artifacts/` — model artifacts (gitignored) except committed `report.md` files
  and manifests under `artifacts/backtests/` and `artifacts/models/`.

## Determinism

Every stochastic component takes an explicit seed and records it in its artifact
manifest. `oracle` entry points must be deterministic given `(snapshot, seed)`.
