# PRD: Playwright End-to-End Test Suite

## Introduction

SportsNot currently has ~30 unit/component tests (rstest + React Testing Library) but zero end-to-end browser tests. Critical user flows — authentication, league management, drafting, roster management, and live scoring — are only validated at the unit level with mocked DOM environments (jsdom). This creates blind spots around routing, real browser rendering, network-level interactions, and cross-page state management.

This PRD defines the addition of a comprehensive Playwright E2E test suite that validates every major user flow in a real browser, with Supabase mocked at the network level via Playwright's route interception. Tests will live in a new `packages/e2e` Nx project, target Chromium, and run in the existing GitHub Actions CI pipeline.

## Goals

- Validate all critical user flows end-to-end in a real Chromium browser
- Catch regressions in routing, navigation, and cross-page state that jsdom tests miss
- Mock Supabase at the network layer so tests are fast, deterministic, and require no external services
- Integrate into CI so every PR is validated before merge
- Establish patterns and fixtures that make writing new E2E tests easy as features are added
- Cover mobile-responsive behavior via viewport emulation

## User Stories

### US-001: Playwright Infrastructure Setup

**Description:** As a developer, I need a working Playwright project in the monorepo so that I can write and run E2E tests.

**Acceptance Criteria:**

- [ ] Scaffold `packages/e2e` using `@nx/playwright` plugin (`nx g @nx/playwright:configuration --project=e2e`)
- [ ] Verify `@nx/playwright` executor is configured in `project.json` with the `e2e` target
- [ ] `playwright.config.ts` is configured with Chromium-only, base URL pointing to local dev server
- [ ] `webServer` config in Playwright starts `nx serve @sportsnot/web` automatically before tests
- [ ] `npx playwright test` runs from `packages/e2e` and passes with a placeholder test
- [ ] `nx e2e @sportsnot/e2e` works via the `@nx/playwright:playwright` executor
- [ ] `.gitignore` updated to ignore Playwright artifacts (`test-results/`, `playwright-report/`, `blob-report/`)

### US-002: Supabase Network Mock Layer

**Description:** As a developer, I need reusable Supabase mock fixtures so that E2E tests don't require a real backend.

**Acceptance Criteria:**

- [ ] Shared fixture file(s) that intercept all Supabase REST and Auth API calls via `page.route()`
- [ ] Mock data factory functions for users, leagues, league members, drafts, draft picks, rosters, and stats
- [ ] Auth mock supports: returning a valid session, returning no session (logged out), and magic link callback simulation
- [ ] Supabase Realtime WebSocket connections are stubbed (no hanging connections)
- [ ] Mock responses match the shape of real Supabase PostgREST responses (array results, `.select()` shapes)
- [ ] Fixtures are importable and composable (tests can override specific mocks)

### US-003: Authentication Flow Tests

**Description:** As a developer, I want E2E tests covering the authentication flow so that login/logout regressions are caught.

**Acceptance Criteria:**

- [ ] Test: unauthenticated user visiting `/` is redirected to `/auth/login`
- [ ] Test: login page renders magic link email form
- [ ] Test: submitting email shows "check your email" confirmation
- [ ] Test: auth callback route (`/auth/callback`) with valid token sets session and redirects to dashboard
- [ ] Test: authenticated user can sign out and is redirected to login
- [ ] Test: expired/invalid session redirects to login
- [ ] All tests pass with mocked Supabase auth endpoints

### US-004: Dashboard Tests

**Description:** As a developer, I want E2E tests for the main dashboard so that the primary landing experience is verified.

**Acceptance Criteria:**

- [ ] Test: authenticated user sees dashboard with league list
- [ ] Test: dashboard shows "no leagues" empty state when user has no leagues
- [ ] Test: dashboard displays live games widget when games are in progress (mocked)
- [ ] Test: clicking a league card navigates to that league's dashboard
- [ ] Test: "Create League" and "Join League" CTAs are visible and functional

### US-005: League Creation Flow Tests

**Description:** As a developer, I want E2E tests for creating a league so that the full creation flow is validated.

**Acceptance Criteria:**

- [ ] Test: navigating to `/leagues/create` shows the league creation form
- [ ] Test: form validates required fields (league name, team name)
- [ ] Test: form enforces max participants range (2–12)
- [ ] Test: successful submission creates league and navigates to league dashboard
- [ ] Test: new league dashboard shows invite code and commissioner controls
- [ ] Test: invite code copy button works (clipboard API mocked)

