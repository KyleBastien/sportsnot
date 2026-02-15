# PRD: Mock Mode

## Introduction

Mock Mode is a developer/QA tool that allows the SportsNot app to run entirely offline — without Supabase or live NHL API calls — by replaying historical 2025 NHL Playoff data. When enabled via `VITE_MOCK_MODE=true`, the app swaps all data hooks and API calls with an in-memory mock data layer seeded from real 2025 playoff results. This lets developers simulate the entire playoff season (draft, games, scoring, rosters, standings) day-by-day and round-by-round — just as a real user would experience checking in daily — ensuring every feature path is exercised before real playoffs begin.

## Goals

- Enable full end-to-end testing of the app without any external dependencies (no Supabase, no NHL API)
- Replay historical 2025 NHL Playoff data (teams, players, games, stats) as the simulation source
- Support solo mock drafts with AI auto-pick bots filling other roster slots
- Provide day-by-day simulation controls within each round, so devs experience the app exactly as a user checking in daily would — seeing that day's games, updated cumulative stats, and standings
- Provide round-by-round advancement (R1 → R2 → CF → SCF) once all days in a round are exhausted, so devs can inspect state at each stage
- Store all mock state in-memory/localStorage only — zero database writes, easy to dump and reset
- Activate via a single environment variable (`VITE_MOCK_MODE=true`) with no code changes required

## User Stories

### US-001: Environment Variable Toggle
**Description:** As a developer, I want to enable mock mode with a single env var so that I can quickly switch between real and mock data without changing code.

**Acceptance Criteria:**
- [ ] Setting `VITE_MOCK_MODE=true` in `.env` (or `.env.local`) activates mock mode app-wide
- [ ] When mock mode is active, a visible banner/indicator appears in the UI (e.g., "🧪 Mock Mode" in the header)
- [ ] When mock mode is NOT active (default), all behavior is identical to production — zero impact on the real app
- [ ] When `VITE_MOCK_MODE` is not `true` (or absent), **zero mock mode code or data is included in the production bundle** — all mock modules are dead-code-eliminated at build time
- [ ] The mock mode env var is documented in `.env.example`
- [ ] Typecheck/lint passes
- [ ] All unit tests pass
- [ ] Playwright tests pass

### US-002: Mock Data Layer — Provider Architecture
**Description:** As a developer, I want a mock data provider that intercepts all Supabase and NHL API hooks so that the app runs entirely on local mock data.

**Acceptance Criteria:**
- [ ] A `MockDataProvider` React context wraps the app when `VITE_MOCK_MODE=true`
- [ ] All `@sportsnot/supabase` hooks (useLeagues, useDraft, useRoster, useStandings, etc.) are replaced with mock implementations when mock mode is active
- [ ] All `@sportsnot/nhl-api` functions (getTeamRoster, getPlayer, getScoresNow, getPlayoffBracket, etc.) return historical 2025 data when mock mode is active
- [ ] No network requests to Supabase or NHL API are made when mock mode is active
- [ ] The swap is transparent — consuming components do not need to know whether they are in mock or real mode
- [ ] Typecheck/lint passes
- [ ] All unit tests pass
- [ ] Playwright tests pass

### US-003: Historical 2025 Playoff Data Bundle
**Description:** As a developer, I want a bundled dataset of the 2025 NHL Playoffs so that mock mode has realistic, complete data to simulate.

