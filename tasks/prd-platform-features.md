# PRD: SportsNot Platform Features (P0–P2)

## Introduction

SportsNot is an NHL playoff fantasy hockey app built as an Nx monorepo (React 19, Supabase, Mantine, TypeScript). The platform currently supports league management, snake drafts, roster management, and standings — but lacks real-time scoring, player comparison tools, mobile-first navigation, notifications, and comprehensive test coverage.

This PRD defines all features across three priority tiers (P0 Critical MVP, P1 Significant, P2 Minor) to bring the platform to a polished, production-ready state. The features are designed to work within the existing architecture: Supabase (PostgreSQL + Realtime + Edge Functions), TanStack React Query, Mantine UI, and Vanilla Extract CSS.

---

## Goals

- Enable real-time scoring updates so users see live point totals without manual refresh
- Provide side-by-side player comparison tools to support draft and roster decisions
- Deliver a mobile-first experience with bottom navigation and responsive table/card layouts
- Add a live games widget so users can track NHL scores and see which rostered players are active
- Build a notification system for draft events and scoring milestones
- Create a scoring history page for transparent point breakdowns
- Extract reusable UI components into `@sportsnot/ui` for consistency and maintainability
- Achieve comprehensive test coverage across all packages
- Add progressive web app capabilities (offline caching + push notifications)

---

## User Stories

### 🔴 P0 — Critical MVP

---

#### Feature: Player Comparison Tools

---

##### US-001: Compare Tray — Add/Remove Players for Comparison

**Description:** As a user, I want to add players to a comparison tray while browsing so that I can collect candidates before comparing them side-by-side.

**Acceptance Criteria:**
- [ ] A floating "Compare" tray is visible at the bottom of the screen when 1+ players are added
- [ ] Tray shows player avatars/names and a count badge (e.g., "Compare (2)")
- [ ] Users can add players via a "Compare" button/icon on PlayerCard components
- [ ] Users can remove individual players from the tray by clicking an "×" on their avatar
- [ ] Tray supports 2–4 players; the add button is disabled when 4 players are selected
- [ ] Tray state persists across page navigation within the same session (React context)
- [ ] A "Clear All" button empties the tray
- [ ] Typecheck/lint passes

##### US-002: Comparison Modal — Side-by-Side Stat View

**Description:** As a user, I want to open a comparison modal from the tray so that I can see 2–4 players' stats side-by-side with differences highlighted.

**Acceptance Criteria:**
- [ ] Clicking "Compare" button on the tray opens a full-screen modal
- [ ] Modal displays players in columns (2–4 columns depending on selection count)
- [ ] Skater stats shown: goals, assists, points, games played, +/-, points per game
- [ ] Goalie stats shown: wins, shutouts, GAA, save percentage, games played
- [ ] The highest value in each stat row is highlighted (bold + accent color)
- [ ] Each player column shows: name, team, position, headshot
- [ ] Fantasy points earned (from roster) are shown if the player is on a user's roster
- [ ] Modal can be closed via "×" button or Escape key
- [ ] Typecheck/lint passes
- [ ] Verify in browser if browser testing tools are available

##### US-003: Integrate Compare into DraftPage

**Description:** As a user, I want to compare players while drafting so that I can make informed pick decisions.

**Acceptance Criteria:**
- [ ] Each player row/card in the DraftPage player list has an "Add to Compare" action
- [ ] Compare tray is visible on the DraftPage without obstructing the draft board
- [ ] Users can open the comparison modal, review stats, close it, and continue drafting
- [ ] Already-drafted players are visually distinguished in the comparison modal
- [ ] Typecheck/lint passes
- [ ] Verify in browser if browser testing tools are available

##### US-004: Integrate Compare into RosterPage

**Description:** As a user, I want to compare players from my roster page so that I can evaluate roster decisions.

**Acceptance Criteria:**
- [ ] Each player in the RosterPage roster slots has an "Add to Compare" action
- [ ] Users can compare their rostered players against each other
- [ ] Points earned are shown in the comparison for rostered players
- [ ] Typecheck/lint passes
- [ ] Verify in browser if browser testing tools are available

---

#### Feature: Live Scoring Updates

---

##### US-005: Client-Side Stat Sync via Supabase RPC

**Description:** As a developer, I need a mechanism to fetch fresh stats from the NHL API and write them to Supabase so that player/team stats stay current.

