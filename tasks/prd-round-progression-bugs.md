# PRD: Round Progression Bug Fixes

## Introduction

When advancing from Round 1 to Round 2 of the NHL playoffs in SportsNot, several bugs degrade the experience. The Re-draft button displays the wrong round number, the draft board shows the wrong round and allows picking eliminated players, the Next Round button is always clickable even when games are still in progress, and the "Back to League" button after a completed draft navigates to a nonexistent route causing a blank screen. These bugs affect both mock mode and production and undermine the core multi-round playoff draft experience.

## Goals

- Ensure round numbers display correctly across all round-transition and draft UI
- Prevent commissioners from advancing to the next round before the current round's games are complete
- Filter out players from teams eliminated in prior rounds during re-drafts
- Fix broken navigation from the draft completion screen back to the league dashboard

## User Stories

### US-001: Fix Re-Draft Button Round Label

**Description:** As a commissioner, I want the Re-Draft button on the Round Transition page to show the correct round number so I know which round I'm about to start.

**Details:**
- **File:** `packages/web/src/app/routes/draft/RoundTransitionPage.tsx`
- **Root cause:** `currentRound` is derived from `league?.current_round ?? 0`. When `current_round` is `null` or `0` (not yet set), `nextRound` computes as `1` instead of `2`.
- **Fix:** Ensure `league.current_round` is correctly set to `1` after the initial draft completes and before the transition page is shown. Alternatively, derive the round number from completed drafts (e.g., `completedDrafts.length + 1`) as a more reliable fallback.

**Acceptance Criteria:**
- [ ] When navigating to the Round Transition page after Round 1 is complete, the button reads "Start Round 2 Re-Draft"
- [ ] When navigating after Round 2 is complete, the button reads "Start Round 3 Re-Draft"
- [ ] The waiting-for-commissioner alert also shows the correct round number
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

---

### US-002: Disable Next Round Button Until Current Round Games Complete

**Description:** As a commissioner, I want the Next Round button on the League Dashboard to be disabled until all games in the current round have finished so I don't accidentally advance too early.

**Details:**
- **File:** `packages/web/src/app/routes/leagues/LeagueDashboardPage.tsx` (lines 157–164)
- **Root cause:** The "Next Round" button is rendered whenever `league.status === 'active'` and user is commissioner, with no check on game completion.
- **Mock mode:** Use the `roundComplete` flag from `MockDataProvider` state (already computed in the `ADVANCE_DAY` reducer by comparing simulation date to round date bounds).
- **Production mode:** Derive completion from game/series data — all series in the current round must have a winner (one team reaches 4 wins).

**Acceptance Criteria:**
- [ ] The "Next Round" button is visually disabled (grayed out, not clickable) when current round games are still in progress
- [ ] In mock mode, the button becomes enabled only after `roundComplete` is `true` in the mock state
- [ ] In production mode, the button becomes enabled only after all series in the current round have a winner
- [ ] A tooltip or helper text explains why the button is disabled (e.g., "All series in the current round must be complete")
- [ ] The button remains hidden entirely if the season is complete (Round 4 finished)
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

---

### US-003: Fix Draft Round Display and Player Eligibility in Round 2+ Drafts

**Description:** As a user participating in a Round 2 re-draft, I want the draft board to correctly display "Round 2" and only show players from teams that are still alive so I don't accidentally draft eliminated players.

