# AGENTS.md — SportsNot

## Always Talk Like Caveman

Terse like caveman. Technical substance exact. Only fluff die.
Drop: articles, filler (just/really/basically), pleasantries, hedging.
Fragments OK. Short synonyms. Code unchanged.
Pattern: [thing] [action] [reason]. [next step].
ACTIVE EVERY RESPONSE. No revert after many turns. No filler drift.
Code/commits/PRs: normal. Off: "stop caveman" / "normal mode".

## Project Overview

SportsNot is an NHL playoff fantasy hockey app. Users create/join leagues, draft real NHL playoff players through a multi-round snake draft, manage rosters with IR slots, and compete based on live NHL stats. The app supports a full offline mock mode for development without Supabase/NHL API credentials.

## Monorepo Structure

Nx monorepo using Yarn 4 (with node-modules as it's nodeLinker via `.yarnrc.yml`). All packages live under `packages/` and are scoped `@sportsnot/*`.

| Package         | Purpose                                                                             |
| --------------- | ----------------------------------------------------------------------------------- |
| `web`           | React 19 SPA — the main app (Rspack bundled, Mantine UI, react-router-dom)          |
| `types`         | Shared TypeScript types (domain models: League, Draft, RosterSlot, NHL types)       |
| `supabase`      | Supabase client + React Query hooks (useAuth, useLeague, useDraft, useRoster, etc.) |
| `supabase-db`   | SQL migrations and Supabase edge functions                                          |
| `nhl-api`       | NHL API client for fetching live playoff stats                                      |
| `ui`            | Shared UI components + vanilla-extract styling (theme, sprinkles)                   |
| `utils`         | Pure utility functions                                                              |
| `mock-data`     | Static fixture data (players, teams, games, bracket) for mock mode                  |
| `e2e`           | Playwright end-to-end tests with page objects                                       |
| `widget-api`    | Shared TS types + HTTP client for the `widget-league-snapshot` edge function        |
| `widget-bridge` | Capacitor plugin bridging the web app to native widget code (iOS + Android)         |

Native iOS code (Capacitor host + `SportsNotWidget` WidgetKit extension +
ActivityKit Live Activity) lives in the top-level [`ios/`](./ios/) directory,
registered as the Nx project `@sportsnot/ios-app`.

Native Android code (Capacitor host + Home Screen widgets + FCM + Live
Update notifications) lives in the top-level [`android/`](./android/)
directory, registered as the Nx project `@sportsnot/android-app`.

**Dependency flow:** `web` → `supabase`, `nhl-api`, `ui`, `utils`, `types`, `mock-data`, `widget-bridge`, `widget-api`

## Build, Test, and Lint Commands

```bash
# Install dependencies
yarn install

# Build (all or specific package)
yarn nx build @sportsnot/web
yarn nx affected -t build

# Dev server (port 4200)
yarn nx serve @sportsnot/web

# Lint (ESLint with Prettier plugin — runs Prettier as an ESLint rule)
yarn nx lint @sportsnot/utils                       # single package
yarn nx affected -t lint                            # affected packages

# Unit tests (rstest via Nx)
yarn nx test @sportsnot/utils                       # single package
yarn nx test @sportsnot/nhl-api                     # single package
yarn nx run-many -t test --all                      # all packages with tests

# Typecheck
yarn nx affected -t typecheck

# E2E tests (Playwright — requires built web app)
yarn nx e2e @sportsnot/e2e
yarn playwright test --config packages/e2e/playwright.config.ts tests/draft-board.spec.ts  # single test

# Mock data download (fetches fresh NHL data into fixtures)
yarn nx download @sportsnot/mock-data
```

## Mock Mode

Set `VITE_MOCK_MODE=true` in `.env` to run the entire app offline with in-memory fixture data. Mock mode:

- Lazy-loads `MockAuthProvider`, `MockDataProvider`, and `SimulationControlPanel` at runtime
- Swaps real Supabase hooks for mock equivalents via `mockHooksRegistry` (`packages/web/src/mock/`)
- Uses static data from `@sportsnot/mock-data` (players, teams, games, bracket)
- When mock mode is off, Rspack aliases `@sportsnot/mock-data` to `false` to tree-shake it out
- Mock query results must include every TanStack Query status field consumed by shared
  hooks (for example, `isFetched: true` for successful static results).

The `packages/web/src/mock/` directory contains all mock infrastructure. The hook registry pattern (`mockHooksRegistry.ts`) maps each real Supabase hook to a mock implementation.

## Git Workflow

- **Never commit or push directly to `main`.** Always create a feature branch and open a pull request.
- Branch naming: `feat/`, `fix/`, `chore/` prefixes (e.g., `fix/draft-night-blockers`, `feat/commissioner-picks`).
- **Do not bypass local hooks.** `yarn install` runs `prepare`, which installs Husky. The pre-commit hook runs lint, typecheck, unit tests, and the CodeScene threshold check.
- **Before pushing:** run `yarn nx affected -t lint`, `yarn nx affected -t typecheck`, `yarn nx build @sportsnot/web`, and `yarn nx run-many -t test --all`. Run `yarn nx e2e @sportsnot/e2e` when a change touches user-facing flows.

## CodeScene Quality Gates

- **Threshold file:** `.codescene-thresholds` stores the SportsNot project ID plus the current Hotspot and Average Code Health ratchets. **Never lower these values.** Only raise them after the repo score improves.
- **Local auth:** export `CODESCENE_PAT` (preferred) or `CODESCENE_ACCESS_TOKEN` before committing. The local CodeScene check fails fast if no token is available.
- **Recovery mode:** `.codescene-thresholds` sets `ALLOW_RECOVERY_MODE=true` so an already-red remote baseline warns instead of blocking the refactor commits needed to recover. When a refactor raises the baseline, update the threshold file in the same branch.
- **Before risky work or hotspot-heavy edits:** use CodeScene MCP to inspect hotspots and touched files. Prefer `codescene-list_technical_debt_hotspots_for_project`, `codescene-code_health_review`, and `codescene-analyze_change_set` before opening a PR.
- **Boy Scout rule:** if you touch a hotspot or low-health file, leave it healthier than you found it. If the CodeScene gate warns, refactor before adding more feature complexity.

## Key Conventions

- **Styling:** Mantine v8 components for UI. Shared design tokens via vanilla-extract in `packages/ui/src/lib/styles/` (theme, sprinkles). The web app itself has no `.css.ts` files — it relies on Mantine + the ui package.
- **Data fetching:** TanStack React Query wrapping Supabase calls. Hooks live in `packages/supabase/src/lib/hooks/`. Stale time is 5 minutes.
- **Routing:** react-router-dom v7 with `<ProtectedRoute>` wrapper. Auth state flows through `AuthContext`.
- **Package exports:** Library packages use `"main": "./src/index.ts"` pointing to raw TypeScript source (no pre-compilation step for libraries). Rspack/Nx handles compilation.
- **TypeScript paths:** Import shared packages via `@sportsnot/<package>` aliases defined in `tsconfig.base.json`.
- **Nx CLI:** Always use `yarn nx`, never `npx nx`. Yarn is the package manager for this repo.
- **ESLint rules:** Unused vars prefixed with `_` are never allowed. Any console usage (including warn or error) is not allowed. Never use any in code, it is 100% not allowed.
- **Prettier:** Single quotes, trailing commas (es5), 2-space indent, 80 char width.
- **E2E tests:** Use page object pattern (`packages/e2e/page-objects/`) with test fixtures (`packages/e2e/fixtures/`).
- **Database:** Supabase with RLS policies. Schema in `packages/supabase-db/migrations/`. Edge functions in `packages/supabase-db/functions/`.
- **Migrations:** Use Supabase CLI timestamp format: `{YYYYMMDDHHmmss}_{name}.sql`. Migrations auto-deploy to production when CI+E2E pass on main.

## Database Migration Deployment

Migration source lives in `packages/supabase-db/migrations/` using Supabase CLI timestamp naming (`{YYYYMMDDHHmmss}_{name}.sql`). CI copies them to `supabase/migrations/` and runs `supabase db push` after CI+E2E pass on main.

**Adding a new migration:**

1. Generate a timestamp: `date +%Y%m%d%H%M%S` (or use current UTC time)
2. Create `packages/supabase-db/migrations/{timestamp}_{name}.sql`
3. Commit, open PR, merge to main — migration auto-deploys

**⚠️ Avoiding migration timestamp drift:**

`supabase db push` fails if the remote `schema_migrations` table contains a version that doesn't match any local filename. This happens when a migration is pushed manually (e.g. `supabase db push` from a local machine) with a different filename than what's committed to the repo.

To prevent drift:

- **Never run `supabase db push` manually** against production. Let CI handle it on merge to main.
- If you must push manually, ensure the **exact filename** (including timestamp) matches what's committed in `packages/supabase-db/migrations/`.
- After any manual push, verify with `supabase migration list` that remote versions match local filenames.
- If drift occurs, rename the local file to match the remote version and commit the rename.

**Manual deployment (local):**

```bash
# Copy migrations to supabase directory
Copy-Item packages\supabase-db\migrations\*.sql supabase\migrations\ -Force

# Link and push
supabase link --project-ref <project-ref>
supabase db push
```

The `supabase/migrations/` directory is gitignored — CI creates it at deploy time.

## Edge Function Deployment

Edge function source lives in `packages/supabase-db/functions/`. The Supabase CLI expects functions in `supabase/functions/`, so you must copy files before deploying (symlinks don't work on Windows).

```bash
# 1. Copy function source to the deploy directory
Copy-Item packages\supabase-db\functions\<function-name> supabase\functions\<function-name> -Recurse -Force

# 2. Deploy (supabase CLI installed via scoop)
supabase functions deploy <function-name> --no-verify-jwt

# Both functions at once
Copy-Item packages\supabase-db\functions\sync-nhl-stats supabase\functions\sync-nhl-stats -Recurse -Force
Copy-Item packages\supabase-db\functions\sync-regular-season-stats supabase\functions\sync-regular-season-stats -Recurse -Force
supabase functions deploy sync-nhl-stats --no-verify-jwt
supabase functions deploy sync-regular-season-stats --no-verify-jwt
```

**Important:** Edge functions use raw `fetch` to the PostgREST API — not the `@supabase/supabase-js` client library. The `esm.sh` CDN build of supabase-js is unreliable in the Deno edge runtime (`.upsert()` returns `undefined`). The `supabase/functions/` directory is gitignored.

## iOS App + Widget

The iOS build wraps the web app in Capacitor and ships a WidgetKit
extension with Home Screen, Lock Screen, Dynamic Island, and ActivityKit
Live Activity surfaces. See [`ios/README.md`](./ios/README.md) for the
full one-time macOS setup.

Nx targets (macOS only):

```bash
yarn nx sync-web @sportsnot/ios-app       # build web + cap sync ios
yarn nx build @sportsnot/ios-app          # xcodebuild App scheme
yarn nx build-widget @sportsnot/ios-app   # xcodebuild SportsNotWidget scheme
yarn nx run-ios @sportsnot/ios-app        # cap run ios (simulator)
yarn nx archive @sportsnot/ios-app        # xcodebuild archive
yarn nx pod-install @sportsnot/ios-app    # cap update ios + pod install
```

Required Supabase function secrets for `push-live-activity-updates`:
`APNS_KEY_ID`, `APNS_TEAM_ID`, `APNS_P8`, `APNS_BUNDLE_ID`, `APNS_ENV`
(`sandbox` for TestFlight/simulator, `production` for App Store).

The iOS CI workflow (`.github/workflows/ios-build.yml`) runs on
`macos-26` and is **not** part of the default `nx affected` lint/test
gate — it triggers only on PRs touching `ios/`, `packages/widget-*`,
`packages/web/`, or `capacitor.config.ts`.

## Android App + Widgets

The Android build wraps the web app in Capacitor with native Kotlin code
for Home Screen widgets (small/medium/large), FCM push notifications, and
Android 15+ Live Update notifications. See [`android/README.md`](./android/README.md)
for the full setup.

Nx targets:

```bash
yarn nx sync-web @sportsnot/android-app       # build web + cap sync android
yarn nx build @sportsnot/android-app          # gradlew assembleDebug
yarn nx run-android @sportsnot/android-app    # cap run android (emulator/device)
yarn nx assemble-release @sportsnot/android-app  # gradlew bundleRelease (AAB)
```

Required Supabase function secrets for Android push (alongside iOS APNs
secrets): `FCM_PROJECT_ID`, `FCM_SERVICE_ACCOUNT_JSON`.

The Android CI workflow (`.github/workflows/android-build.yml`) runs on
`ubuntu-latest` and is **not** part of the default `nx affected` lint/test
gate — it triggers only on PRs touching `android/`, `packages/widget-*`,
`packages/web/`, or `capacitor.config.ts`.

## Draft Oracle (`ml/`)

- Run Python checks from `ml/`: `.venv/Scripts/python.exe -m ruff check src tests scripts`,
  `.venv/Scripts/python.exe -m mypy src tests scripts`, and
  `.venv/Scripts/python.exe -m pytest`.
- Tests enforce offline execution through the autouse socket guard in
  `ml/tests/conftest.py`; HTTP tests must use fixture transports.
- Stamp generated artifact manifests through
  `draft_oracle.provenance.add_git_provenance` so `git_sha` and `git_dirty` stay
  consistent. For clean-worktree regeneration, run the Python process with its
  working directory inside that clean worktree; changing `PYTHONPATH` alone does not
  change the repository inspected by `git_state()`.
- `test_committed_model_evidence.py` guards committed model/backtest/projection
  provenance, seeds, coverage, and league-comparison structure. Every manifest SHA
  must be an ancestor of HEAD; models plus backtests share one evidence-pass SHA,
  while all four 2026 projection fixtures may share a separate SHA. Regenerate each
  report/manifest pair together at a fixed seed. The 2026 `r500` backtest can run for
  roughly seven CPU hours and writes its artifact only when the run completes; quiet
  output is normal while the process remains active.
- Committed projection CSV/parquet twins must contain the same ordered rows and
  columns. Compare them with blank-string/null normalization and a `1e-12` float
  tolerance in `test_committed_projection_artifacts.py`.
- Combined-event manifest components are independently serialized to six decimal
  places. Formula decomposition assertions need `3e-6` absolute tolerance.
- Keep imports in `draft_oracle.cli.project` lightweight. Import training and HTTP
  modules inside command bodies so draft-time commands start without LightGBM,
  scikit-learn, or httpx. Keep `draft_oracle.optimize` package re-exports lazy and
  isolate artifact-consumption primitives from simulation/training modules; import
  guards must exercise real `draft` and `recommend` commands, not only `--help`.
- Team outcome features belong to `draft_oracle.models.game_win`; shared Elo math
  lives in `draft_oracle.features.elo`. Do not recreate a parallel team/series
  matrix unless a production model consumes and evaluates it.
- Every team-game pivot derives winners from normalized `team_games.win`, never goal
  comparison. This includes game-win training, series-sim replay, and shutout
  training. Shootout rows can have equal `goals_for`; pivots retain them and warn
  when a game lacks exactly one archive winner.
- Game-win reports/manifests must list priced/total market coverage for every temporal
  split season and explicitly mark zero-coverage seasons. Normalize `season_end_year`
  keys before integer conversion because odds joins can promote them to floats.
- Odds cross-validation compares each source's `home_implied`, never favorite-probability
  magnitudes; opposite favorites can otherwise look equal. Market joins are
  orientation-sensitive even though game-type lookup is not, so reverse-only archive
  matches must be blanked, counted, and logged as unjoinable.
- NHL stats-rest cap guards check both declared `total` and `len(data)`; omitted/null
  totals must not let a full 10,000-row response pass as complete.
- League entity matching requires `skater_games.parquet` as well as the pick/player/team
  tables. Scored sheet matches are review-flagged when all three exact integer point
  splits disagree with the NHL archive; goalie/team rows skip this skater-points check.
  Guard globally keyed player-name overrides with `expected_matches` in
  `name_overrides.yaml`; `match-drafts` must fail if the raw-name corpus count changes.
  Duplicate asset ownership is scoped by `(league_name, season, draft_event)`, keyed by
  `player_id` for skaters and `team_id` for goalie/team slots, and ignores same-manager
  source copies.
- Opponent fitting must call `dedupe_duplicate_events` and group through league-aware
  `event_keys`. App rows remain authoritative, but missing app skater `team_id` values
  inherit an unambiguous sheet match on `(league event, manager, player_id)` before
  sheet rows are dropped; existing app ids and goalie/team rows stay untouched.
- Recommend vectorized kernels must match object policies on exact ties
  (`rank_value` descending, then asset key ascending) and keep fitted `need_weight`
  per manager. Fitted CLI output must disclose league-average/no-affinity fallback
  when seat ids do not match committed per-manager keys.
- Draft-night CLI validation is shared by `draft` and `recommend`: manager ids must
  be unique case-insensitively, eliminated-team abbreviations must all resolve, and
  `DraftState.new` repeats manager uniqueness validation. A new draft refuses any
  existing session path; users must pass `--resume` or choose another `--session`.

## Ralph Agent System

The repo includes a Ralph autonomous agent system (`scripts/ralph/`) for automated story implementation. Ralph agents read a `prd.json`, implement stories one at a time, and track progress in `progress.txt`. Agent instructions are in `scripts/ralph/CLAUDE.md`. Copilot Skills for PRD generation and Ralph conversion are in `.agents/skills/`.