**Acceptance Criteria:**
- [ ] Create a Supabase RPC function `sync_player_stats` that accepts a list of player IDs
- [ ] Create a Supabase RPC function `sync_team_stats` that accepts a list of team abbreviations
- [ ] The client calls these RPCs on a polling interval (configurable, default 60 seconds) during active games
- [ ] RPC functions use `@sportsnot/nhl-api` data to upsert into `player_stats_cache` and `team_stats_cache`
- [ ] Stats include: goals, assists, games_played, is_injured (players); wins, shutouts, is_eliminated (teams)
- [ ] Stale data is updated, new data is inserted — no duplicates
- [ ] Typecheck/lint passes

##### US-006: Database Triggers for Auto-Recalculating Points

**Description:** As a system, I need to automatically recalculate roster points when stats change so that standings are always accurate.

**Acceptance Criteria:**
- [ ] Create a PostgreSQL trigger on `player_stats_cache` that fires AFTER INSERT OR UPDATE
- [ ] Create a PostgreSQL trigger on `team_stats_cache` that fires AFTER INSERT OR UPDATE
- [ ] Triggers call `calculate_player_points()` / `calculate_goalie_points()` logic (using scoring rules: goal=1, assist=1, win=2, shutout=4 replacing win)
- [ ] Updated points are written to `rosters.points_earned` for all active roster slots referencing the changed player/team
- [ ] `league_members.total_points` is recalculated by summing active roster slot points
- [ ] Trigger logic is idempotent (re-running produces the same result)
- [ ] Migration file is created for the triggers
- [ ] Typecheck/lint passes

##### US-007: Client-Side Live Scoring Indicators

**Description:** As a user, I want to see visual indicators when scores update in real-time so that I know data is fresh.

**Acceptance Criteria:**
- [ ] A "Last updated" timestamp is shown on StandingsPage and RosterPage
- [ ] When a point total changes, the number briefly animates (pulse/highlight effect)
- [ ] A small "live" indicator (green dot + "LIVE") appears when active games are in progress
- [ ] Point changes show a brief "+N" animation next to the updated total
- [ ] Supabase Realtime subscription on `rosters` and `league_members` tables pushes updates to the client
- [ ] Typecheck/lint passes
- [ ] Verify in browser if browser testing tools are available

##### US-008: Stat Sync Polling Hook

**Description:** As a developer, I need a React hook that manages the polling lifecycle for stat syncs so that components can trigger and control live updates.

**Acceptance Criteria:**
- [ ] Create `useStatSync(leagueId)` hook in `@sportsnot/supabase`
- [ ] Hook polls the sync RPC every 60 seconds when there are active NHL games
- [ ] Hook stops polling when no games are active (checks via `getScoresNow()`)
- [ ] Hook exposes: `lastSyncedAt`, `isSyncing`, `syncNow()` (manual trigger), `isLive`
- [ ] Hook uses React Query's `refetchInterval` for efficient polling
- [ ] Polling pauses when the browser tab is not visible (`document.hidden`)
- [ ] Typecheck/lint passes

---

#### Feature: Mobile-Responsive Design

---

##### US-009: Bottom Navigation Bar for Mobile

**Description:** As a mobile user, I want a bottom navigation bar so that I can quickly switch between main sections with my thumb.

**Acceptance Criteria:**
- [ ] Bottom nav bar appears on screens below `sm` breakpoint (Mantine: 768px)
- [ ] Tabs: Home (dashboard icon), Draft (list icon), Roster (users icon), Standings (trophy icon), Profile (user icon)
- [ ] Active tab is highlighted with accent color
- [ ] Bottom nav replaces the top header navigation links on mobile
- [ ] Top AppShell header remains but shows only logo and user avatar on mobile
- [ ] Bottom nav is fixed to the viewport bottom and does not scroll with content
- [ ] Page content has bottom padding to avoid being hidden behind the nav bar
- [ ] Typecheck/lint passes
- [ ] Verify in browser if browser testing tools are available

##### US-010: ResponsiveTable — Table-to-Cards Pattern

**Description:** As a mobile user, I want data tables to transform into card layouts on small screens so that I can read information without horizontal scrolling.

**Acceptance Criteria:**
- [ ] Create a `ResponsiveTable` component in `@sportsnot/ui`
- [ ] On desktop (`md`+): renders as a standard Mantine `Table` with columns and rows
- [ ] On mobile (below `md`): renders as a vertical stack of cards, each card representing one row
- [ ] Each card shows all column values as labeled key-value pairs
- [ ] Column headers become labels in card view (e.g., "Goals: 5", "Assists: 3")
- [ ] Component accepts standard table props: `columns`, `data`, `onRowClick`, `sortable`
- [ ] Sorting works in both table and card views
- [ ] Typecheck/lint passes
- [ ] Verify in browser if browser testing tools are available

##### US-011: Responsive Draft Interface

