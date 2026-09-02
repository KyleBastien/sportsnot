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
| Fit opponents   | `uv run oracle train-opponents`          |
| Project skaters | `uv run oracle project-skaters`          |
| Batch projection| `uv run oracle project --season 2026 --round 1` |
| Projection + IR | `uv run oracle project --season 2026 --round 1 --managers 4 --ir` |
| Slot strategies | `uv run oracle project --season 2026 --round 1 --managers 12` (emits `slot_strategies.md`) |
| Recommend pick  | `uv run oracle recommend --artifact-dir artifacts/2026-r1 --managers 6 --seat 3` |
| Compare drafters| `uv run oracle compare-strategies`       |
| Draft assistant | `uv run oracle draft --artifact artifacts/2026-r1 --managers 4 --slot 1 [--ir]` |
| Backtest replay | `uv run oracle backtest --seasons 2022` |

Most tests use self-contained fixtures. Real-data regression tests skip when generated
`data/normalized/*.parquet` tables are absent. Run all real-data checks after generating
normalization, matched league drafts, and odds:

```bash
uv run oracle normalize --force
uv run oracle league-drafts
uv run oracle match-drafts
uv run oracle odds
uv run pytest
```

## Package layout

The `draft_oracle` package (under `src/`) is organized by pipeline stage. Each
subpackage maps to the stories called out in `SPEC.md §4`:

```
src/draft_oracle/
  rules.py       scoring, snake/re-draft order, roster validation (US-002)
  ingest/        NHL API, odds, league drafts, entity match, injuries (US-003..008)
  features/      skater features, shared Elo math, leakage guard (US-009/010/119)
  models/        win, shutout, series sim, skater rate, returns, projections (US-011..016)
  optimize/      VOR, draft simulator, opponents, recommend, IR value, slot strategies (US-018..023)
  cli/           batch projection + interactive draft assistant (US-017/024)
  backtest/      replay engine + reporting (US-025/026)
```

## Pipeline stages

1. **Rules engine** (`rules.py`) — mirrors the app's scoring and draft order exactly.
   Public API: `player_points`, `goalie_series_points`, `goalie_game_points`,
   `snake_order`, `redraft_order`, `roster_composition`, and `validate_roster`
   (with `RosterSlot` / `RosterValidation`). These are the byte-for-byte mirror of
   `packages/utils/src/lib/utils.ts`; golden vectors in `tests/test_rules.py` are
   equivalent to those in `utils.test.ts` to catch cross-language drift.
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
| `kaggle_espn` (Kaggle/ESPN) | 2004 – Dec 2025; retained for audit, currently no usable prices | favorite-side only, but no trustworthy favorite attribution |
| `espn_completion` (ESPN API) | Dec 2025 – Jun 2026 incl. 2026 playoffs | favorite-side only, attributed from cached raw summaries |

**De-vigging** (`SPEC.md §5`):

- Two-sided prices (SBR) use the **proportional** method: each raw implied
  probability (`1/decimal`) is divided by their sum (the overround), so fair
  probabilities sum to 1 while preserving their ratio.
- Favorite-only prices remove a documented **standard two-way overround**
  (`STANDARD_OVERROUND = 1.045`, ~4.5% hold) from the favorite's raw implied
  probability; the underdog is the complement. **No underdog American price is
  ever fabricated** — only probabilities are produced.