**Acceptance Criteria:**
- [ ] TypeScript fixture files contain all 16 playoff teams (name, abbreviation, logo URL, seed, conference) conforming to `NHLTeam`
- [ ] TypeScript fixture files contain full rosters for all 16 teams (player name, position, number, headshot URL) conforming to `NHLPlayer`
- [ ] TypeScript fixture files contain all playoff game results by round (R1, R2, CF, SCF) with scores, dates, game IDs, and series outcomes conforming to `NHLGame`
- [ ] Game results are indexed by date so that day-by-day simulation can look up which games occurred on each calendar day
- [ ] TypeScript fixture files contain per-player per-game stats for the entire 2025 playoffs (goals, assists, points, +/-, TOI, shots, PIM for skaters; saves, shots against, SV%, shutouts for goalies) conforming to `NHLPlayerStats` / `NHLGoalieGameStats`
- [ ] Per-player stats are available at per-game granularity (not just cumulative per-round) so that daily accumulation is accurate
- [ ] Playoff bracket/series data (matchups, seeds, series wins) is included conforming to `NHLPlayoffSeries`
- [ ] Data is stored in a `packages/mock-data/` package and is tree-shaken out of production builds
- [ ] Data format matches existing `@sportsnot/types` interfaces (NHLPlayer, NHLTeam, NHLGame, NHLPlayoffSeries, NHLPlayerStats) — adapter functions are used where the raw API response doesn't map cleanly
- [ ] Fixture files are checked into the repository so they are always available without re-running the download script
- [ ] Typecheck/lint passes
- [ ] All unit tests pass
- [ ] Playwright tests pass

### US-003b: Fixture Data Collection Script
**Description:** As a developer, I want an automated script that downloads the 2025 NHL Playoff data from the NHL API and generates the TypeScript fixture files, so that the data is reproducible and can be refreshed if needed.

**Acceptance Criteria:**
- [ ] A script exists as an Nx target on the `@sportsnot/mock-data` package (runnable via `nx download mock-data`)
- [ ] The script uses the existing `@sportsnot/nhl-api` package functions to fetch all required data — no raw fetch calls or duplicate API logic
- [ ] The script executes the following data collection pipeline:
  1. **Bracket & Teams:** Calls `getPlayoffBracket("20242025")` to identify all 16 playoff teams and series matchups
  2. **Rosters:** Calls `getTeamRoster(abbr, "20242025")` for each of the 16 teams (parallelized with rate limiting)
  3. **Playoff Schedule:** Calls `getPlayoffSchedule("20242025")` to get all game IDs, dates, scores, and round assignments
  4. **Player Game Logs:** Calls `getPlayerGameLog(playerId, "20242025", 3)` for every player on every playoff roster (parallelized with rate limiting) to get per-game stats
  5. **Boxscores (possibly needed enrichment):** Calls `getGameBoxscore(gameId)` for each game if additional detail is needed (e.g., goalie stats not covered by game logs)
- [ ] The script includes rate limiting (e.g., max 10 concurrent requests, 100ms delay between batches) to avoid overwhelming the NHL API
- [ ] The script writes output as TypeScript files with `export const` and `as const` assertions into `packages/mock-data/src/`:
  - `teams.ts` — all 16 playoff teams
  - `players.ts` — all player rosters keyed by team abbreviation
  - `bracket.ts` — playoff series/bracket data
  - `games-r1.ts`, `games-r2.ts`, `games-cf.ts`, `games-scf.ts` — game results split by round
  - `player-game-logs.ts` — per-player per-game stat lines keyed by player ID
- [ ] The script logs progress as it runs (e.g., "Fetching roster for TBL... done (23 players)", "Fetching game logs: 142/312 players...")
- [ ] The script is idempotent — running it again overwrites the existing fixture files with fresh data
- [ ] The script handles API errors gracefully (retries transient failures, logs and skips permanently missing data)
- [ ] A README in `packages/mock-data/` documents how to run the script and what it produces
- [ ] Typecheck/lint passes
- [ ] All unit tests pass
- [ ] Playwright tests pass

### US-004: Mock Authentication
**Description:** As a developer, I want mock mode to bypass Supabase auth so that I can use the app without logging in.

**Acceptance Criteria:**
- [ ] When mock mode is active, the app automatically "logs in" as a mock user (no magic link required)
- [ ] The mock user has a deterministic ID, display name ("Mock User"), and avatar
- [ ] `useAuth()` returns the mock user session — all auth-gated routes work normally
- [ ] Sign-out in mock mode resets to the mock user (or shows a "mock mode — auth disabled" message)
- [ ] Typecheck/lint passes
- [ ] All unit tests pass
- [ ] Playwright tests pass