### US-006: Join League Flow Tests

**Description:** As a developer, I want E2E tests for joining a league via invite code.

**Acceptance Criteria:**

- [ ] Test: navigating to `/leagues/join` shows invite code input
- [ ] Test: entering invalid invite code shows error message
- [ ] Test: entering valid invite code shows league preview and team name prompt
- [ ] Test: submitting team name joins the league and navigates to league dashboard
- [ ] Test: attempting to join a full league shows appropriate error
- [ ] Test: attempting to join an already-joined league shows appropriate message

### US-007: League Dashboard & Settings Tests

**Description:** As a developer, I want E2E tests for the league dashboard and commissioner settings.

**Acceptance Criteria:**

- [ ] Test: league dashboard shows league name, status, member list, and standings
- [ ] Test: non-commissioner sees no settings controls
- [ ] Test: commissioner sees settings link and can navigate to settings page
- [ ] Test: commissioner can edit league name from settings
- [ ] Test: commissioner can regenerate invite code
- [ ] Test: "Start Draft" button appears for commissioner when league is in setup status

### US-008: Draft Lobby & Preparation Tests

**Description:** As a developer, I want E2E tests for the pre-draft lobby experience.

**Acceptance Criteria:**

- [ ] Test: navigating to draft lobby shows member list with ready status
- [ ] Test: draft order (snake) visualization is displayed
- [ ] Test: commissioner sees "Start Draft" button in lobby
- [ ] Test: non-commissioner sees waiting state without start button

### US-009: Draft Board & Player Selection Tests

**Description:** As a developer, I want E2E tests for the core drafting experience.

**Acceptance Criteria:**

- [ ] Test: draft page renders available players list (virtualized)
- [ ] Test: players can be filtered by position (F, D, G/Team)
- [ ] Test: players can be searched by name
- [ ] Test: players can be sorted by stats (goals, assists, points)
- [ ] Test: eliminated players appear as unavailable/greyed out
- [ ] Test: clicking a player shows draft confirmation modal
- [ ] Test: confirming a pick adds the player to the user's roster sidebar
- [ ] Test: after picking, the current pick advances to the next drafter
- [ ] Test: roster sidebar shows filled/empty slots with position requirements

### US-010: Player Comparison Tests

**Description:** As a developer, I want E2E tests for the player comparison feature used during drafts.

**Acceptance Criteria:**

- [ ] Test: adding a player to the compare tray shows the compare bar
- [ ] Test: up to 4 players can be compared side-by-side
- [ ] Test: compare tray shows stat comparison (goals, assists, points)
- [ ] Test: players can be removed from the compare tray
- [ ] Test: compare tray persists across draft page interactions

### US-011: Roster Management Tests

**Description:** As a developer, I want E2E tests for viewing and managing rosters.

**Acceptance Criteria:**

- [ ] Test: roster page shows all active slots (5F, 3D, 1G) with player details
- [ ] Test: IR slots (IR_F, IR_D) are displayed with correct state
- [ ] Test: each player shows current round stats and points
- [ ] Test: total team points are calculated and displayed
- [ ] Test: roster page is accessible from league dashboard navigation

### US-012: IR Activation Flow Tests

**Description:** As a developer, I want E2E tests for the injured reserve activation flow.

**Acceptance Criteria:**

- [ ] Test: injured player on roster shows IR activation option
- [ ] Test: clicking activate opens IR activation modal
- [ ] Test: modal shows eligible replacement players (same position only)
- [ ] Test: modal displays point differential preview
- [ ] Test: confirming activation updates roster and recalculates points
- [ ] Test: position mismatch replacements are not offered

### US-013: Standings & Scoring Tests

**Description:** As a developer, I want E2E tests for standings and scoring history.

**Acceptance Criteria:**

- [ ] Test: standings page shows all league members ranked by total points
- [ ] Test: points breakdown is displayed (player points, goalie points)
- [ ] Test: round-by-round points columns are shown
- [ ] Test: current user's row is highlighted
- [ ] Test: CSV export button downloads standings data
- [ ] Test: scoring history page shows scoring events with filters
- [ ] Test: scoring events can be filtered by player, team, and date

### US-014: Round Transition Tests

