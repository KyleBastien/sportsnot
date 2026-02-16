# PRD: Round Progression & Scoring Fixes

## Introduction

This PRD addresses six interrelated bugs and improvements in the SportsNot NHL playoff fantasy hockey app. The issues span scoring display inconsistencies, roster page UX, draft order correctness, cumulative standings scoring, simulation control panel synchronization, and the missing Round 3/4 combined draft mechanic. These fixes improve the core gameplay loop and ensure mock mode accurately simulates the intended multi-round playoff experience.

## Goals

- Fix points displaying as 0 on the League Dashboard page while Standings shows correct values
- Hide the Actions column on the Roster page when no actions are available
- Ensure re-draft order is correctly based on reverse standings (worst team picks first)
- Display cumulative scores across all completed rounds in Standings
- Decouple the League page "Next Round" button from the Simulation Control Panel "Advance Round" button so each has a single, clear responsibility
- Implement combined Round 3/4 drafting where Round 3 picks carry into Round 4, with eliminated players visually struck through

## User Stories

### US-001: Fix League Dashboard Points Display

**Description:** As a league member, I want to see my correct total points on the League Dashboard page so that I can quickly check my standing without navigating to the Standings page.

**Acceptance Criteria:**
- [ ] The League Dashboard page (`/leagues/:leagueId`) shows each member's correct `total_points` reflecting all accumulated stats
- [ ] Points update as the simulation date advances (mock mode) or as live stats come in (live mode)
- [ ] Points on the League Dashboard match the total points shown on the Standings page for the same league
- [ ] If a member has 0 actual points (e.g., Round 1 hasn't started), 0 is correctly shown
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

### US-002: Conditionally Hide Actions Column on Roster Page

**Description:** As a user viewing my roster, I want the Actions column hidden when there are no actions to perform so the table is cleaner and less confusing.

**Acceptance Criteria:**
- [ ] The Actions column is not rendered in the roster table when no row in the table has an available action
- [ ] The Actions column appears when at least one row has an available action (e.g., "Activate IR" is possible)
- [ ] This applies to all roster tables on the page (active roster, IR slots, etc.)
- [ ] Column visibility is recalculated when roster state changes (e.g., after activating IR)
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

### US-003: Fix Re-Draft Order Based on Reverse Standings

**Description:** As a league member, I want the re-draft order for Rounds 2+ to be based on reverse standings (worst team picks first) so that the league stays competitive.

**Acceptance Criteria:**
- [ ] In Round 2+ re-drafts, the team with the fewest total points picks first
- [ ] Snake draft pattern is applied using the reverse-standings order (e.g., worst→best, best→worst, worst→best...)
- [ ] Ties in total points are broken consistently (e.g., by original draft position)
- [ ] The draft lobby displays the correct pick order before drafting begins
- [ ] This works correctly in both mock mode and live mode
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

### US-004: Fix Cumulative Scoring in Standings

**Description:** As a league member viewing standings, I want total points to reflect the cumulative score across all completed rounds so I can see the true leaderboard.

**Acceptance Criteria:**
- [ ] The `total_points` field on the Standings page reflects the sum of points from all completed rounds (e.g., Round 1 + Round 2)
- [ ] The round-by-round breakdown still shows individual round scores correctly
- [ ] At the end of Round 2, total points = Round 1 points + Round 2 points
- [ ] At the end of Round 3, total points = Round 1 + Round 2 + Round 3 points
- [ ] At the end of Round 4, total points = Round 1 + Round 2 + Round 3 + Round 4 points
- [ ] The league member's `total_points` in the database/mock state is updated cumulatively
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

### US-005: Decouple League "Next Round" from Simulation "Advance Round"

**Description:** As a league admin and mock mode user, I want the League page "Next Round" button to only open the draft for the next round, and the Simulation Control Panel "Advance Round" button to only advance the simulation date/round, so the two controls don't conflict or get out of sync.

**Acceptance Criteria:**
- [ ] The League page "Next Round" button sets the league status to `'drafting'` and navigates to the draft transition/lobby page — it does NOT change `currentRound` or `simulationDate` in the mock state
- [ ] The Simulation Control Panel "Advance Round" button increments `currentRound` and advances `simulationDate` to the start of the next round — it does NOT trigger any draft flow
- [ ] The intended flow is enforced: (a) Round N ends → (b) League admin clicks "Next Round" to start draft → (c) Draft completes → (d) Mock panel "Advance Round" advances simulation into Round N+1 → (e) "Next Day" steps through Round N+1 days
- [ ] The League page "Next Round" button is only enabled when the current round's games are complete (round is over)
- [ ] The Simulation "Advance Round" button is enabled whenever the current round's games are complete, regardless of whether any league has drafted for the next round
- [ ] Leagues that have not completed their draft before the simulation advances do not earn points in the new round
- [ ] Both buttons display clear labels indicating their distinct purpose (e.g., "Start Next Draft" vs "Advance to Round N")
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

### US-006: Implement Combined Round 3/4 Draft

**Description:** As a league member, I want my Round 3 draft picks to carry over into Round 4 so that the Conference Finals and Stanley Cup Final are treated as a combined drafting period, with eliminated players shown as struck through once Round 4 begins.

**Acceptance Criteria:**
- [ ] When drafting for Round 3, the draft is labeled to indicate it covers both Conference Finals and Stanley Cup Final
- [ ] The same 11 picks (5F + 3D + 1G + 1IR_F + 1IR_D) are used for both Round 3 and Round 4
- [ ] There is NO separate Round 4 draft — Round 3 picks automatically carry into Round 4
- [ ] When Round 4 begins, roster slots whose player's team was eliminated in Round 3 are visually struck through on the Roster page
- [ ] Eliminated players earn 0 points in Round 4 but their Round 3 points still count toward the owner's total
- [ ] The Standings page correctly reflects Round 4 scoring: only surviving players accumulate points
- [ ] The draft transition flow skips the draft for Round 4 (since picks carry over from Round 3)
- [ ] Available players in the Round 3 draft exclude teams eliminated in Rounds 1 and 2 (existing behavior, just confirm it still works)
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

## Functional Requirements

- FR-1: The League Dashboard page must compute and display each member's total points consistently with the Standings page. If the source of truth is computed from roster/stats, the same computation must be used on both pages.
- FR-2: The Roster page must check all rows for available actions before rendering the Actions column. If no row has an action, the column must not be rendered.
- FR-3: Re-draft order for Rounds 2+ must sort league members by `total_points` ascending (lowest first) and apply snake draft pattern from that order.
- FR-4: The `total_points` field must be a cumulative sum across all completed rounds, not just the current round's points.
- FR-5: The League page "Next Round" button must only change the league's status to `'drafting'` and navigate to the draft transition page. It must not modify `currentRound` or `simulationDate`.
- FR-6: The Simulation Control Panel "Advance Round" button must only increment `currentRound` and advance `simulationDate`. It must not trigger any draft flow.
- FR-7: The Simulation "Advance Round" button must be enabled whenever the current round's games are complete, regardless of whether any league has completed its draft for the upcoming round. Leagues that have not drafted before the simulation advances to the next round simply do not earn points in that round.
- FR-8: Round 3 draft picks must be stored as covering both Round 3 and Round 4. No separate Round 4 draft is created.
- FR-9: When Round 4 starts, the system must identify which Round 3 picks have eliminated teams and mark those roster slots as eliminated.
- FR-10: Eliminated roster slots in Round 4 must render with a strikethrough on the player name in the Roster page.
- FR-11: Eliminated roster slots must not accumulate points in Round 4, but their Round 3 points remain in the owner's total.
- FR-12: The draft transition flow must detect that Round 4 does not require a draft and skip directly to active play.

## Non-Goals (Out of Scope)

- Redesigning the overall Standings page layout or adding new visualizations
- Adding trade functionality between league members
- Push notifications or alerts for round transitions
- Changes to the Round 1 initial draft flow (random order is correct for Round 1)
- Changing the number of roster slots (stays at 11: 5F+3D+1G+1IR_F+1IR_D)
- Supabase database migration changes
- Handling edge cases where a user leaves or is removed mid-draft

## Design Considerations

- **Roster Actions column:** Use Mantine's column visibility feature or conditional column definition to toggle the Actions column based on data. No new components needed.
- **Strikethrough for eliminated players:** Apply CSS `text-decoration: line-through` and reduce opacity on the player name cell for eliminated Round 4 roster slots. Use existing Mantine `sx` or `style` props.
- **Button labels:** Rename the League page button from "Next Round" to "Start Next Draft" and the Simulation panel button label should clearly say "Advance to Round N" (where N is the next round number).
- **Round 3 draft label:** Add a subtitle or badge on the draft page indicating "Conference Finals & Stanley Cup Final" when round is 3.

## Technical Considerations

- **Points computation:** The root cause of US-001 and US-004 is likely that `total_points` on the `league_members` object in mock state is not being recalculated as stats accumulate. The mock hooks (`useMockStandings`, `useMockRoster`) compute points on-the-fly, but the `league_members.total_points` field in `MockState` may not be kept in sync. The fix should ensure a single source of truth for point computation.
- **Re-draft order (US-003):** The `RoundTransitionPage` sorts members by `total_points` ascending, but if `total_points` is stale or 0 (per US-001), the order will be wrong. Fixing US-001/US-004 first may resolve US-003 as a side effect.
- **Simulation decoupling (US-005):** The `ADVANCE_ROUND` action in `MockDataProvider` currently increments `currentRound` directly. The League page's "Next Round" button should dispatch a different action (e.g., `START_NEXT_DRAFT`) that only changes league status without touching simulation state.
- **Round 3/4 combined draft (US-006):** The `rosterHistory` structure (`Record<string, Record<number, RosterSlot[]>>`) already supports per-round roster snapshots. For Round 4, instead of creating new roster slots from a draft, copy Round 3 slots and mark eliminated ones. Add an `isEliminated` flag to `RosterSlot` or derive it from `TeamStats.isEliminated`.
- **Dependency order:** US-001 and US-004 (scoring fixes) should be implemented before US-003 (draft order), since correct point totals are needed for correct re-draft ordering.

## Success Metrics

- League Dashboard page shows non-zero points matching Standings page after at least one game day has been simulated
- Roster page renders without an Actions column when no IR activation is available
- In Round 2+ re-drafts, the team with the lowest cumulative points is assigned pick #1
- Standings `total_points` at end of Round 2 equals sum of Round 1 + Round 2 points
- A full mock mode playthrough from Round 1 through Round 4 completes without the Next Round buttons conflicting
- Round 4 roster shows struck-through players whose teams were eliminated in Round 3, with 0 new points accumulating for those players

## Open Questions

- Should the "Start Next Draft" button on the League page be visible to all members or only the league commissioner? -- Just the commissioner.
- When copying Round 3 roster to Round 4, should IR activations from Round 3 carry over, or does the IR state reset? -- IR carries over. It's like round 3 and 4 are the same round.
- If all of a user's players are eliminated after Round 3, should we show any special messaging on their roster page for Round 4? -- No.
