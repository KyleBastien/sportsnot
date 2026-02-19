# PRD: Draft UX & Scoring Bugs

## Introduction

This PRD addresses six bugs and improvements related to the draft experience, round-specific scoring, and round progression in SportsNot. These issues affect both the live draft UX (no scroll in history, no "my team" view) and the scoring/round-transition pipeline (points leaking across rounds, missing R4 roster carry-over, misleading "Start Next Draft" button after Round 3).

## Goals

- Ensure draft pick history is fully scrollable during a live draft
- Fix round-specific scoring so each round's points reflect only that round's games
- Allow users to see their roster being built during the draft
- Prevent misleading "Start Next Draft" button from appearing after Round 3's draft
- Ensure Round 4 roster carry-over works correctly in both mock and production modes

## User Stories

### US-001: Scrollable Draft History During Live Draft

**Description:** As a drafter, I want to scroll through the full draft history while the draft is in progress so that I can see all picks back to #1.

**Current Behavior:** The live draft view in `DraftPage.tsx` (lines 782–815) only shows the last 10 picks in a non-scrollable `<Stack>`. After the draft is complete, a separate scrollable `<ScrollArea h={400}>` table shows all picks.

**Root Cause:** `.slice(0, 10)` limits picks and there is no `<ScrollArea>` wrapper during the live draft.

**Acceptance Criteria:**
- [ ] During a live draft, the Draft History section displays ALL picks (remove `.slice(0, 10)`)
- [ ] The Draft History section is wrapped in a `<ScrollArea>` with a max height (e.g. `h={400}`) so it scrolls when content overflows
- [ ] The most recent pick is visible by default (scroll starts at the top since picks are sorted descending by pick number)
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

**Key Files:**
- `packages/web/src/app/routes/draft/DraftPage.tsx` — lines 782–815 (live draft history)

---

### US-002: Fix Round-Specific Points in Mock Roster Hook

**Description:** As a league member, I want my roster page to show the points earned during the current round (per slot) AND a cumulative total across all completed rounds so I can see both my current round performance and my overall standing.

**Current Behavior:** `useMockRoster.ts` calculates `points_earned` using `calculatePlayerPoints(playerId, state.simulationDate)` and `calculateGoaliePoints(teamId, state.simulationDate)`, which accumulate stats from the **beginning of all games** through `simulationDate`. This means an R2 roster shows cumulative R1+R2 points instead of just R2 points. There is also no way to see a cumulative total across all rounds on the roster page.

**Root Cause:** The `calculatePlayerPoints` and `calculateGoaliePoints` helpers in `useMockRoster.ts` (lines 79–116) only filter by `throughDate` (upper bound) but have no `fromDate` (lower bound) to isolate the current round's games. In contrast, `calculateRoundMemberPoints` in `utils.ts` correctly uses `getRoundDateBounds(round)` to provide both bounds.

**Acceptance Criteria:**
- [ ] `useMockRoster` and `useMockLeagueRosters` compute `points_earned` using the current round's date bounds from `getRoundDateBounds(slot.round)` — only counting stats between `firstDate` and min(`simulationDate`, `lastDate`) for that round
- [ ] Refactor to reuse `calculateRoundMemberPoints` from `utils.ts` (or pass `fromDate` to the existing helpers) instead of duplicating calculation logic
- [ ] R1 roster slots show only R1 game points; R2 slots show only R2 game points, etc.
- [ ] The mock roster hook (or a companion hook) also returns cumulative points across all rounds for the member, using `calculateMemberPoints` from `utils.ts`
- [ ] Standings page (`calculateMemberPoints` in `utils.ts`) continues to show correct cumulative totals (it already uses round date bounds — verify no regression)
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

**Key Files:**
- `packages/web/src/mock/hooks/useMockRoster.ts` — `calculatePlayerPoints`, `calculateGoaliePoints`, `useMockRoster`, `useMockLeagueRosters`
- `packages/web/src/mock/utils.ts` — `calculateRoundMemberPoints`, `calculateMemberPoints`, `getRoundDateBounds` (reference implementation)
- `packages/web/src/mock/MockDataProvider.tsx` — `getRoundDateBounds` export

---

### US-003: Fix Round-Specific Points in Production (Supabase) Mode

**Description:** As a league member in production mode, I want my roster page to show the points earned during the current round AND a cumulative total across all rounds.

**Current Behavior:** In production mode, `points_earned` on `roster_slots` is stored in the database. The mechanism that updates these points needs to be verified to ensure it counts games within the correct round's date bounds. There is also no cumulative total shown.

**Acceptance Criteria:**
- [ ] Audit the Supabase edge function or client-side logic that populates `points_earned` on `roster_slots` to verify it uses round-specific date filtering
- [ ] If `points_earned` is calculated client-side (e.g. in `useMyRoster` query), apply the same round-date-bounds filtering as the mock fix
- [ ] If `points_earned` is calculated by an edge function, verify it filters game stats by the round's date range
- [ ] R2 roster slots only reflect R2 game stats (not cumulative R1+R2)
- [ ] The production roster hook (or a companion hook) also returns cumulative points across all rounds for the member (e.g., by querying/summing `points_earned` from roster_slots across all rounds, or using `total_points` on `league_members`)
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