**Details:**
- **File:** `packages/web/src/app/routes/draft/DraftPage.tsx`
- **Round display bug:** `currentRound = draft?.round ?? 1` (line 468). If the `draft.round` field is not correctly set to `2` when the Round 2 draft is created, it falls back to `1`. This also cascades to `isRound1 = currentRound === 1` (line 479), which controls sorting behavior and column visibility.
- **Player eligibility bug:** The `usePlayoffPlayers` and `useMockPlayoffPlayers` hooks receive `currentRound` to fetch player data. If `currentRound` is wrong (1 instead of 2), the hooks may return players from teams that were eliminated after Round 1.
- **Fix approach:**
  1. Verify that the re-draft creation flow (triggered from `RoundTransitionPage.handleStartReDraft`) correctly sets `draft.round` to the appropriate value (e.g., `2` for Round 2).
  2. Ensure the playoff player/team hooks filter out teams eliminated in all prior rounds (not just the current round's series).
  3. Validate that the `isRound1` flag correctly reflects the actual draft round for UI differences (sorting, column display).

**Acceptance Criteria:**
- [ ] During a Round 2 draft, the header displays "Round 2" (not "Round 1")
- [ ] During a Round 2 draft, `isRound1` is `false`, so regular-season stats columns are hidden and sorting uses playoff points
- [ ] Players from teams eliminated after Round 1 are not shown in the Round 2 draft player list
- [ ] Players from teams still alive in Round 2 are available for drafting
- [ ] The same logic scales correctly for Round 3 and Round 4 drafts
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

---

### US-004: Fix "Back to League" Navigation After Draft Completion

**Description:** As a user, I want the "Back to League" button on the draft completion screen to take me to the league dashboard instead of a blank screen.

**Details:**
- **File:** `packages/web/src/app/routes/draft/DraftPage.tsx` (line 648)
- **Root cause:** The button navigates to `` `/league/${leagueId}` `` (singular "league"), but the route is defined as `/leagues/:leagueId` (plural "leagues") in `app.tsx` (line 213). This causes react-router to match no route, rendering a blank screen.
- **Fix:** Change the navigation path from `/league/` to `/leagues/`.

**Acceptance Criteria:**
- [ ] Clicking "Back to League" on the draft completion screen navigates to `/leagues/:leagueId`
- [ ] The league dashboard loads correctly after navigation
- [ ] This works in both mock mode and production mode
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

---

## Functional Requirements

- FR-1: The Round Transition page must display the correct next round number derived from the league's `current_round` field or from completed draft count
- FR-2: The "Next Round" button on the League Dashboard must be disabled when the current round's games/series are not yet complete
- FR-3: In mock mode, round completion must be determined by the `roundComplete` flag in `MockDataProvider` state
- FR-4: In production mode, round completion must be determined by checking that all series in the current round have a winner (4 wins)
- FR-5: The draft board must display the correct round number from the `draft.round` field
- FR-6: The re-draft creation flow must set `draft.round` to the correct value (previous round + 1)
- FR-7: Playoff player/team data hooks must filter out all teams eliminated in prior rounds when fetching data for a given round
- FR-8: The "Back to League" button on the draft completion screen must navigate to `/leagues/:leagueId` (plural)
- FR-9: The "Next Round" button must be hidden entirely when the season is complete (all 4 rounds finished)

## Non-Goals

- No changes to the simulation control panel or mock day-advancement logic
- No changes to the actual draft pick mechanics (snake order, timer, etc.)
- No new playoff round types or bracket structures
- No changes to scoring or standings calculations
- No changes to the draft lobby or pre-draft flow

## Technical Considerations

- **Mock state exposure:** The `roundComplete` flag exists in `MockDataProvider` state but may not be exposed via a hook consumable by `LeagueDashboardPage`. A new mock hook (e.g., `useMockRoundComplete`) or context value may be needed.
- **Production round completion check:** May require a new Supabase query or hook that checks series completion status for the current round. Consider reusing the `getEliminatedTeams()` function from `@sportsnot/nhl-api`.
- **Draft creation flow:** The `handleStartReDraft` function in `RoundTransitionPage.tsx` and its mock equivalent (`useMockStartReDraft`) must correctly set the round field. Trace through both paths to find where the round is set.
- **Existing hooks:** `usePlayoffPlayers(season, round)` and `useMockPlayoffPlayers(season, round)` already accept a round parameter — verify they correctly filter eliminated teams for that round.

## Success Metrics

- Round number displayed on the Re-Draft button matches the actual next round in all scenarios
- Commissioners cannot advance rounds while games are still in progress
- No eliminated players appear in re-draft player lists
- "Back to League" navigation works 100% of the time from all locations

## Open Questions

- Is `league.current_round` reliably set to `1` after the initial draft completes, or does it remain `0`/`null`? This determines whether the re-draft button fix requires a data-layer change or just a UI fallback. -- Need to investigate.
- Are there other navigation paths that use `/league/` (singular) that also need fixing? -- Need to investigate.
- Should the "Next Round" button show a loading state while checking series completion status in production mode? -- Yes.