**Description:** As a developer, I want E2E tests for the round transition and re-draft flow.

**Acceptance Criteria:**

- [ ] Test: round transition page shows previous round final standings
- [ ] Test: new draft order (worst-to-best, snake) is displayed
- [ ] Test: eliminated players are removed from the draft pool
- [ ] Test: commissioner can trigger new round draft

### US-015: Mobile Viewport Tests

**Description:** As a developer, I want E2E tests that verify the app works on mobile viewports.

**Acceptance Criteria:**

- [ ] Test: mobile viewport (375×667) shows bottom navigation instead of desktop sidebar
- [ ] Test: draft page is usable on mobile viewport (scrolling, filtering, picking)
- [ ] Test: roster page renders correctly on mobile
- [ ] Test: league dashboard is navigable on mobile
- [ ] Test: modals render as bottom sheets on mobile viewports

### US-016: Navigation & Routing Tests

**Description:** As a developer, I want E2E tests that verify app-wide navigation and routing.

**Acceptance Criteria:**

- [ ] Test: all main nav links navigate to the correct pages
- [ ] Test: browser back/forward navigation works correctly
- [ ] Test: deep-linking to any protected route redirects to login when unauthenticated
- [ ] Test: deep-linking to a valid route when authenticated loads the correct page
- [ ] Test: 404/unknown routes show an appropriate error page or redirect

### US-017: GitHub Actions CI Integration

**Description:** As a developer, I want Playwright tests to run automatically in CI on every pull request.

**Acceptance Criteria:**

- [ ] Playwright tests run as a step in the existing CI workflow (or a dedicated E2E job)
- [ ] CI installs Playwright browsers via `npx playwright install --with-deps chromium`
- [ ] CI builds the web app, then runs Playwright against the built output (not dev server)
- [ ] Test results are uploaded as CI artifacts (HTML report + trace files on failure)
- [ ] CI job fails the PR if any Playwright test fails
- [ ] CI uses caching for Playwright browser binaries to speed up runs

### US-018: Error State & Edge Case Tests

**Description:** As a developer, I want E2E tests for error handling and edge cases.

**Acceptance Criteria:**

- [ ] Test: network failure during data fetch shows error boundary/fallback UI
- [ ] Test: Supabase returning 401 triggers re-authentication flow
- [ ] Test: submitting forms with server-side validation errors shows error messages
- [ ] Test: loading states are displayed while data is being fetched
- [ ] Test: empty states are shown for leagues with no members, drafts with no picks, etc.

## Functional Requirements

- FR-1: The `packages/e2e` project must be scaffolded using the **@nx/playwright** plugin (e.g., `nx g @nx/playwright:configuration`) so that Nx manages the `e2e` target, caching, and affected detection natively. Playwright and Chromium are installed as part of this plugin setup.
- FR-2: All Supabase API calls (REST, Auth, Realtime) must be intercepted and mocked at the network level using `page.route()` and `page.routeWebSocket()` (or equivalent)
- FR-3: Mock data factories must produce type-safe data matching `@sportsnot/types` interfaces
- FR-4: Tests must use Playwright's `test.describe()` and `test()` structure with descriptive names
- FR-5: Each test file must be focused on a single user flow or page (e.g., `auth.spec.ts`, `draft.spec.ts`)
- FR-6: Shared fixtures (auth state, mock data, page helpers) must be defined using Playwright's `test.extend()` fixture system
- FR-7: Tests must not depend on execution order — each test must set up its own state via mocks
- FR-8: Mobile viewport tests must use Playwright's `page.setViewportSize()` or project-level viewport config
- FR-9: The Playwright HTML reporter must be configured for local debugging and CI artifact uploads
- FR-10: The `e2e` target for `@sportsnot/e2e` must be provided by `@nx/playwright`, using Nx's executor (`@nx/playwright:playwright`) so that Nx caching, affected commands, and task orchestration apply automatically
- FR-11: Tests must have reasonable timeouts (30s default, configurable per test for slower flows like drafting)
- FR-12: Page Object Model (POM) pattern should be used for complex pages (draft board, roster management) to keep tests readable

## Non-Goals

- No visual regression / screenshot comparison testing (can be added later)
- No cross-browser testing beyond Chromium (Firefox/WebKit out of scope)
- No real Supabase instance or database seeding — all network-mocked
- No performance/load testing
- No accessibility (a11y) audit testing (existing Mantine components handle this; can be added separately)
- No testing of Supabase Edge Functions or database migrations
- No testing of the NHL API integration against real NHL servers