### US-005: Mock League Creation
**Description:** As a developer, I want to create mock leagues with configurable member counts so that I can test draft and roster features.

**Acceptance Criteria:**
- [ ] When creating a league in mock mode, a "Bot Members" count selector appears (2–16 members total, including the mock user)
- [ ] Bot members are created with generated with the names of random NHL players (e.g., "Connor McDavid", "Auston Matthews", "Leon Draisaitl")
- [ ] The mock league is stored in-memory and appears on the dashboard like a real league
- [ ] Mock leagues are visually tagged (e.g., "🧪 Mock" badge) to distinguish from any real leagues
- [ ] All league settings (roster size, scoring rules, etc.) work as normal
- [ ] Typecheck/lint passes
- [ ] All unit tests pass
- [ ] Playwright tests pass

### US-006: Mock Draft with AI Auto-Pick
**Description:** As a developer, I want to run a mock draft where bots auto-pick players so that I can test the full draft flow solo.

**Acceptance Criteria:**
- [ ] Starting a draft in a mock league initiates a snake draft with the mock user and all bots
- [ ] When it's a bot's turn, the bot auto-picks within 1–2 seconds (no waiting for real timers)
- [ ] Bot draft strategy is "best available by position need" — bots fill roster slots sensibly (not all goalies)
- [ ] The mock user drafts manually via the normal draft UI (player list, pick button, draft board)
- [ ] Draft state (picks, board, current turn) updates in real-time via the existing UI components
- [ ] The draft completes when all roster slots are filled for all teams
- [ ] Typecheck/lint passes
- [ ] All unit tests pass
- [ ] Playwright tests pass

### US-007: Day-by-Day and Round-by-Round Simulation Controls
**Description:** As a developer, I want to advance the simulation one day at a time within each round — and then advance to the next round when all days are complete — so that I experience the app exactly as a user would checking in daily during the real playoffs.

**Acceptance Criteria:**
- [ ] A simulation mock controls overlay is toggle-able when in mock mode
- [ ] The control panel displays the current simulated date (e.g., "April 19, 2025") and the current round (e.g., "Round 1 — First Round")
- [ ] A **"Next Day →"** button advances the simulated date by one calendar day
- [ ] After advancing a day, cumulative player stats, standings, scoring history, and roster stats reflect all games played up to and including the new simulated date
- [ ] The existing Live Games section on the dashboard shows that day's games and scores (from the 2025 historical data), or "No games today" on off-days
- [ ] When the current round's final game day has been reached, the "Next Day →" button becomes disabled and displays a message: **"Round complete — advance to next round"**
- [ ] A **"Advance Round →"** button is available alongside the day controls; it is disabled until all days in the current round have been simulated
- [ ] Clicking "Advance Round →" transitions the simulation to the next round (R1 → R2 → CF → SCF), and the day-by-day cycle restarts for the new round
- [ ] After advancing a round, the playoff bracket updates to show series winners advancing and losers eliminated
- [ ] A **"Reset Season"** button clears all simulation state back to pre-Round 1 (post-draft), resetting the simulated date to the day before R1 game 1
- [ ] When all 4 rounds have been fully simulated (day-by-day through SCF), both buttons are disabled and a "🏆 Season Complete" indicator is shown
- [ ] Typecheck/lint passes
- [ ] All unit tests pass
- [ ] Playwright tests pass

### US-007b: Daily Games Scoreboard in Mock Mode
**Description:** As a developer, I want to see that day's game scores on the dashboard when advancing day-by-day so that the Live Games widget works correctly in mock mode.