**Favorite attribution and placeholder guard** — Kaggle's two team rows usually
repeat one game-level spread, so they do not identify which team owns the
favorite-only price. Those rows remain auditable but unattributed and uncovered;
the parser never guesses a side. A per-season guard also rejects constant or
modal placeholder prices (including the archive's fabricated `-105` blocks).
ESPN-completion favorites instead come from each game's cached raw summary
`homeTeamOdds.favorite` flag; a missing flag with no usable home-relative spread
also stays unattributed and uncovered. Consequence: the historical pipeline has
**no usable market coverage for 2024-25**.

**Archive join and consolidation** — Kaggle/ESPN UTC dates first snap to the NHL
archive's local game date. The archive join supplies authoritative `gameTypeId`
(2 regular season, 3 playoffs), replacing date-window playoff guesses and
implicitly excluding preseason games absent from the archive. Consolidation then
collapses source rows to one best row per game (`odds.parquet`) while preserving
all rows in `odds_by_source.parquet`. Matching uses season plus oriented away/home
ids with exact or ±1-day local-date tolerance; at most one row per source may
attach to a game. SBR Close wins ties. Covering sources are cross-validated in a
consistent home-team frame: `xval_delta` is the max-minus-min `home_implied`, and
rows above the `0.15` gate are blanked to uncovered. Unattributed, placeholder,
cross-validation-failed, and orientation-unjoinable rows are flagged and counted,
never imputed or silently dropped.

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
  favorite-only) for individual future games. It infers the favorite from the
  home-relative spread; unlike the committed completion parser, it does not use
  retained per-side favorite flags. ESPN 403s browser-like User-Agents, so the
  default httpx UA is used.

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
  bar**. The shipped player override corrects the 2024 R3+4 bare `McDavid` row to
  Leon Draisaitl and declares `expected_matches: 1`; `match-drafts` fails loudly
  if future input changes that match count.

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

**`injuries` table** — one row per player: `player_id` (canonical NHL id for a
resolved skater), `espn_id` (original ESPN athlete id retained for provenance),
`player_name`, `position`, `team_id` (stable NHL id via `resolve_team_id`),
`team_abbrev`, normalized `status` (`out` / `ir` / `day_to_day` / `healthy`),
`status_raw`, `return_date`, `detail`, `as_of_date`, `source`
(`espn` / `override` / `last_known`).

ESPN ids are not NHL ids. `resolve_player_ids` matches the ESPN name against the
NHL player dimension, disambiguating collisions by team then fantasy position and
using a unique-surname fallback only when unambiguous. Goalies remain team-level.
An unresolved skater is kept under its ESPN id, listed in
`InjuriesResult.unresolved_player_ids`, and never silently joined to NHL skaters.

**Overrides — final authority** — `data/overrides/injuries.yaml` merges *over*
the source. Each `overrides:` entry matches by NHL `player_id` first, then
`espn_id`, then `player` name (accent/punctuation-insensitive); a match rewrites
status / return date / detail, `remove: true` deletes the row, and an unmatched
entry is injected as a new row. Ships empty.

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

## Team model features and Elo decision

The unused `features/team_series.py` matrix was deleted in US-119. It built
team-form, market, injury, and matchup joins but no training, evaluation,
projection, or draft path consumed its output. Keeping that parallel matrix made
load-bearing-looking code and tests without affecting a recommendation.

The live per-game win pipeline remains the single team-feature owner. It builds
chronological Elo and in-season aggregate differences directly from each game,
joins exact-game market probabilities when available, and reports the held-out
market ablation described below. The series simulator consumes that fitted
per-game model. Current injuries affect explicit projection and IR-stash paths;
they are not duplicated into an unconsumed team matrix.