**Description:** As a mobile user, I want the draft interface to work on my phone so that I can participate in drafts from anywhere.

**Acceptance Criteria:**
- [ ] DraftPage uses a tabbed layout on mobile (below `sm`): "Players", "Board", "My Picks"
- [ ] "Players" tab shows the available player list as cards (using ResponsiveTable)
- [ ] "Board" tab shows the draft board (scrollable grid with pick cells)
- [ ] "My Picks" tab shows the current user's picks so far
- [ ] Only one tab is visible at a time on mobile; all three are visible side-by-side on desktop
- [ ] The "Make Pick" action is accessible regardless of which tab is active (sticky footer button)
- [ ] Draft timer/turn indicator is always visible at the top on mobile
- [ ] Typecheck/lint passes
- [ ] Verify in browser if browser testing tools are available

##### US-012: Responsive Roster and Standings Pages

**Description:** As a mobile user, I want the roster and standings pages to be usable on my phone.

**Acceptance Criteria:**
- [ ] RosterPage uses `ResponsiveTable` for roster slot display
- [ ] Roster actions (activate IR, swap) work via tap interactions on mobile
- [ ] StandingsPage uses `ResponsiveTable` for the standings table
- [ ] Member names in standings truncate gracefully on small screens
- [ ] Typecheck/lint passes
- [ ] Verify in browser if browser testing tools are available

---

### 🟡 P1 — Significant

---

#### Feature: Live Games Widget

---

##### US-013: Real-Time NHL Scores Widget

**Description:** As a user, I want to see live NHL game scores so that I can follow the action without leaving the app.

**Acceptance Criteria:**
- [ ] A `LiveGamesWidget` component displays current/recent NHL game scores
- [ ] Each game card shows: team logos/abbreviations, current score, period/time remaining, game status (live/final/upcoming)
- [ ] Widget uses `getScoresNow()` from `@sportsnot/nhl-api` with 30-second polling
- [ ] Widget is displayed on the DashboardPage and LeagueDashboardPage
- [ ] Widget is horizontally scrollable on mobile, grid layout on desktop
- [ ] Typecheck/lint passes
- [ ] Verify in browser if browser testing tools are available

##### US-014: Rostered-Player Highlighting in Games Widget

**Description:** As a user, I want to see which of my rostered players are playing in live games so that I know which games matter to me.