**Acceptance Criteria:**
- [ ] The existing Live Games / scoreboard section on the dashboard is fed by mock data when mock mode is active
- [ ] For the current simulated date, the scoreboard shows all games that occurred on that date with final scores, teams, and series status (e.g., "TBL leads 2-1")
- [ ] On off-days (no games scheduled), the widget displays an appropriate empty state (e.g., "No games scheduled today")
- [ ] Rostered players who scored that day are highlighted (if the Live Games widget supports player highlighting)
- [ ] The `getScoresNow()` / `useLiveGames()` hook returns the current simulated day's games instead of making real NHL API calls
- [ ] Typecheck/lint passes
- [ ] All unit tests pass
- [ ] Playwright tests pass

### US-008: Mock Roster Management
**Description:** As a developer, I want roster management to work in mock mode so that I can test IR activation, roster changes, and roster history.

**Acceptance Criteria:**
- [ ] After the draft, each team's roster is populated and viewable on the roster page
- [ ] Player stats on the roster page accumulate day-by-day as the simulation advances (reflecting 2025 historical stats through the current simulated date)
- [ ] IR activation/deactivation works in mock mode (stored in-memory)
- [ ] Roster history page shows changes made during the mock session
- [ ] Typecheck/lint passes
- [ ] All unit tests pass
- [ ] Playwright tests pass

### US-009: Mock Standings & Scoring
**Description:** As a developer, I want standings and scoring history to work in mock mode so that I can verify point calculations and ranking logic.

**Acceptance Criteria:**
- [ ] Standings page calculates and displays league standings based on drafted players' historical stats accumulated through the current simulated date
- [ ] Standings update after each simulated day (not just per round)
- [ ] Scoring history page shows a timeline of scoring events derived from 2025 game data, growing as each day is simulated
- [ ] Point totals match the app's scoring rules applied to the historical stats
- [ ] Typecheck/lint passes
- [ ] All unit tests pass
- [ ] Playwright tests pass

### US-010: Mock Playoff Bracket
**Description:** As a developer, I want the playoff bracket to render correctly in mock mode so that I can verify bracket progression and team elimination.

**Acceptance Criteria:**
- [ ] The playoff bracket page shows all 16 teams in their correct 2025 seeding positions
- [ ] After simulating a round, the bracket updates to show series winners advancing and losers eliminated
- [ ] Series scores (e.g., "4-2") are displayed on each matchup
- [ ] After all 4 rounds, the Stanley Cup champion is displayed
- [ ] Typecheck/lint passes
- [ ] All unit tests pass
- [ ] Playwright tests pass

### US-011: Data Reset & Dump
**Description:** As a developer, I want to easily reset or dump all mock data so that I can start fresh or debug state issues.

**Acceptance Criteria:**
- [ ] A "Reset All Mock Data" button in the mock controls panel clears all in-memory and localStorage mock state
- [ ] After reset, the app returns to an empty dashboard (no leagues, no drafts)
- [ ] A "Dump State to Console" button logs the entire mock state tree to the browser console as JSON (for debugging)
- [ ] Typecheck/lint passes
- [ ] All unit tests pass
- [ ] Playwright tests pass

### US-012: Production Bundle Exclusion
**Description:** As a developer, I want to guarantee that no mock mode code, data fixtures, or mock providers are included in the production bundle when `VITE_MOCK_MODE` is not enabled, so that we never accidentally ship test data or mock logic to users.

**Acceptance Criteria:**
- [ ] All mock mode imports (MockDataProvider, fixture data, simulation controls, bot logic, mock auth) use dynamic `import()` behind an `if (import.meta.env.VITE_MOCK_MODE === 'true')` guard so Rspack can dead-code-eliminate them
- [ ] A production build (`nx build web`) with `VITE_MOCK_MODE` unset or `false` produces a bundle containing zero references to mock data, mock providers, or historical fixture files — verifiable by searching the output bundle
- [ ] The 2025 historical data fixtures (teams, players, games, stats) are isolated in their own chunk(s) that are only requested when mock mode is active
- [ ] No mock-related React components (MockModeBanner, SimulationControlPanel, etc.) appear in the production bundle
- [ ] A CI check or build-time assertion can verify bundle exclusion (e.g., `grep -r "mock" dist/ --include="*.js"` returns no matches for mock provider/fixture identifiers)
- [ ] Typecheck/lint passes
- [ ] All unit tests pass
- [ ] Playwright tests pass