Shared Elo configuration and pure math now live in `features/elo.py`. Both the
per-game win model and series simulator import those primitives, while each owns
its chronological state replay.

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
cross-season `elo_diff` (reusing `features/elo.py` primitives), in-season regular-season
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
(SPEC §7). Fresh reports and manifests also list priced/total games for every
train, validation, and test season, explicitly marking zero-coverage seasons.

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
# writes artifacts/2026-r1/{skaters,teams}.{parquet,csv} + cheatsheet.md
#   + slot_strategies.md + run_manifest.json
uv run oracle project --season 2026 --round 1 --managers 4 --ir   # IR-slot league
uv run oracle project --season 2026 --round 1 --managers 12 --no-slot-strategies  # skip US-023
```

- `skaters.{parquet,csv}` — `player_id, player_name, team_abbrev, position (F/D),
  expected_points, p10/p50/p90, pts_per_game, expected_games,
  availability_multiplier, injured, low_confidence`.
- `teams.{parquet,csv}` — `team_id, team_abbrev, opponent_abbrev, is_top_seed,
  playoff_round, p_series_win, e_wins, e_games, e_goalie_points (goalie slot),
  e_shutout_wins` (goalie slot = a whole team's goaltending, SPEC §1).
- `cheatsheet.md` — the VOR draft board (US-018): every skater and team priced by
  value over replacement, sorted descending. See below.
- `slot_strategies.md` — the per-slot draft plan (US-023): one plan per snake slot
  `1..N`. See below.
- `run_manifest.json` — snapshot id, every sub-model version, feature version, git
  SHA, seeds, the VOR scarcity summary, the per-slot summary, and a UTC timestamp.

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

## IR-stash valuation (`optimize/ir_value.py`)

IR slots let a manager roster an *injured* skater who cannot help the active lineup
yet. Activation is a **retroactive same-position swap** (SPEC §1): when the stash is
activated it replaces a same-position active starter (`F` swaps `F`, `D` swaps `D`,
enforced) and its points count **from the start of the round** — the swap rewrites
the whole round, it is never additive. Playing optimally, the manager ends the round
with whichever of the two same-position players scored more, so
`retroactive_swap_points(ir, active) = max(ir, active)`.

The stash EV composes the upstream models honestly: the **US-015 return-time curve**
says *when* the stash is back (a long-shot that returns in game 6 of a short series
adds almost nothing), and the **US-016 projection** drives the points it *would*
score once available. `value_stash` Monte-Carlos those samples against the
replacement-level active starter it would swap out (US-018 level): the marginal
`stash_value = E[max(X − Y, 0)]` — a stash only ever helps, since the starter is kept
when the stash underperforms.

The cheat sheet gains an **IR stash candidates** section (only with `--ir` and injured
skaters present) ranking injured `F`/`D` by stash value against the healthy
replacement-level alternative a manager could take instead, with a `stash` / `avoid`
verdict. With `--ir`, `oracle recommend` reprices injured skaters to their stash value
(`reprice_pool_for_ir`) so the optimizer values an `IR_F` / `IR_D` slot for the
retroactive-swap points it really adds, not for unreachable full-health production. The
artifact's `skaters.parquet` carries `ir_stash_ev` / `ir_stash_value` / `ir_verdict`
and the run manifest an `ir_stash` summary.

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

## Fitted opponent model (`optimize/opponents.py`)

The greedy fallback assumes everyone drafts the best publicly-ranked player; real
managers over-draft their favourite NHL teams and weight positions idiosyncratically.
US-020 fits an opponent policy to *this* league's committed draft history so survival
estimates reflect how these specific managers draft. It implements the same
`OpponentModel` interface as the simulator, so a fitted model drops straight into
`run_draft` / `survival_probability`, and `opponent_model_from_config("greedy" |
"fitted", …)` swaps policies from one config string.

**Approach and assumptions (owner-confirmed: the sheets record only final rosters plus
the snake seat order — the pick *sequence* is not observable; only the 2026 app export
carries a true `pick_number`).** We use the documented simpler approximation the story
permits: a per-manager **player-selection propensity conditioned on positional need**,
expressed as a conditional-logit (softmax) choice model. For each historical
`(season, event, base position)` the assets drafted at that position across the whole
league are the observed candidate pool, and each of a manager's picks is modelled as an
independent softmax draw over that pool — an **order-free, with-replacement**
approximation (we never condition on an observed pick index). The utility of an asset
for a manager is

```
U = beta_rank · rank_z  +  beta_affinity · team_affinity(manager, asset_team)
```

- `rank_z` — the standardized **public ranking** within the pool, from
  `points_when_drafted` (a *pre-draft* cumulative total, so no outcome leakage). The
  sheet round-1 tabs carry no public ranking, so `rank_z` is zero there and the model
  leans on affinity. At draft time the same coefficient reads the standardized
  `DraftAsset.rank_value` (regular-season points) within the manager's legal assets at a
  position — both are public quality signals on a z-scale, so the coefficient transfers.
- `team_affinity` — the fraction of a manager's history spent drafting that NHL team,
  the **own-team fandom** signal. Computed only from the *training* picks, so held-out
  validation never sees the season it scores.
- **positional need** is applied at draft time in `FittedOpponentModel.pick` as
  `need_weight · (open_slots / limit)` — a quantity fixed by roster state, never by a
  pick index. It governs which *position* a manager reaches for; the fitted coefficients
  govern which *player* within a position.

**Blending.** A league-level model is always fit (Newton-Raphson, L2-regularized). A
manager also gets their own coefficients when they clear `min_manager_picks`; those are
shrunk toward the league model by `n / (n + manager_blend_k)`, and the league model is
in turn shrunk toward the greedy best-available fallback (`beta_rank = fallback_rank`,
`beta_affinity = 0`) by `N / (N + league_fallback_k)`. Thin data degrades smoothly to
the league average and then to the fallback (SPEC §8).

**Validation (`uv run oracle train-opponents` → `artifacts/models/opponent/`).**
Leave-one-season-out **roster-membership accuracy**: refit on the other seasons, replay
each held-out event with the true snake order and drafted pool, and measure the fraction
of each manager's actual roster the model reproduces — compared against the greedy
fallback, per season. Where the true pick order exists (the 2026 app export), we also
report teacher-forced per-pick top-1 / top-K accuracy. Current measured values and
per-season wins/losses live in `artifacts/models/opponent/report.md` and
`manifest.json`; those generated artifacts are the canonical evidence. Do not duplicate
their numbers here, because every data-correction refit may move them. The dominant
positive affinity coefficient remains the main signal absent from the greedy fallback.

## Multi-step pick recommendation (`optimize/recommend.py`)

The cheat sheet ranks assets *in a vacuum*; US-021 answers the question on the clock:
*which pick right now leaves the best final roster once the draft plays out against
these opponents?* `recommend_pick(state, owner, opponent_model)` rolls the whole
remaining draft forward with Monte-Carlo: the owner tentatively takes each candidate,
the opponent model drafts through all of the owner's remaining turns, the owner's future
slots are filled by a greedy value-over-replacement rollout policy, and the owner's
total final-roster projection is averaged over `>=500` seeded rollouts. The recommended
pick is the `argmax` of that expected final-roster value, so the engine automatically
prefers a scarce-position asset that will not survive to the next turn over a safe one
that will, times a goalie slot correctly, and respects forced picks.

- **Explanations** — the top-5 carry VOR, `P(survives to next pick)`, expected delta vs.
  the #2 option, and positional need (`open/limit`).
- **Speed** — a full-depth 12-manager 11-pick recommendation runs in <10 s. The 500
  rollouts are **vectorized** in numpy (the pick order is identical across rollouts, so
  the whole batch advances in lockstep; only opponent draws differ) for the greedy path;
  candidate pruning to the top VOR assets, an owner-full early stop, and **common random
  numbers** across candidates (paired comparison, low-variance ranking) keep it there.
- **`--depth` / `--rollouts`** trade accuracy for speed; depth bounds how many owner
  turns are simulated against live opponents before a fast greedy tail fill.

```
uv run oracle recommend --artifact-dir artifacts/2026-r1 --managers 6 --seat 3
uv run oracle recommend ... --rollouts 800 --depth 2   # tune accuracy/speed
uv run oracle recommend ... --managers ben,judah,levi,kyle --opponents fitted  # real seats
```

**Opponent model (`--opponents` / `--managers`, US-113).** Both `oracle recommend` and
`oracle draft` default to `--opponents auto`: the committed **fitted** league model
(`artifacts/models/opponent/`) is used when its `manifest.json` is present (loaded
directly — no network, no training, no `league_draft_picks.parquet`), otherwise the
greedy fallback. Force either with `--opponents greedy|fitted` (an explicit `fitted`
with no artifact fails loudly rather than silently downgrading). `--managers` accepts
**either** a league size (`4` → `seat1..seat4`) **or** a comma list of real ids
(`ben,judah,levi,kyle`) so each manager's fitted model attaches to their real seat; the
`seatN` ids fall back to the fitted league model. The fitted path is vectorized (the
same batched kernel as greedy, faithful to the object rollout to <1e-9), so it holds the
same <10 s budget at `rollouts>=500`.

**Committed comparison (`uv run oracle compare-strategies` →
`artifacts/models/recommend/`).** Over `>=200` seeded, single-decision same-slot drafts:
each draft is advanced to a shared decision slot with a greedy tail against fitted-league
opponents, each strategy makes exactly one pick, and the draft finishes with an identical
greedy-VOR tail. Two honest scenarios (SPEC §7 — report misses, never cherry-pick):
against **balanced fitted opponents** multi-step *ties* greedy-VOR (fitted opponents
draft positions evenly via within-position `rank_z`, so a static VOR board is already
optimal) and edges one-step; against **positional-run opponents** (a run pushes a
position below its pool-wide replacement, where a static board is blind) multi-step
**beats both** baselines.

## Per-slot draft strategy report (`optimize/slot_strategies.py`)

Round-1 snake order is randomized and revealed only moments before the draft, so a
drafter has no time to plan once their seat drops. `oracle project` therefore
**precomputes a full plan for every slot `1..N`** (US-023) and writes it to
`slot_strategies.md` in the artifact dir.

Each slot's plan replays the whole draft from that seat against the **fitted opponent
model** (US-020, loaded from `league_draft_picks.parquet`; the greedy fallback is used
when no league history exists). At every owner turn the multi-step recommender (US-021)
surfaces the recommended pick plus its top-3 alternatives; the plan follows the
recommended line so later turns are conditioned on the picks already made.

- **Expected pick numbers** — the deterministic snake positions the slot owns
  (`slot_pick_numbers`).
- **Contingency guidance** on the first two turns — the gap of opponent picks before
  the owner's next turn is rolled out `contingency_rollouts` times, the most-likely
  board states (which top targets survive) are clustered from those branches, and each
  branch gets its own best pick.
- **Projected final-roster total** per slot, plus a summary table comparing all slots.
- Covers both **IR and no-IR** shapes (follows `--ir`).

```
uv run oracle project --season 2026 --round 1 --managers 12        # emits slot_strategies.md
uv run oracle project --season 2026 --round 1 --slot-rollouts 40   # faster per-turn rollouts
uv run oracle project --season 2026 --round 1 --no-slot-strategies # skip the report
```

A 12-slot league finishes well inside the 15-minute batch budget (greedy fallback in
seconds via the vectorized kernel; the fitted-opponent path in a few minutes).

## Interactive draft assistant (`cli/draft.py`)

*"I'm live on draft night — record every pick and tell me my best option now."*
`oracle draft` starts a terminal session that reads **only** the precomputed
projection artifact: no network, no model training at draft time. Every valuation
routes through the US-021 recommender and the rules-enforcing simulator.

```
uv run oracle draft --artifact artifacts/2026-r1 --managers 4 --slot 1        # start
uv run oracle draft --artifact artifacts/2026-r1 --managers 4 --slot 2 --ir   # IR league
uv run oracle draft --artifact artifacts/2026-r1 --managers ben,judah,levi,kyle --slot 1  # fitted seats
uv run oracle draft --resume draft-session.json                               # resume a log
```

Session commands:

| Command | Effect |
| --- | --- |
| `pick <manager> <name>` | Record a pick. `manager` is a seat number (`1`), id (`seat1`), or prefix; `name` is fuzzy-matched. |
| `undo` | Undo the most recent pick (state is rebuilt by replay). |
| `board` | Remaining assets grouped by position, best projection first. |
| `roster [manager]` | A roster (yours by default). |
| `recommend [--depth N]` | Top-5 explained picks (VOR, survival, need, delta vs #2). Full multi-step lookahead by default; `--depth 1` is the fast path. |
| `save <path>` / `resume <path>` | Write / reload the session JSON. In-loop resume switches autosave to the resumed path. |
| `help`, `quit` | Help and exit. |

Illegal actions are rejected **with the reason** — not your turn, already drafted,
position full, or on an eliminated team (`--eliminated ABC,DEF`). `recommend` returns
in under 10 s at any state with full-depth rollouts (under 5 s with `--depth 1`). The
session autosaves to a replayable JSON log after every pick (default
`./draft-session.json`, override with `--session`), so a draft can be replayed
for post-hoc analysis. Starting a new session refuses to overwrite an existing
log; use `--resume` or choose a different `--session` path.
Resuming autosaves in place by default. `--resume A --session B` may create a new
autosave copy at `B`, but refuses when a distinct `B` already exists. An in-loop
`resume <path>` switches all later autosaves to that resumed path, leaving the launch
log untouched.

## Backtest replay engine (`backtest/replay.py`)

*"Measure the edge on past playoffs — don't assume it."* `oracle backtest` replays
every playoff round of each requested season end-to-end: it rebuilds the US-017
projection artifact using **only** games played before the round started, seats the
oracle in **every** snake slot against the fitted league-history opponent model
(leave-one-season-out; greedy fallback where history omits the season), and scores
every drafted roster with the **actual** historical results through the rules engine.
Projections drive the decisions; actuals only ever drive the score.

```
uv run oracle backtest --seasons 2022                          # one season, greedy fallback
uv run oracle backtest --seasons 2022 --seasons 2023           # multiple seasons
uv run oracle backtest --seasons 2022 --strategy oracle --strategy greedy_vor  # + baselines
```

A hard leakage guard (`assert_round_inputs_leakfree`) fails the run loudly if any
round-N game leaks into the as-of inputs for round N — both a date check and a direct
`game_id` identity check. Runs are seeded and reproducible: `(snapshot, seed)` fully
determines every roster and score. The run manifest and per-round intermediates are
written under `artifacts/backtests/<run-id>/` (manifest committed, per-round JSON
regenerable) so reporting can run separately.

## Backtest reporting (`backtest/report.py`)

`oracle backtest` also writes a committed, self-contained
`artifacts/backtests/<run-id>/report.md` (via `build_backtest_report` /
`write_report`) so the tool's edge is *inspected*, not assumed:

- **Projection accuracy** — skater and team projection MAE + Spearman rank correlation
  vs. the realized round points, per season and in aggregate.
- **Series-model calibration** — the series win model's Brier score on **two tracks**:
  *stat-only* (the probabilities the artifact actually drafted from, scored on every
  series) and *market-aware* (a post-hoc probability from de-vigged per-game betting
  odds, scored only where historical odds exist), each vs. the higher-seed and
  coin-flip baselines.
- **Draft strategy vs. baselines** — the multi-step oracle's actual roster points and
  win rate against `greedy_vor`, `one_step`, and `random_legal`, broken out per snake
  slot.
- **League comparison** — where a backtested season overlaps the committed league draft
  history, the oracle's simulated roster points vs. what the league's managers actually
  drafted (rounds 3+4 map to the league's combined `R3_4` redraft).

Every metric is reported truthfully (SPEC §7): a baseline the oracle fails to beat, or
a projection that misses, is printed with its honest value. The committed
`2023-2024-2025-seed20260827` run demonstrates all four sections over three seasons.

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