**Key Files:**
- `packages/web/src/app/routes/roster/RosterPage.tsx` — `useMyRoster` (production query)
- `packages/supabase-db/functions/` — edge functions that may update `points_earned`
- `packages/supabase/src/lib/hooks/` — any hooks that calculate or fetch points

---

### US-002/003 UI: Roster Page Points Display

**Description:** The Roster page must clearly show both the current round's points and a cumulative total across all rounds.

**Current Behavior:** The Roster page shows a single "Total Points" card (line 247–256 of `RosterPage.tsx`) that sums `points_earned` from the current round's active slots. There is no breakdown by round or cumulative total.

**Acceptance Criteria:**
- [ ] The Roster page header displays **two** point values:
  - **Round N Points** — sum of `points_earned` from the current round's active slots (this is the per-round total)
  - **Total Points** — cumulative sum across all rounds (R1 + R2 + ... + current round), sourced from `calculateMemberPoints` (mock) or `total_points` / summed roster query (production)
- [ ] Per-slot `points_earned` in the roster table continues to show the current round's points only (not cumulative)
- [ ] When in Round 1, both values are identical (there is only one round)
- [ ] When in Round 2+, "Total Points" includes prior rounds' contributions and "Round N Points" shows only the current round
- [ ] Layout: Both values displayed side-by-side in the header area (e.g., two cards or a single card with two columns)

**Key Files:**
- `packages/web/src/app/routes/roster/RosterPage.tsx` — header section (lines 239–257)

---

### US-004: My Team View During Draft

**Description:** As a drafter, I want to see my in-progress roster during the draft so that I can track which positions are filled and who I've already picked.

**Current Behavior:** There is no dedicated "My Team" view during the draft. The only indication of your picks is slot counters in the pick confirmation modal and the draft history (which shows all teams' picks, not just yours).

**Acceptance Criteria:**
- [ ] A collapsible section is added to the `DraftPage` (above or below the draft board area) showing "My Team" or "My Roster"
- [ ] The section groups the current user's picks by position (F, D, G, IR_F, IR_D) matching the roster page layout
- [ ] Each slot shows the player/team name and position
- [ ] Empty slots are shown as placeholders (e.g. "Empty Forward slot") to indicate remaining picks
- [ ] The section is collapsed by default to save vertical space, expandable on click
- [ ] Updates in real-time as picks are made
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

**Key Files:**
- `packages/web/src/app/routes/draft/DraftPage.tsx` — main draft UI
- `packages/types/src/lib/types.ts` — `ROSTER_CONFIG` defines slot counts per position

---

### US-005: Hide "Start Next Draft" After Round 3

**Description:** As a commissioner, I should not see a "Start Next Draft" button at the end of Round 3 because Round 4 has no re-draft — rosters carry over automatically.

**Current Behavior:** `LeagueDashboardPage.tsx` shows the "Start Next Draft" button when `league.status === 'active' && isCommissioner && !seasonComplete`. At end of Round 3, `seasonComplete` is `false` (season ends after R4), so the button appears and is enabled. Clicking it navigates to the `RoundTransitionPage`, which does correctly handle the R3→R4 case. However, the button label is misleading and the user expects it not to appear.

**Root Cause:** The visibility condition `!seasonComplete` doesn't account for the fact that Round 4 has no draft.

**Acceptance Criteria:**
- [ ] The "Start Next Draft" button is NOT rendered when `currentRound >= 3` (since R3→R4 has no draft)
- [ ] The SimulationControlPanel's "Advance Round" button (mock mode) remains the mechanism for advancing from R3 to R4
- [ ] In production mode, an alternative mechanism exists or the transition page is accessible via another path (e.g., the round transition page could auto-trigger when R3 completes, or a different button labeled appropriately could be shown)
- [ ] Ensure the R3→R4 flow is still accessible to commissioners in production mode — if hiding the button creates a dead end, add an "Advance to Finals" button or auto-navigate to the transition page
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

**Key Files:**
- `packages/web/src/app/routes/leagues/LeagueDashboardPage.tsx` — lines 181–195 (button visibility)
- `packages/web/src/mock/components/SimulationControlPanel.tsx` — "Advance to Round X" button
- `packages/web/src/app/routes/draft/RoundTransitionPage.tsx` — handles R3→R4 transition correctly

---

### US-006: Fix Round 4 Roster Carry-Over

**Description:** As a league member in Round 4, I want to see my Round 3 roster carried over so that the "My Roster" page shows my actual team instead of "Your roster has not been set yet."

**Current Behavior:** The `RosterPage` shows "Your roster for Round 4 has not been set yet" when `slots.length === 0`. The roster carry-over from R3→R4 is supposed to happen in `ADVANCE_ROUND` (mock mode) or `handleSkipToRound4` (transition page). However, there are two issues:

1. **Mock mode gap:** The `SKIP_TO_ROUND4` action (dispatched from the RoundTransitionPage) only updates league status/round but does NOT copy rosters — it assumes `ADVANCE_ROUND` was already called. If the user navigates Dashboard → Transition Page → "Continue to Finals" without first clicking "Advance Round" in the SimulationControlPanel, rosters are never copied.
2. **Production mode:** The `handleSkipToRound4` in `RoundTransitionPage.tsx` does copy rosters (lines 169–189). But if the table name is `rosters` vs `roster_slots`, verify the query is correct.

**Acceptance Criteria:**
- [ ] **Mock mode:** `SKIP_TO_ROUND4` reducer action copies Round 3 rosters to Round 4 (with `round: 4`, `pointsEarned: 0`) if rosters for Round 4 don't already exist (idempotent — don't duplicate if `ADVANCE_ROUND` already ran)
- [ ] **Production mode:** Verify `handleSkipToRound4` correctly copies roster slots; ensure the Supabase table name (`rosters` vs `roster_slots`) is correct
- [ ] After R3→R4 transition, navigating to "My Roster" shows the carried-over roster with 0 points for R4
- [ ] The "No Roster Yet" message does NOT appear in Round 4 when roster was carried over
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