- FR-1: The app must check `import.meta.env.VITE_MOCK_MODE` at startup and conditionally swap data providers
- FR-2: When mock mode is active, zero network requests to Supabase (`*.supabase.co`) or NHL API (`api-web.nhle.com`) shall be made
- FR-3: Mock mode must provide implementations for ALL data hooks used by the app (auth, leagues, drafts, rosters, standings, scoring, playoff bracket, player stats, team stats)
- FR-4: Historical 2025 NHL Playoff data must include all 16 teams, full rosters, all game results (R1–SCF) indexed by date, and per-player stats at per-game granularity for accurate daily accumulation
- FR-5: Mock drafts must support snake draft order with 1–2 second bot auto-pick timing
- FR-6: Bot draft strategy must distribute picks across positions to build valid rosters (forwards, defensemen, goalies)
- FR-7: The "Next Day" control must advance the simulated date by one day, updating all derived data (cumulative stats, standings, scoreboard, scoring history) to reflect games through that date
- FR-7b: The "Advance Round" control must be gated — disabled until all days in the current round are simulated — and transition the simulation to the next round's first day
- FR-7c: The Live Games / scoreboard widget must display the current simulated day's games and scores (or an empty state on off-days)
- FR-8: All mock state must be stored in-memory (React state/context) with optional localStorage backup — no database writes
- FR-9: All mock mode code and data fixtures must be **completely excluded from production builds** when `VITE_MOCK_MODE` is not `true`. This includes mock providers, fixture data, simulation controls, bot logic, and mock UI components. This is not optional tree-shaking — it is a hard requirement enforced by build-time guards and verifiable by inspecting the output bundle.
- FR-10: A visible mock mode indicator must be present at all times when mock mode is active so developers never confuse mock and real environments
- FR-11: The mock user must be automatically authenticated with no login flow required
- FR-12: "Reset All Mock Data" must clear both in-memory state and any localStorage entries used by mock mode

## Non-Goals (Out of Scope)

- **Not user-facing:** Mock mode is a developer/QA tool only — no user-facing "practice mode" or "sandbox" features
- **No multi-season support:** Only 2025 playoff data is bundled — no season selector or historical season picker (can be added later)
- **No multiplayer mock drafts:** Bots only — real users cannot join mock leagues
- **No Supabase persistence:** Mock data never touches the database — no mock tables, no mock RLS policies
- **No real-time simulation:** Days advance instantly on button click — no simulated game clocks, period-by-period progression, or play-by-play within a game day
- **No mock notifications:** The notification system (P1 feature) is not required to work in mock mode initially
- **No mock Edge Functions:** Supabase Edge Functions are bypassed entirely — stat syncing is replaced by direct fixture reads
- **No CI/CD integration:** Mock mode is for local development only — no headless simulation runner or automated regression tests (yet)

## Design Considerations

