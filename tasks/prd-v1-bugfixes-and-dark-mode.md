# PRD: V1 Bugfixes, Player Name Resolution & Dark Mode

## Introduction

After initial testing of SportsNot, several bugs and UX gaps were identified across the draft flow, roster display, scoring system, round advancement, and overall theming. This PRD covers nine items: fixing player name resolution (draft complete screen, roster page), draft history team attribution, scoring bugs (goalie points and standings aggregation), round advancement issues (roster reset and re-draft exposure), a missing navigation button, and adding dark mode support with OS/browser preference detection.

## Goals

- Fix all screens that display raw database IDs instead of player/team names
- Ensure draft history shows which team made each pick
- Fix goalie point calculation so wins/shutouts are properly credited
- Fix standings page to correctly aggregate and display team points
- Add a "Back to League" button on the Draft Complete screen
- Ensure rosters are properly reset when advancing to the next playoff round
- Expose the re-draft option when advancing to a new round
- Add dark mode with automatic OS/browser preference detection and manual toggle

## User Stories

### US-001: Draft History Shows Team Picks

**Description:** As a league member, I want the draft history to show which team made each pick so that I can track the draft strategy of every team.

**Acceptance Criteria:**

- [ ] Each entry in the draft history list displays: Pick #, Team Name, Player Full Name, Position
- [ ] Player names are resolved from `player_id` using the players dataset (not showing raw IDs)
- [ ] Team names are resolved from `league_members.team_name` via the drafting user
- [ ] Works correctly in both mock mode and live/production mode
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

---

### US-002: Draft Complete Screen Shows Player Names

**Description:** As a league member, I want the Draft Complete screen to show actual player names instead of database IDs so that I can see the final draft results clearly.

**Acceptance Criteria:**

- [ ] The draft complete results table shows player full names (first + last) instead of `player_id` numbers
- [ ] If a pick is a team-level pick (goalie), the team name is displayed instead of `team_id`
- [ ] Player/team name lookup uses the same players/teams data available in the draft context
- [ ] All columns display correctly: Pick #, Team Name, Player/Team Name, Position
- [ ] Works correctly in both mock mode and live/production mode (player/team data resolution uses the same code path or equivalent logic)
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

---

### US-003: Draft Complete Screen Navigation Button

**Description:** As a league member, I want a button on the Draft Complete screen to navigate back to the league page so that I'm not stuck on a dead-end screen.

**Acceptance Criteria:**

- [ ] A clearly visible "Back to League" (or similar) button is present on the Draft Complete screen
- [ ] Clicking the button navigates to `/league/{leagueId}` (the league dashboard)
- [ ] Button uses consistent Mantine styling with the rest of the app
- [ ] Works correctly in both mock mode and live/production mode
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

---

### US-004: My Roster Shows Player Names

**Description:** As a league member, I want my roster page to display player names instead of database IDs so that I can see who is on my team.

**Acceptance Criteria:**

- [ ] Each roster slot shows the player's full name (first + last) instead of `Player #<id>`
- [ ] If a slot is a goalie/team pick, the team name is shown instead of `Team #<id>`
- [ ] Player jersey number and/or team abbreviation may optionally be shown alongside the name
- [ ] Roster groupings (Forward, Defenseman, Goalie, IR) continue to work correctly
- [ ] Points earned per slot are still displayed correctly next to the resolved name
- [ ] Works correctly in both mock mode and live/production mode
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

---

### US-005: Fix Goalie Points Calculation

**Description:** As a league member, I want goalie points (wins and shutouts) to be correctly calculated so that standings reflect actual goalie performance.

**Acceptance Criteria:**

- [ ] Goalie wins are credited with 2 points per win (as defined in SCORING constant)
- [ ] Goalie shutouts are credited with 4 points (replacing win points, not additive)
- [ ] At the end of Round 1 in mock mode, a team like the Oilers with 4 goalie wins should show 8 points (not 0)
- [ ] Goalie points are correctly summed into `goalie_points` on the standings page
- [ ] Goalie points contribute to `total_points` for each team
- [ ] Verified with mock mode test data: simulate a full round and confirm goalie point totals
- [ ] Goalie scoring logic works in both mock mode and live/production mode (Supabase scoring backend must calculate goalie points equivalently)
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

