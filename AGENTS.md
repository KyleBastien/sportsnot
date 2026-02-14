# AGENTS.md — SportsNot

## Overview

SportsNot is an NHL Fantasy Playoff Hockey platform. Users create leagues, draft real NHL playoff players via snake draft, earn points from live playoff stats, and re-draft between rounds. Built as an Nx monorepo with React 19, Supabase backend, and deployed to GitHub Pages.

## Commands

```bash
# Development
nx serve @sportsnot/web           # Dev server (rspack, port 4200)
nx build @sportsnot/web           # Production build

# Testing (rstest runs at root, not through Nx)
rstest                            # Run all tests
rstest --coverage                 # Run all tests with coverage
rstest packages/utils/src/lib/utils.test.ts   # Run a single test file

# Linting, typechecking, formatting
nx run-many -t lint               # Lint all packages
nx run-many -t typecheck          # Typecheck all packages
nx lint @sportsnot/ui             # Lint a single package
nx typecheck @sportsnot/types     # Typecheck a single package
prettier --write .                # Format all files
prettier --check .                # Check formatting without writing
```

## Architecture

**Monorepo packages** (`packages/`), all imported via `@sportsnot/<name>`:

| Package       | Purpose                                                                                          |
| ------------- | ------------------------------------------------------------------------------------------------ |
| `web`         | React 19 SPA — routes, pages, app shell (rspack bundler)                                         |
| `ui`          | Shared presentational components (PlayerCard, GameCard, RosterSlot, etc.)                        |
| `nhl-api`     | Client for the undocumented NHL API (`api-web.nhle.com/v1`)                                      |
| `supabase`    | Supabase client + all React Query hooks (auth, leagues, drafts, rosters, live scoring)           |
| `supabase-db` | SQL migrations, RLS policies, edge functions                                                     |
| `types`       | Shared TypeScript interfaces and constants (User, League, Draft, RosterSlot, ScoringEvent, etc.) |
| `utils`       | Pure business logic — scoring calculations, draft order generation, CSV export                   |

**Data flow**: `nhl-api` → `supabase` edge functions sync stats → `supabase` hooks query data → `ui` components render → `web` pages compose everything.

## Key Conventions

### Styling

- **Vanilla Extract** for all custom CSS — theme tokens in `packages/ui/src/lib/styles/theme.css.ts`, sprinkles for atomic utilities
- **Mantine v8** for complex interactive components (modals, forms, app shell, notifications)
- No inline styles outside of Mantine component props

### Data Fetching

- **All server state via TanStack React Query v5** — never `useState` for async data
- Query keys follow `['resource', scopeId]` pattern (e.g., `['leagues', userId]`, `['draft', leagueId]`)
- Queries use `enabled` to skip when dependencies are missing
- Mutations invalidate related queries via `queryClient.invalidateQueries()`
- Supabase realtime subscriptions for live scoring updates

### React Query Hooks Location

All hooks live in `packages/supabase/src/lib/hooks/`:

- `useAuth.ts` — magic link auth (email only, no passwords)
- `useLeague.ts` — CRUD for leagues, join via invite code
- `useDraft.ts` — draft status, make picks, start draft
- `useRoster.ts` — roster management, IR activation with retroactive points
- `useLiveScoring.ts` — realtime stat subscriptions
- `useStatSync.ts` — polls NHL API and syncs to Supabase cache tables

### Testing

- Test runner: **rstest** (not Jest/Vitest) with jsdom environment
- Test files: `*.test.ts` / `*.test.tsx` co-located with source
- Component tests use `@testing-library/react`
- `test-setup.ts` polyfills `matchMedia`, `ResizeObserver`, and vanilla-extract file scope for jsdom
- Coverage thresholds vary per package (utils=90%, ui=80%, nhl-api/supabase=70%, web=60%)

### TypeScript

- Strict mode enabled; no implicit any
- Unused variables prefixed with `_` (ESLint rule: `argsIgnorePattern: '^_'`)
- All cross-package imports use path aliases (`@sportsnot/types`, `@sportsnot/utils`, etc.)

### Domain Constants

```
Scoring: goal=1pt, assist=1pt, win=2pts, shutout=4pts (replaces win bonus)
Roster:  5F, 3D, 1G, 1 IR_F, 1 IR_D
Draft:   Snake order; re-draft between rounds uses worst-to-best standings
```

### Environment Variables

- `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` — required for Supabase client
- Tests mock these automatically via rstest config `source.define`

### Toolchain

- **Node 24**, **Yarn 4 (Berry)**, **Nx 22.5**, **TypeScript 5.9**
- **rspack** as bundler (not webpack), configured via `@nx/rspack`
- **React Compiler** enabled (`babel-plugin-react-compiler`)
- Prettier: single quotes, trailing commas, 2-space indent, 80 char width