**Acceptance Criteria:**
- [ ] Games containing a user's rostered players are visually highlighted (accent border or badge)
- [ ] A small indicator shows how many of the user's rostered players are in each game
- [ ] Clicking a highlighted game shows which specific rostered players are playing
- [ ] Highlighting is league-context-aware (uses active league's roster)
- [ ] Typecheck/lint passes
- [ ] Verify in browser if browser testing tools are available

---

#### Feature: Notifications System

---

##### US-015: Notification Context and Store

**Description:** As a developer, I need a client-side notification system so that components can push and consume notifications.

**Acceptance Criteria:**
- [ ] Create a `NotificationContext` in `@sportsnot/web` using React Context
- [ ] Notification shape: `{ id, type, title, message, timestamp, read, leagueId? }`
- [ ] Types: `'draft'`, `'scoring'`, `'league'`, `'system'`
- [ ] Context provides: `notifications[]`, `unreadCount`, `markAsRead(id)`, `markAllRead()`, `addNotification()`
- [ ] Notifications persist in localStorage (cleared on sign-out)
- [ ] Maximum 50 notifications stored (oldest removed first)
- [ ] Typecheck/lint passes

##### US-016: Toast Alerts for Real-Time Events

**Description:** As a user, I want to see brief toast alerts when important events happen so that I'm informed without disrupting my workflow.

**Acceptance Criteria:**
- [ ] Toast notifications appear in the top-right corner of the screen
- [ ] Draft events that trigger toasts: "It's your turn to pick!", "Player X was drafted by Team Y"
- [ ] Scoring events that trigger toasts: "Player X scored a goal! (+1 pt)", "Team X recorded a shutout! (+4 pts)"
- [ ] Toasts auto-dismiss after 5 seconds
- [ ] Toasts are color-coded by type (draft=blue, scoring=green, league=yellow)
- [ ] Clicking a toast marks it as read and navigates to the relevant page
- [ ] Maximum 3 toasts visible at once (oldest dismissed first)
- [ ] Toasts use Mantine's `notifications` system
- [ ] Typecheck/lint passes
- [ ] Verify in browser if browser testing tools are available

##### US-017: Notification Center (Bell Icon)

**Description:** As a user, I want to access a notification center from the header so that I can review past alerts.

**Acceptance Criteria:**
- [ ] A bell icon in the AppShell header shows unread notification count as a badge
- [ ] Clicking the bell opens a dropdown/drawer listing all notifications
- [ ] Each notification shows: icon (by type), title, message preview, relative timestamp ("2m ago")
- [ ] Unread notifications are visually distinct (bold text, accent left-border)
- [ ] "Mark all as read" button at the top of the list
- [ ] Clicking a notification marks it as read and navigates to the relevant context
- [ ] Empty state: "No notifications yet" with icon
- [ ] Typecheck/lint passes
- [ ] Verify in browser if browser testing tools are available

---

#### Feature: Scoring History Page

---

##### US-018: Scoring Events Database Table

**Description:** As a developer, I need a `scoring_events` table so that individual scoring events are tracked and queryable.

**Acceptance Criteria:**
- [ ] Create `scoring_events` table with columns: `id`, `league_id`, `member_id`, `roster_id`, `player_id` (nullable), `team_id` (nullable), `event_type` ('goal' | 'assist' | 'win' | 'shutout'), `points`, `game_id`, `game_date`, `description`, `created_at`
- [ ] Add foreign keys to `leagues`, `league_members`, and `rosters`
- [ ] Add index on `(league_id, member_id, created_at)` for efficient queries
- [ ] Add RLS policies: users can read scoring events for leagues they belong to
- [ ] Enable Realtime on the table
- [ ] Migration file created and applied
- [ ] Typecheck/lint passes

##### US-019: Populate Scoring Events from Stat Syncs

**Description:** As a system, I need to create scoring event records when stats change so that users can see a history of how points were earned.

**Acceptance Criteria:**
- [ ] When `player_stats_cache` is updated and goals/assists increase, create corresponding `scoring_events` records
- [ ] When `team_stats_cache` is updated and wins/shutouts increase, create corresponding `scoring_events` records
- [ ] Each event captures the delta (e.g., if goals went from 3→4, create one "goal" event)
- [ ] Events are linked to the correct roster slot and league member
- [ ] Duplicate events are prevented (idempotent based on game_id + player_id + event_type)
- [ ] Typecheck/lint passes

##### US-020: Scoring History Page UI

**Description:** As a user, I want to view a timeline of scoring events so that I can see how points were earned over time.

**Acceptance Criteria:**
- [ ] New route: `/scoring/:leagueId` accessible from league navigation
- [ ] Page shows a chronological timeline of scoring events (newest first)
- [ ] Each event shows: player/team name, event type icon, points earned, game info, timestamp
- [ ] Filter by: player/team, event type (goal/assist/win/shutout), date range
- [ ] Filter by league member ("Show only my events" toggle)
- [ ] Events are grouped by game date with date headers
- [ ] Pagination or infinite scroll for large event lists (20 events per page)
- [ ] Uses `ResponsiveTable` for mobile compatibility
- [ ] Typecheck/lint passes
- [ ] Verify in browser if browser testing tools are available

---

#### Feature: Reusable UI Components

---

##### US-021: Extract TeamCard Component

**Description:** As a developer, I want a reusable `TeamCard` component in `@sportsnot/ui` so that team information is displayed consistently.

**Acceptance Criteria:**
- [ ] `TeamCard` component in `@sportsnot/ui` with props:
  ```typescript
  interface TeamCardProps {
    teamName: string;
    teamAbbrev: string;
    logoUrl?: string;
    record?: { wins: number; losses: number };
    points?: number;
    isEliminated?: boolean;
    onClick?: () => void;
    size?: 'sm' | 'md' | 'lg';
  }
  ```
- [ ] Shows team logo/abbreviation, name, record, and points
- [ ] Eliminated teams shown with reduced opacity and strikethrough
- [ ] Size variants control overall card dimensions
- [ ] Typecheck/lint passes
- [ ] Verify in browser if browser testing tools are available

##### US-022: Extract RosterSlot Component

**Description:** As a developer, I want a reusable `RosterSlot` component so that roster positions are displayed consistently across pages.

**Acceptance Criteria:**
- [ ] `RosterSlot` component in `@sportsnot/ui` with props:
  ```typescript
  interface RosterSlotProps {
    position: 'F' | 'D' | 'G' | 'IR_F' | 'IR_D';
    player?: {
      name: string;
      teamAbbrev: string;
      headshot?: string;
      stats?: Record<string, number>;
    };
    pointsEarned?: number;
    isActive?: boolean;
    isEmpty?: boolean;
    onAction?: (action: 'compare' | 'activate' | 'details') => void;
    actions?: ('compare' | 'activate' | 'details')[];
  }
  ```
- [ ] Empty slots show a dashed border with position label and "Empty" text
- [ ] Filled slots show player info with position badge and points
- [ ] IR slots are visually distinct (different background/border color)
- [ ] Action buttons render based on `actions` prop
- [ ] Typecheck/lint passes
- [ ] Verify in browser if browser testing tools are available

##### US-023: Extract PointsBadge Component

**Description:** As a developer, I want a reusable `PointsBadge` component for displaying point values consistently.

**Acceptance Criteria:**
- [ ] `PointsBadge` component in `@sportsnot/ui` with props:
  ```typescript
  interface PointsBadgeProps {
    points: number;
    size?: 'sm' | 'md' | 'lg';
    animate?: boolean;
    delta?: number; // shows "+N" indicator
    variant?: 'filled' | 'outline' | 'subtle';
  }
  ```
- [ ] Displays point value with consistent styling
- [ ] When `animate` is true, pulses briefly on value change
- [ ] When `delta` is provided, shows a small "+N" or "−N" indicator
- [ ] Color scales with point value (gray=0, accent=positive)
- [ ] Typecheck/lint passes
- [ ] Verify in browser if browser testing tools are available

##### US-024: Extract StatRow Component

**Description:** As a developer, I want a reusable `StatRow` component for displaying labeled stat values.

**Acceptance Criteria:**
- [ ] `StatRow` component in `@sportsnot/ui` with props:
  ```typescript
  interface StatRowProps {
    label: string;
    value: string | number;
    highlight?: boolean;
    trend?: 'up' | 'down' | 'neutral';
    compact?: boolean;
  }
  ```
- [ ] Renders a horizontal label-value pair with consistent alignment
- [ ] `highlight` applies bold + accent color to the value
- [ ] `trend` shows a small arrow icon (green up, red down, gray neutral)
- [ ] `compact` reduces spacing for use in dense layouts
- [ ] Typecheck/lint passes
- [ ] Verify in browser if browser testing tools are available

##### US-025: Extract PositionBadge Component

**Description:** As a developer, I want a reusable `PositionBadge` for displaying player positions with consistent colors.

**Acceptance Criteria:**
- [ ] `PositionBadge` component in `@sportsnot/ui` with props:
  ```typescript
  interface PositionBadgeProps {
    position: 'F' | 'D' | 'G' | 'IR_F' | 'IR_D' | 'C' | 'LW' | 'RW';
    size?: 'sm' | 'md';
    variant?: 'filled' | 'outline';
  }
  ```
- [ ] Each position has a distinct color: F=blue, D=green, G=orange, IR_*=red, C/LW/RW=blue variants
- [ ] Renders as a Mantine `Badge` with the position abbreviation
- [ ] Typecheck/lint passes
- [ ] Verify in browser if browser testing tools are available

##### US-026: Extract LiveIndicator Component

**Description:** As a developer, I want a reusable `LiveIndicator` component for showing real-time status.

**Acceptance Criteria:**
- [ ] `LiveIndicator` component in `@sportsnot/ui` with props:
  ```typescript
  interface LiveIndicatorProps {
    isLive: boolean;
    lastUpdated?: Date;
    showTimestamp?: boolean;
    size?: 'sm' | 'md';
  }
  ```
- [ ] When `isLive` is true: shows a pulsing green dot with "LIVE" text
- [ ] When `isLive` is false: shows a gray dot with "OFFLINE" or hidden entirely
- [ ] When `showTimestamp` is true: shows "Updated 2m ago" relative timestamp
- [ ] Typecheck/lint passes
- [ ] Verify in browser if browser testing tools are available

##### US-027: Extract GameCard Component

**Description:** As a developer, I want a reusable `GameCard` component for displaying NHL game scores.

**Acceptance Criteria:**
- [ ] `GameCard` component in `@sportsnot/ui` with props:
  ```typescript
  interface GameCardProps {
    homeTeam: { abbrev: string; score: number; logoUrl?: string };
    awayTeam: { abbrev: string; score: number; logoUrl?: string };
    status: 'upcoming' | 'live' | 'final';
    period?: string;
    timeRemaining?: string;
    startTime?: Date;
    highlight?: boolean;
    highlightReason?: string;
    onClick?: () => void;
  }
  ```
- [ ] Shows both teams with scores, game status, and period info
- [ ] Live games show pulsing indicator and current period/time
- [ ] Final games show "FINAL" badge
- [ ] Upcoming games show scheduled start time
- [ ] `highlight` adds an accent border for games with rostered players
- [ ] Typecheck/lint passes
- [ ] Verify in browser if browser testing tools are available

---

#### Feature: Testing Coverage

---

##### US-028: Component Tests for @sportsnot/ui

**Description:** As a developer, I want component tests for all `@sportsnot/ui` components so that I can refactor with confidence.

**Acceptance Criteria:**
- [ ] Tests for `PlayerCard`: renders player info, handles missing data, shows points when provided
- [ ] Tests for `TeamCard`: renders team info, shows eliminated state, handles click
- [ ] Tests for `RosterSlot`: renders empty state, filled state, IR state, action buttons
- [ ] Tests for `PointsBadge`: renders points, shows delta, handles animation prop
- [ ] Tests for `StatRow`: renders label/value, highlight state, trend icons
- [ ] Tests for `PositionBadge`: renders each position with correct color
- [ ] Tests for `LiveIndicator`: live/offline states, timestamp display
- [ ] Tests for `GameCard`: all game statuses, highlight state
- [ ] Tests for `ResponsiveTable`: table and card views (mock viewport)
- [ ] All tests use React Testing Library (`@testing-library/react`)
- [ ] Tests run via `rstest` framework
- [ ] Typecheck/lint passes

##### US-029: Component Tests for Key Web Pages

**Description:** As a developer, I want rendering tests for key pages so that regressions are caught early.

**Acceptance Criteria:**
- [ ] Tests for `DashboardPage`: renders league grid, handles empty state, shows loading
- [ ] Tests for `DraftPage`: renders player list, draft board, handles turn indicator
- [ ] Tests for `RosterPage`: renders roster slots, handles IR activation
- [ ] Tests for `StandingsPage`: renders standings table, shows point totals
- [ ] Tests for `LoginPage`: renders login form, handles magic link flow
- [ ] All page tests mock Supabase hooks and React Router
- [ ] Tests use React Testing Library
- [ ] Tests run via `rstest` framework
- [ ] Typecheck/lint passes

##### US-030: Hook Tests for @sportsnot/supabase

**Description:** As a developer, I want tests for data hooks so that data fetching logic is verified.

**Acceptance Criteria:**
- [ ] Tests for `useAuth`: sign-in, sign-out, session restoration
- [ ] Tests for `useLeagues`, `useLeague`: data fetching, error handling, loading states
- [ ] Tests for `useDraft`, `useMakePick`: draft flow, pick validation
- [ ] Tests for `useRoster`: roster data, IR activation
- [ ] Tests for `useStatSync`: polling lifecycle, pause on hidden tab, manual sync
- [ ] All hooks tested with `@testing-library/react` `renderHook`
- [ ] Supabase client is mocked (no real API calls)
- [ ] Typecheck/lint passes

##### US-032: Coverage Targets and CI Configuration

**Description:** As a developer, I want coverage targets defined and enforced so that test quality is maintained.

**Acceptance Criteria:**
- [ ] Configure rstest to output coverage reports
- [ ] Coverage targets per package:
  - `@sportsnot/utils`: 90% line coverage (currently well-tested)
  - `@sportsnot/nhl-api`: 70% line coverage
  - `@sportsnot/supabase`: 70% line coverage
  - `@sportsnot/ui`: 80% line coverage
  - `@sportsnot/web`: 60% line coverage
- [ ] Coverage report is generated on `yarn test`
- [ ] CI fails if coverage drops below targets (when CI is set up)
- [ ] Typecheck/lint passes

---

### 🟢 P2 — Minor

---

##### US-033: PlayerDetailModal

**Description:** As a user, I want to click on a player to see their full stat sheet and game log in a modal so that I can evaluate them in detail.

**Acceptance Criteria:**
- [ ] Clicking a player name/card anywhere in the app opens a `PlayerDetailModal`
- [ ] Modal shows: headshot, name, team, position, full stat line, game-by-game log
- [ ] Game log shows last 10 games with stats per game
- [ ] Data fetched via `getPlayerGameLog()` from `@sportsnot/nhl-api`
- [ ] "Add to Compare" button in the modal header
- [ ] Loading skeleton while data fetches
- [ ] Typecheck/lint passes
- [ ] Verify in browser if browser testing tools are available

##### US-034: CSV Export for Rosters and Standings

**Description:** As a user, I want to export my roster and league standings as CSV so that I can analyze data in a spreadsheet.

**Acceptance Criteria:**
- [ ] "Export CSV" button on RosterPage exports current roster with stats and points
- [ ] "Export CSV" button on StandingsPage exports standings table
- [ ] CSV includes all visible columns with headers
- [ ] File is named `sportsnot-{type}-{leagueName}-{date}.csv`
- [ ] Export works on mobile (triggers download)
- [ ] Typecheck/lint passes

##### US-035: Service Worker — Offline Caching and Push Notifications

**Description:** As a user, I want the app to work offline and send push notifications so that I stay informed even when the app isn't open.

**Acceptance Criteria:**
- [ ] Register a service worker on app load
- [ ] Cache static assets (JS, CSS, images) with cache-first strategy
- [ ] Cache API responses (rosters, standings) with stale-while-revalidate strategy
- [ ] Offline fallback page when network is unavailable
- [ ] Push notification support: request permission, subscribe to push endpoint
- [ ] Push notifications for: draft turn, scoring milestones (configurable)
- [ ] Push payload includes: title, body, icon, click action URL
- [ ] Unsubscribe option in profile settings
- [ ] Typecheck/lint passes

##### US-036: Virtualized Lists for Large Data Sets

**Description:** As a user, I want player lists and game logs to load efficiently so that the app stays fast even with hundreds of items.

**Acceptance Criteria:**
- [ ] Player list in DraftPage uses virtualization for 500+ player lists
- [ ] Game log in PlayerDetailModal uses virtualization if log exceeds 20 entries
- [ ] Use `@tanstack/react-virtual` for virtualization
- [ ] Scroll position is preserved when switching tabs or returning to the list
- [ ] Visible items render at 60fps (no jank during scroll)
- [ ] Typecheck/lint passes
- [ ] Verify in browser if browser testing tools are available

---

## Functional Requirements

### Player Comparison
- FR-1: The system must maintain a client-side comparison tray (React context) that holds 2–4 selected players
- FR-2: The comparison modal must display player stats in a side-by-side column layout with the best value in each row highlighted
- FR-3: The comparison tray and modal must be accessible from both DraftPage and RosterPage

### Live Scoring
- FR-4: The client must poll NHL stats via Supabase RPC functions on a 60-second interval during active games
- FR-5: PostgreSQL triggers must auto-recalculate `rosters.points_earned` when `player_stats_cache` or `team_stats_cache` are updated
- FR-6: PostgreSQL triggers must auto-recalculate `league_members.total_points` when roster points change
- FR-7: The client must subscribe to Supabase Realtime on `rosters` and `league_members` tables to receive live point updates
- FR-8: A visual "LIVE" indicator and "Last updated" timestamp must be shown when live scoring is active

### Mobile Responsive
- FR-9: A bottom navigation bar must appear on screens below 768px with tabs: Home, Draft, Roster, Standings, Profile
- FR-10: Data tables must transform into card stacks on mobile via the `ResponsiveTable` component
- FR-11: The DraftPage must use a tabbed layout on mobile with "Players", "Board", and "My Picks" tabs
- FR-12: All pages must be usable without horizontal scrolling on screens 320px and wider

### Live Games Widget
- FR-13: The system must display live NHL game scores with 30-second polling, showing team names, scores, period, and game status
- FR-14: Games containing the user's rostered players must be visually highlighted

### Notifications
- FR-15: A client-side notification context must store up to 50 notifications in localStorage
- FR-16: Toast alerts must appear for draft turns, draft picks, goals, and shutouts — auto-dismissing after 5 seconds
- FR-17: A notification bell in the header must show unread count and provide access to the full notification list

### Scoring History
- FR-18: A `scoring_events` table must record individual scoring events (goal, assist, win, shutout) with game context
- FR-19: A scoring history page must display a filterable, chronological timeline of scoring events

### UI Components
- FR-20: Seven reusable components (TeamCard, RosterSlot, PointsBadge, StatRow, PositionBadge, LiveIndicator, GameCard) must be extracted to `@sportsnot/ui` with documented TypeScript interfaces
- FR-21: A `ResponsiveTable` component must render as a table on desktop and cards on mobile

### Testing
- FR-22: Component tests must exist for all `@sportsnot/ui` components using React Testing Library
- FR-23: Page rendering tests must exist for DashboardPage, DraftPage, RosterPage, StandingsPage, and LoginPage
- FR-24: Hook tests must exist for all `@sportsnot/supabase` data hooks
- FR-25: Coverage targets must be enforced: utils=90%, nhl-api=70%, supabase=70%, ui=80%, web=60%

### P2 Features
- FR-27: A `PlayerDetailModal` must show full stat sheet and game log for any player
- FR-28: CSV export must be available for roster and standings data
- FR-29: A service worker must cache static assets and API responses for offline use and support push notifications
- FR-30: Player lists exceeding 500 items must use virtualized rendering

---

## Non-Goals (Out of Scope)

- **No trade system** — players cannot be traded between league members
- **No custom scoring rules** — scoring is fixed (goal=1, assist=1, win=2, shutout=4)
- **No chat/messaging** — no in-app communication between league members
- **No email notifications** — notifications are client-side only (toasts + notification center + push in P2)
- **No historical season support** — app only supports the current NHL playoff season
- **No public league discovery** — leagues are private, join-by-invite-code only
- **No native mobile app** — mobile support is via responsive web + PWA (service worker)
- **No admin dashboard** — no global admin panel for managing all leagues
- **No automated draft (auto-pick)** — drafts are manual only
- **No stat projections or predictions** — only actual stats are shown

---

## Design Considerations

- **UI Framework:** All components use Mantine 8 for consistency. Avoid custom CSS where Mantine props suffice.
- **Responsive Breakpoints:** Follow Mantine defaults: `xs=576`, `sm=768`, `md=992`, `lg=1200`, `xl=1408`
- **Component Library:** Extracted components in `@sportsnot/ui` should have zero dependency on `@sportsnot/supabase` or `@sportsnot/web` — they are pure presentational components receiving data via props.
- **Color System:** Use Mantine theme colors for consistency. Position colors (F=blue, D=green, G=orange) should be defined as theme constants.
- **Animation:** Point change animations should be subtle (200ms pulse). Avoid distracting animations during draft.
- **Comparison Modal:** Use Mantine `Modal` with `fullScreen` prop on mobile, standard size on desktop. Maximum 4 columns to avoid cramped layouts.
- **Bottom Nav:** Use Mantine `AppShell.Footer` for the bottom navigation to integrate with the existing AppShell layout.
- **Notification Toasts:** Use Mantine `@mantine/notifications` package for consistent toast styling.

---

## Technical Considerations

- **Supabase RPC for Stats:** Client-side polling calls Supabase RPC functions which fetch from the NHL API and write to the database. This avoids CORS issues and keeps API keys server-side. The RPC functions should be implemented as Supabase Edge Functions (Deno/TypeScript).
- **Database Triggers:** Point recalculation triggers must be efficient — use `WHEN (OLD.* IS DISTINCT FROM NEW.*)` to avoid unnecessary recalculations. Triggers should operate on the specific changed rows, not scan entire tables.
- **Realtime Subscriptions:** Already configured for `rosters`, `league_members`, `draft_picks`, and `drafts`. Adding `scoring_events` to Realtime is straightforward.
- **React Query Integration:** All new data hooks should use TanStack React Query with the existing 5-minute stale time. Stat sync polling overrides stale time with `refetchInterval`.
- **Bundle Size:** Adding `@tanstack/react-virtual` (P2) and `@mantine/notifications` (P1) are small additions. Monitor bundle size after adding dependencies.
- **Service Worker (P2):** Use Workbox for service worker generation. Rspack supports Workbox plugins. Push notification backend requires a Supabase Edge Function to send push payloads via web-push.
- **Testing Environment:** rstest is the configured test runner. React Testing Library is already installed. Component tests should mock Supabase client, React Router, and React Query provider.
- **Scoring Events Idempotency:** Use `(game_id, player_id, event_type)` as a unique constraint to prevent duplicate scoring events when stat syncs run multiple times.

---

## Success Metrics

- **Live Scoring:** Point totals update within 90 seconds of an NHL goal/win/shutout during live games
- **Player Comparison:** Users can add players and open comparison modal in under 3 clicks
- **Mobile Responsiveness:** All pages are fully functional on 375px-wide screens (iPhone SE) with no horizontal scroll
- **Notifications:** Draft turn notifications appear within 2 seconds of turn change
- **Scoring History:** Scoring timeline loads in under 1 second for a full playoff round
- **Test Coverage:** All packages meet their coverage targets; zero failing tests in CI
- **Component Reuse:** All 7 extracted UI components are used in at least 2 different pages/features
- **Performance:** Draft page with 500+ players renders at 60fps (via virtualization in P2)

---

## Open Questions

1. **Stat Sync Rate Limiting:** Does the NHL API have rate limits that could affect 60-second polling across many concurrent leagues? May need to batch or queue sync requests.
2. **Push Notification Backend:** For P2 service worker push notifications, do we need a Supabase Edge Function to manage push subscriptions and send payloads, or should we use a third-party push service?
3. **Scoring Events Backfill:** When the `scoring_events` table is first created, should we backfill historical events from existing `player_stats_cache` data, or start fresh from that point forward?
4. **Comparison Tray Persistence:** Should the compare tray persist across browser sessions (localStorage) or only within a single session (React state)?
5. **Bottom Nav and League Context:** The bottom nav has "Draft" and "Roster" tabs which are league-specific. If the user is not in a league context, should these link to the most recently viewed league or show a league selector?