---

### US-006: Fix Standings Page Point Aggregation

**Description:** As a league member, I want the standings page to correctly show each team's total points so that I can see the league rankings.

**Acceptance Criteria:**

- [ ] Player points (goals + assists) per team are correctly summed and displayed in the "Player Points" column
- [ ] Goalie points per team are correctly summed and displayed in the "Goalie Points" column
- [ ] Round-by-round point breakdowns (R1, R2, R3, R4) are populated correctly
- [ ] Total Points = Player Points + Goalie Points for each team
- [ ] Teams are ranked by Total Points in descending order
- [ ] Points update correctly as simulation advances (mock mode)
- [ ] Standings page works correctly in both mock mode and live/production mode (Supabase must populate the same point fields that the standings page reads)
- [ ] Verified in mock mode: after simulating Round 1, no team with active roster shows 0 total points unless they genuinely scored 0
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

---

### US-007: Dark Mode with OS/Browser Preference Detection

**Description:** As a user, I want the app to support dark mode that automatically respects my OS/browser light/dark preference so that the app is comfortable to use in any lighting condition.

**Acceptance Criteria:**

- [ ] App defaults to the user's OS/browser color scheme preference (`prefers-color-scheme` media query)
- [ ] A manual toggle is available in the app header/navigation (e.g., sun/moon icon button) to switch between light, dark, and auto modes
- [ ] Selected preference persists across sessions (localStorage)
- [ ] "Auto" mode follows the OS/browser setting dynamically (changes if OS setting changes)
- [ ] Mantine's built-in `MantineProvider` color scheme system is used (`colorScheme: 'auto'`)
- [ ] `ColorSchemeScript` is included to prevent flash of wrong theme on page load
- [ ] All existing Mantine components render correctly in dark mode
- [ ] Custom components and layouts (AppShell, cards, tables) are readable in dark mode
- [ ] No hardcoded color values that break in dark mode (check for inline `color:` or `background:` styles)
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

---

### US-008: Reset Rosters on Round Advancement

**Description:** As a league member, I want my roster to be cleared when advancing to the next playoff round so that the new round starts fresh with a new draft.

**Acceptance Criteria:**

- [ ] When the league advances to a new round, all team rosters for the new round start empty
- [ ] In live/production mode, round advancement happens automatically when a playoff round ends (based on NHL schedule/results)
- [ ] In mock mode, round advancement is triggered manually via the simulation controls
- [ ] Previous round rosters are preserved in the database for historical reference (keyed by round number)
- [ ] The My Roster page shows an empty/placeholder state for the new round before re-draft
- [ ] Points from the previous round are preserved and displayed in the standings round breakdown
- [ ] Both mock mode and live mode correctly clear rosters on round transition
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

---

### US-009: Expose Re-Draft Option on Round Advancement

**Description:** As a league commissioner, I want a clearly visible "Start Re-Draft" button when advancing to the next round so that the league can draft new rosters for the next playoff round.

**Acceptance Criteria:**

- [ ] When a round completes, the commissioner sees a "Start Re-Draft" button on the league dashboard or round transition page
- [ ] Only the league commissioner can see and use the re-draft button (other members see a "Waiting for commissioner to start re-draft" message)
- [ ] Clicking "Start Re-Draft" creates a new draft for the next round with draft order based on standings (worst-to-best, snake format)
- [ ] If the commissioner does not start a re-draft, no points are awarded for that round (teams cannot earn points without drafting)
- [ ] After re-draft is started, all members are redirected/notified to join the new draft room
- [ ] The eliminated players/teams from the previous round are not available in the new draft pool
- [ ] Re-draft flow works correctly in both mock mode and live/production mode
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

---

## Functional Requirements