**Key Files:**
- `packages/web/src/mock/MockDataProvider.tsx` — `SKIP_TO_ROUND4` case (line 384), `ADVANCE_ROUND` case (line 322)
- `packages/web/src/app/routes/draft/RoundTransitionPage.tsx` — `handleSkipToRound4` (line 156)
- `packages/web/src/app/routes/roster/RosterPage.tsx` — empty state check (line 184)

---

## Functional Requirements

- FR-1: The live draft history must display all picks in a scrollable container with a max height
- FR-2: `useMockRoster` and `useMockLeagueRosters` must compute `points_earned` using round date bounds (`fromDate` to `throughDate`), not cumulative from beginning of time
- FR-3: Production roster point calculation must use round-specific date filtering
- FR-3a: The Roster page must display both **Round N Points** (current round only) and **Total Points** (cumulative across all rounds R1+R2+...+Rn) in the header
- FR-4: The draft page must include a collapsible "My Team" section showing the current user's picks grouped by position
- FR-5: The "Start Next Draft" button must not be rendered when `currentRound >= 3`
- FR-6: An alternative R3→R4 advancement mechanism must exist for commissioners in production mode (e.g., "Advance to Finals" button or auto-navigation)
- FR-7: The `SKIP_TO_ROUND4` mock reducer must copy R3 rosters to R4 if they don't already exist
- FR-8: The production `handleSkipToRound4` must be verified to correctly copy roster slots

## Non-Goals

- No changes to scoring values (goals, assists, wins, shutouts point values remain the same)
- No changes to the post-draft-complete view (which already has scrollable history)
- No changes to the snake draft ordering algorithm
- No new database migrations (unless the production roster copy query needs fixing)
- No changes to the SimulationControlPanel's "Advance Round" flow (it works correctly already)

## Design Considerations

- **Draft History scroll:** Reuse `<ScrollArea>` from Mantine (already used in the post-draft view). Keep the same max height of 400px.
- **My Team section:** Use Mantine `<Collapse>` or `<Accordion>` for the collapsible behavior. Reuse the position grouping logic from `RosterPage.tsx` (`POSITION_ORDER`, `POSITION_LABELS`).
- **Button changes:** Simple conditional rendering change on `LeagueDashboardPage`.

## Technical Considerations

- **Scoring fix is the highest-priority item** — it affects data correctness. The `useMockRoster.ts` helpers should be refactored to accept a `fromDate` parameter or delegate to `calculateRoundMemberPoints` from `utils.ts`.
- **Idempotency for roster copy:** When `SKIP_TO_ROUND4` copies rosters, check if R4 rosters already exist (from a prior `ADVANCE_ROUND` call) before inserting duplicates.
- **Production mode R3→R4 path:** If the "Start Next Draft" button is hidden, ensure the `RoundTransitionPage` is still reachable. Options: add an "Advance to Finals" button on the dashboard, or auto-redirect when R3 is complete.
- **`getRoundDateBounds` is exported from `MockDataProvider.tsx`** — may need to move to `utils.ts` if used more broadly.

## Success Metrics

- Draft history is fully scrollable during live draft — all picks visible
- R2 roster points only reflect R2 games (no R1 contamination)
- R4 roster page shows carried-over roster, never shows "No Roster Yet" after transition
- "Start Next Draft" button never appears after Round 3

## Open Questions

- Should the "My Team" collapsible section be expanded by default on smaller rosters (e.g., early in draft) and collapsed later?
- Should the production R3→R4 path use auto-navigation (detect R3 complete → redirect to transition page) or a manual "Advance to Finals" button?
- Are there any other places in the app that display per-slot `points_earned` that also need the round-date-bounds fix (e.g., league rosters view, scoring history)?
