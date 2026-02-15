# AGENTS.md — SportsNot

## Project Overview

SportsNot is an NHL playoff fantasy hockey app. Users create/join leagues, draft real NHL playoff players through a multi-round snake draft, manage rosters with IR slots, and compete based on live NHL stats. The app supports a full offline mock mode for development without Supabase/NHL API credentials.

## Monorepo Structure

Nx monorepo using Yarn 4 (with node-modules as it's nodeLinker via `.yarnrc.yml`). All packages live under `packages/` and are scoped `@sportsnot/*`.

| Package       | Purpose                                                                             |
| ------------- | ----------------------------------------------------------------------------------- |
| `web`         | React 19 SPA — the main app (Rspack bundled, Mantine UI, react-router-dom)          |
| `types`       | Shared TypeScript types (domain models: League, Draft, RosterSlot, NHL types)       |
| `supabase`    | Supabase client + React Query hooks (useAuth, useLeague, useDraft, useRoster, etc.) |
| `supabase-db` | SQL migrations and Supabase edge functions                                          |
| `nhl-api`     | NHL API client for fetching live playoff stats                                      |
| `ui`          | Shared UI components + vanilla-extract styling (theme, sprinkles)                   |
| `utils`       | Pure utility functions                                                              |
| `mock-data`   | Static fixture data (players, teams, games, bracket) for mock mode                  |
| `e2e`         | Playwright end-to-end tests with page objects                                       |

**Dependency flow:** `web` → `supabase`, `nhl-api`, `ui`, `utils`, `types`, `mock-data`

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

The `packages/web/src/mock/` directory contains all mock infrastructure. The hook registry pattern (`mockHooksRegistry.ts`) maps each real Supabase hook to a mock implementation.

## Key Conventions

- **Styling:** Mantine v8 components for UI. Shared design tokens via vanilla-extract in `packages/ui/src/lib/styles/` (theme, sprinkles). The web app itself has no `.css.ts` files — it relies on Mantine + the ui package.
- **Data fetching:** TanStack React Query wrapping Supabase calls. Hooks live in `packages/supabase/src/lib/hooks/`. Stale time is 5 minutes.
- **Routing:** react-router-dom v7 with `<ProtectedRoute>` wrapper. Auth state flows through `AuthContext`.
- **Package exports:** Library packages use `"main": "./src/index.ts"` pointing to raw TypeScript source (no pre-compilation step for libraries). Rspack/Nx handles compilation.
- **TypeScript paths:** Import shared packages via `@sportsnot/<package>` aliases defined in `tsconfig.base.json`.
- **ESLint rules:** Unused vars prefixed with `_` are never allowed. Any console usage (including warn or error) is not allowed. Never use any in code, it is 100% not allowed.
- **Prettier:** Single quotes, trailing commas (es5), 2-space indent, 80 char width.
- **E2E tests:** Use page object pattern (`packages/e2e/page-objects/`) with test fixtures (`packages/e2e/fixtures/`).
- **Database:** Supabase with RLS policies. Schema in `packages/supabase-db/migrations/`. Edge functions in `packages/supabase-db/functions/`.

## Ralph Agent System

The repo includes a Ralph autonomous agent system (`scripts/ralph/`) for automated story implementation. Ralph agents read a `prd.json`, implement stories one at a time, and track progress in `progress.txt`. Agent instructions are in `scripts/ralph/CLAUDE.md`. Copilot Skills for PRD generation and Ralph conversion are in `.agents/skills/`.