- FR-1: Resolve `player_id` to player full name (first + last) using the players dataset across all display screens (draft history, draft complete, roster)
- FR-2: Resolve `team_id` to team name using the teams dataset for goalie/team-level picks
- FR-3: Display team name alongside each pick in the draft history list
- FR-4: Add a "Back to League" navigation button on the Draft Complete screen that routes to `/league/{leagueId}`
- FR-5: Calculate goalie points as: WIN = 2 pts, SHUTOUT = 4 pts (replaces win, not additive); credit based on game outcome where goalie's team wins
- FR-6: Aggregate player points (goals + assists) and goalie points per team into the standings display
- FR-7: Ensure `total_points`, `player_points`, `goalie_points`, and `round_points` are correctly computed and reflected on the standings page
- FR-8: Implement Mantine color scheme with `'auto'` default, manual light/dark/auto toggle, and localStorage persistence
- FR-9: Include `ColorSchemeScript` in the HTML head to prevent theme flash on load
- FR-10: Clear roster data for the new round when advancing (preserve previous round data)
- FR-11: Show "Start Re-Draft" button to commissioners on the league dashboard when a round is complete and the next round has not been drafted
- FR-12: Non-commissioner members see a waiting state when re-draft has not been initiated
- FR-13: Re-draft creates a new draft with standings-based draft order (worst-to-best) and filters out eliminated players/teams
- FR-14: All features work in mock mode as well as Live/production mode, we cannot have it work one way and not the other. So our Supabase scoring backend must work.

## Non-Goals (Out of Scope)

- Push notifications for draft events or round transitions
- Custom theme colors or branding beyond light/dark mode
- Mobile-specific dark mode optimizations beyond what Mantine provides
- Historical draft replay or detailed pick-by-pick analytics
- Trade functionality between teams

## Design Considerations

- **Player Name Resolution:** Create a shared utility or hook (e.g., `usePlayerLookup`) that maps `player_id` → player name and `team_id` → team name. This should be reusable across DraftPage, RosterPage, and any future screens.
- **Dark Mode Toggle:** Use a sun/moon `ActionIcon` in the AppShell header, consistent with Mantine's recommended pattern. Consider a segmented control (Light | Dark | Auto) in a settings dropdown.
- **Draft Complete Screen:** The "Back to League" button should be prominent (primary variant) and placed below the results table.
- **Standings:** Consider color-coding point values or using Mantine's `Table` highlight features to make the standings more scannable.

## Technical Considerations

- **Mantine Color Scheme:** Use `MantineProvider` with `defaultColorScheme="auto"` and `useMantineColorScheme()` hook for the toggle. Add `<ColorSchemeScript defaultColorScheme="auto" />` before the app mounts.
- **Player Data Availability:** The players/teams datasets from `@sportsnot/mock-data` are already loaded in the draft and roster contexts. Ensure the lookup utility works with the existing data shape (`NHLPlayer` type with `id`, `firstName.default`, `lastName.default`).
- **Mock Mode Scoring:** The bugs in US-005 and US-006 are in `useMockScoringHistory.ts` and `useMockStandings.ts`. Debug the point accumulation logic — likely an issue with how goalie game logs are matched to roster slots, or how standings read the calculated points.
- **Round Advancement State:** In live/production mode, round advancement is automatic — triggered when a playoff round ends based on NHL schedule/results. In mock mode, it is manually triggered via simulation controls. The round transition logic in `RoundTransitionPage.tsx` and the `MockDataProvider` reducer need to properly clear roster state and expose the re-draft action. The live mode needs a mechanism (e.g., Supabase edge function or scheduled check) to detect when an NHL playoff round completes and advance the league round accordingly.
- **Hardcoded Colors:** Audit for any inline `color:` or `backgroundColor:` styles that would break in dark mode. Replace with Mantine theme tokens or CSS variables.

## Success Metrics

- All screens display player/team names instead of database IDs in both mock and live modes
- Goalie points correctly reflect wins (2 pts) and shutouts (4 pts) in both mock and live modes
- Standings page shows accurate, non-zero point totals after simulating a round in both mock and live modes
- Dark mode toggle works and respects OS preference on first load
- Round advancement cleanly resets rosters and surfaces the re-draft option in both mock and live modes
- Zero regressions in existing functionality (typecheck, lint, tests all pass)

## Open Questions

- Should the dark mode toggle be a two-state (light/dark) or three-state (light/dark/auto) control? -- Two state.
- Should the Draft Complete screen also show a summary of each team's full roster, or just the pick-by-pick list? -- Just the pick-by-pick list.
- When the commissioner starts a re-draft, should there be a countdown or immediate start? -- Immediate start.
- Should eliminated players be visually indicated (strikethrough, grayed out) in the draft history from previous rounds? -- Yes, as well as historical scoring views.