- **Mock Mode Banner:** A persistent, non-dismissible banner (e.g., bright yellow/orange strip at the top of the page or a badge in the header) should make it unmistakable that mock mode is active. Consider using Mantine's `Alert` or a custom `MockModeBanner` component.
- **Simulation Control Panel:** Could be implemented as:
  - A floating overlay/drawer accessible from a FAB (Floating Action Button)
  - A collapsible sidebar panel
  Recommend: A floating overlay/drawer accessible from a FAB (Floating Action Button) that shows:
  - Current simulated date (e.g., "📅 April 19, 2025")
  - Current round label (e.g., "Round 1 — First Round")
  - "Next Day →" button (primary action, used most often)
  - "Advance Round →" button (disabled until round's days are exhausted, then becomes primary)
  - "Reset Season" and "Dump State to Console" buttons (secondary/danger actions)
  - A mini calendar or day counter showing progress through the current round (e.g., "Day 12 of 18")
- **Bot Avatars:** Use generated initials or placeholder avatars (Mantine `Avatar` with color based on bot name) — no need for real images.
- **Reuse Existing Components:** All existing UI components (PlayerCard, draft board, roster page, standings table, bracket view) should work as-is — mock mode only swaps the data layer, not the presentation.

## Technical Considerations

- **Provider Swap Pattern:** Use a `MockDataProvider` that implements the same interface as the real Supabase hooks. The app's entry point (`app.tsx`) conditionally wraps children in either the real or mock provider based on `VITE_MOCK_MODE`. This keeps the swap clean and prevents mock code from leaking into real code paths.
- **Data Fixture Format:** Store 2025 data as TypeScript files (`.ts`) rather than JSON to get type safety and autocompletion. Use `as const` assertions where appropriate. Split into logical files: `teams.ts`, `players.ts`, `bracket.ts`, `games-r1.ts`, `games-r2.ts`, `games-cf.ts`, `games-scf.ts`, `player-game-logs.ts`. Games must include a `date` field (ISO date string, e.g., `"2025-04-19"`) so the day-by-day simulation can index games by calendar date.
- **Data Collection Pipeline:** The download script is an Nx target (`nx download mock-data`) on the `@sportsnot/mock-data` package, leveraging the existing `@sportsnot/nhl-api` package — no duplicate API logic. The pipeline is:
  1. `getPlayoffBracket("20242025")` → extract 16 team abbreviations + series data → write `bracket.ts` and `teams.ts`
  2. `getTeamRoster(abbr, "20242025")` × 16 teams (parallelized, rate-limited) → write `players.ts`
  3. `getPlayoffSchedule("20242025")` → split games by round number → write `games-r1.ts` through `games-scf.ts`
  4. `getPlayerGameLog(playerId, "20242025", 3)` × all players (~300+, parallelized in batches of 10, 100ms between batches) → write `player-game-logs.ts`
  5. (Optional) `getGameBoxscore(gameId)` for goalie-specific stats if game logs lack goalie detail
  The script writes TypeScript `export const ... = [...] as const` files that are directly importable. Fixture files are committed to the repo so mock mode works without re-running the script. The script only needs to run once (or again if data needs refreshing).
- **NHL API Season Format:** The NHL API uses concatenated season strings: `"20242025"` for the 2024–2025 season. Playoff game type is `3` (passed to `getPlayerGameLog`). These are already supported by the `@sportsnot/nhl-api` package.
- **Rate Limiting:** The NHL API is public and unauthenticated but will throttle aggressive clients. The download script must limit concurrency (max 10 in-flight requests) and add small delays between batches. A full download (~16 rosters + ~300 game logs + ~80 games) should take 2–5 minutes.
- **In-Memory State Management:** Use React Context + `useReducer` for mock state. The reducer handles actions like `CREATE_LEAGUE`, `MAKE_PICK`, `ADVANCE_DAY`, `ADVANCE_ROUND`, `RESET_ALL`. State includes `currentDate: string` (ISO date) and `currentRound: 1|2|3|4`. Day advancement recalculates cumulative stats by filtering all games with `date <= currentDate`. This gives a predictable state machine with easy debugging (actions are logged).
- **Daily Stat Accumulation:** When `ADVANCE_DAY` is dispatched, the reducer filters the game fixture data for all games on or before the new date, sums per-player stats from those games, and updates the cumulative stats map. This is a pure function of `(fixtures, currentDate)` → `cumulativeStats`, making it deterministic and easy to test.
- **Round Boundary Detection:** Each round's game fixtures define a `firstDate` and `lastDate`. When `currentDate >= lastDate` for the current round, the "Next Day" button is disabled and the "Advance Round" button is enabled. Advancing a round sets `currentDate` to the day before the next round's `firstDate` (so the first "Next Day" click lands on the first game day of the new round).
- **Dead-Code Elimination (Critical):** All mock mode code must be behind a build-time constant guard: `if (import.meta.env.VITE_MOCK_MODE === 'true') { ... }`. Rspack (like webpack) evaluates `import.meta.env.*` at compile time via `DefinePlugin` / `builtins.define`, so when `VITE_MOCK_MODE` is not `'true'`, the entire branch — including any `import()` calls inside it — is eliminated as dead code. **No mock code should be imported at the top level of any non-mock module.** All mock imports must be dynamic and inside the guard. This pattern ensures:
  1. Production builds contain zero bytes of mock code or fixture data
  2. No lazy-loaded mock chunks are emitted in the build output
  3. The guard is verifiable: run `nx build web` without the flag and grep the `dist/` output for known mock identifiers (e.g., `MockDataProvider`, `ADVANCE_DAY`, fixture team names)
- **Rspack Configuration:** Ensure `builtins.define` (or `DefinePlugin`) maps `import.meta.env.VITE_MOCK_MODE` to `"false"` (or `undefined`) in production builds so the dead-code branch is statically resolvable. If using `EnvironmentPlugin`, confirm it doesn't accidentally set a truthy default.
- **Existing E2E Factories:** The `packages/e2e/fixtures/data-factories.ts` file already has mock data patterns (createMockUser, createMockLeague, etc.). Consider reusing or extending these for mock mode to maintain consistency.
- **Type Compatibility:** Mock data must conform to existing `@sportsnot/types` interfaces. If historical data doesn't map cleanly, add adapter functions rather than modifying the core types.
- **Rspack Env Vars:** Rspack supports `import.meta.env.VITE_*` pattern for client-side env vars. Verify that the project's Rspack config exposes `VITE_MOCK_MODE` — may need to add `builtins.define` or `EnvironmentPlugin` configuration if not already set up.

## Success Metrics

- Developer can go from `VITE_MOCK_MODE=true` → app running with mock data in under 5 seconds (no external dependencies)
- Full playoff season simulation (draft + day-by-day through 4 rounds) can be completed in under 10 minutes of manual interaction
- All existing app pages (dashboard, draft, roster, standings, scoring, bracket) render correctly with mock data — zero blank screens or errors
- Zero network requests to external services when mock mode is active (verifiable in browser DevTools Network tab)
- Mock mode adds zero bytes to the production bundle — verifiable by building without the flag and grep-checking `dist/` for mock identifiers

## Open Questions

- What Rspack configuration is needed to support `import.meta.env.VITE_MOCK_MODE`? Need to verify current env var handling in the build config.
- If a developer has real leagues in Supabase AND enables mock mode, should real leagues still appear (read-only) alongside mock leagues, or should the dashboard show only mock data? -- No real leagues.
- Should the mock draft bot AI be configurable (e.g., "smart" vs "random" strategy) for testing different scenarios? -- No.
- On off-days (no games scheduled), should the "Next Day" button auto-skip to the next game day, or should the developer manually click through off-days to see the empty state? -- Manual click.
- Does `getPlayerGameLog` return goalie-specific stats (saves, GAA, SV%), or do we need to supplement with `getGameBoxscore` calls for goalie data? Needs verification against the actual API response.

## Resolved Questions

- ~~Should the 2025 historical data be scraped/collected manually, generated from NHL API snapshots, or sourced from a public dataset?~~ → **Resolved:** An automated script (`scripts/download-mock-data.ts`) will use the existing `@sportsnot/nhl-api` package to download all data from the NHL API. See US-003b.
- ~~The 2025 historical data needs per-game player stats — is this available from the NHL API?~~ → **Resolved:** Yes. `getPlayerGameLog(playerId, "20242025", 3)` returns per-game stat lines for playoff games. See US-003b pipeline step 4.
- ~~Should mock mode support the Player Comparison Tool?~~ → **Resolved:** Yes, it should.