## Design Considerations

- Use Playwright's built-in fixture system (`test.extend()`) for composable test setup — avoid `beforeAll`/`beforeEach` boilerplate
- Organize tests by feature area, mirroring the app's route structure:
  ```
  packages/e2e/
  ├── playwright.config.ts
  ├── package.json
  ├── fixtures/
  │   ├── auth.fixture.ts          # Authenticated/unauthenticated page fixtures
  │   ├── supabase-mock.fixture.ts # Supabase route interception
  │   └── data-factories.ts        # Mock data generators
  ├── page-objects/
  │   ├── dashboard.page.ts
  │   ├── draft.page.ts
  │   ├── roster.page.ts
  │   └── ...
  ├── tests/
  │   ├── auth.spec.ts
  │   ├── dashboard.spec.ts
  │   ├── league-create.spec.ts
  │   ├── league-join.spec.ts
  │   ├── league-dashboard.spec.ts
  │   ├── draft-lobby.spec.ts
  │   ├── draft-board.spec.ts
  │   ├── player-compare.spec.ts
  │   ├── roster.spec.ts
  │   ├── ir-activation.spec.ts
  │   ├── standings.spec.ts
  │   ├── scoring-history.spec.ts
  │   ├── round-transition.spec.ts
  │   ├── navigation.spec.ts
  │   ├── mobile.spec.ts
  │   └── error-states.spec.ts
  └── project.json
  ```
- Page Object Models should expose semantic methods (e.g., `draftPage.pickPlayer('Connor McDavid')` not `page.click('.player-row:nth-child(3) button')`)
- Leverage `data-testid` attributes in the app where existing selectors are fragile — add them surgically as needed

## Technical Considerations

- **Dev server vs. production build:** CI should test against a production build (`nx build @sportsnot/web` then `npx serve` or `playwright.config.ts` `webServer` with preview). Local development can use the dev server for faster iteration. The `@nx/playwright` executor handles orchestration of the web server and test run.
- **Nx plugin benefits:** Using `@nx/playwright` provides automatic target inference, Nx caching of test results (when inputs haven't changed), `nx affected` support so only relevant E2E tests run on PRs, and consistent executor configuration across the team.
- **Supabase mock fidelity:** Mocks must return PostgREST-shaped responses (arrays for `.select()`, objects for `.single()`, proper error shapes). The `@supabase/supabase-js` client parses these responses, so shape matters.
- **Realtime subscriptions:** Supabase Realtime uses WebSockets. Tests should stub the WebSocket connection to prevent hanging. Playwright's `page.routeWebSocket()` or closing connections immediately is sufficient.
- **React Query caching:** Tests may need to account for TanStack Query's caching behavior. Mocking at the network level means the cache works naturally, but tests should wait for data to render (use `page.waitForSelector()` or Playwright's auto-waiting).
- **Environment variables:** The web app requires `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY`. These must be set to mock-compatible values during E2E test runs.
- **Playwright browser caching in CI:** Use `actions/cache` to cache `~/.cache/ms-playwright` to avoid downloading browsers on every CI run.
- **SPA routing:** GitHub Pages uses a 404.html redirect hack for client-side routing. E2E tests should verify deep-link navigation works correctly through this mechanism when testing against a production build.

## Success Metrics

- All critical user flows (auth, league CRUD, drafting, roster management, standings) have at least one happy-path E2E test
- Playwright tests run in CI in under 5 minutes (Chromium only, mocked backend)
- Zero flaky tests at launch — all tests are deterministic via network mocking
- New features can have E2E tests added by following established patterns (fixtures, page objects, data factories)
- Developers can run the full E2E suite locally with a single command (`nx e2e @sportsnot/e2e`)

## Open Questions

- Should `data-testid` attributes be added proactively to all interactive elements, or only when existing selectors prove fragile during test authoring?
- Should Playwright trace recording be enabled by default on CI (increases artifact size but invaluable for debugging failures)?
- Should there be a "smoke test" subset that runs on every commit to main, with the full suite running only on PRs?
- Should the NHL API client calls (to `api-web.nhle.com`) also be mocked, or are they already indirectly mocked via the Supabase layer?
