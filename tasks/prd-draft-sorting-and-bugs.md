# PRD: Draft Page Sorting & Bug Fixes

## Introduction

The draft page has several usability issues and bugs that need to be addressed. Players in the draft board are not sorted in a useful way, IR slot assignment requires unnecessary manual selection when there's only one valid option, and a bug causes the draft to break mid-draft showing "Turn #41 - Unknown" instead of the correct team name. This PRD covers player sorting improvements, IR slot UX enhancement, and the draft turn resolution bug.

## Goals

- Sort available players by playoff points (descending) so the most productive players appear first
- In round 1 drafts, sort players by regular season total points since no playoff stats exist yet
- Improve the IR slot selection UX by pre-selecting and disabling unavailable options when a regular slot is full
- Fix the draft turn resolution bug that causes "Unknown" team display mid-draft after an IR pick

## User Stories

### US-001: Sort Draft Board Players by Playoff Points
**Description:** As a drafter, I want players sorted by total playoff points (highest first) so I can quickly identify the most productive available players.

**Acceptance Criteria:**
- [ ] Skaters table in the draft board is sorted by points (goals + assists) descending by default
- [ ] When two players have equal points, secondary sort is by goals descending
- [ ] Sort applies after position filtering (F, D, ALL)
- [ ] Goalies/Teams table remains sorted by wins descending (existing behavior)
- [ ] Typecheck passes
- [ ] Lint passes
- [ ] Unit tests pass
- [ ] Playwright tests pass

### US-002: Sort by Regular Season Points in Round 1
**Description:** As a drafter in round 1, I want players sorted by regular season total NHL points so I have useful data before any playoff games have been played.

**Acceptance Criteria:**
- [ ] Add NHL API function to fetch regular season stats for playoff players (game type 2)
- [ ] Add a `regular_season_points` column (or equivalent field) to the player stats cache or fetch inline
- [ ] In the draft board, when `draft.round === 1`, display a "Reg Season Pts" column in the skaters table
- [ ] In round 1, skaters table is sorted by regular season points descending by default
- [ ] In rounds 2+, the "Reg Season Pts" column is hidden and sorting reverts to playoff points
- [ ] Regular season stats are only fetched when the draft round is 1 (no unnecessary API calls)
- [ ] Mock data includes regular season points fixtures for round 1 testing
- [ ] Typecheck passes
- [ ] Lint passes
- [ ] Unit tests pass
- [ ] Playwright tests pass

### US-003: Smart IR Slot Pre-Selection
**Description:** As a drafter, I want the slot selection modal to pre-select the IR slot and disable the regular slot when all regular slots of that position are filled, so I don't have to manually choose the only valid option.

**Acceptance Criteria:**
- [ ] When drafting a forward and all 5 regular F slots are filled, the confirmation modal pre-selects "IR Forward" and the "Forward" option is disabled (greyed out, not clickable)
- [ ] When drafting a defenseman and all 3 regular D slots are filled, the confirmation modal pre-selects "IR Defense" and the "Defense" option is disabled
- [ ] When both regular and IR slots are available, behavior remains unchanged (no pre-selection)
- [ ] When the IR slot is already filled but regular slots remain, the IR option is disabled and regular is pre-selected
- [ ] The disabled option shows a visual indicator (e.g., greyed out text or tooltip explaining "All regular forward slots filled")
- [ ] Typecheck passes
- [ ] Lint passes
- [ ] Unit tests pass
- [ ] Playwright tests pass

### US-004: Fix Draft Turn Resolution Bug ("Unknown" Team)
**Description:** As a drafter, I want the draft to correctly show whose turn it is after every pick, so the draft doesn't appear broken mid-draft.

**Acceptance Criteria:**
- [ ] Investigate the root cause of "Turn #41 - Unknown" occurring in mock mode after an IR-F pick when picks remain
- [ ] The `currentPick` to `draftOrder` index mapping correctly handles all pick numbers within the valid range (1 to draftOrder.length)
- [ ] The member lookup from `draftOrder[index]` always resolves to a valid team name for in-range picks
- [ ] When `currentPick > draftOrder.length`, the draft is marked as completed and the UI shows a "Draft Complete" state instead of "Turn #N - Unknown"
- [ ] Add bounds checking: if `currentPick` exceeds `draftOrder.length`, do not attempt to look up a team name
- [ ] Verify the IR-F and IR-D pick submission flows advance `currentPick` correctly (same as regular picks)
- [ ] Playwright test is written which starts the app in mock mode (unlike the existing tests) and does a mock draft all the way to completion with 4 players in a league
- [ ] Mock draft simulation completes a full 11-round (inlcuding the IR picks), 4-member draft (44 picks) without showing "Unknown" at any point
- [ ] Typecheck passes
- [ ] Lint passes
- [ ] Unit tests pass
- [ ] Playwright tests pass

## Functional Requirements

- FR-1: The skaters table in the draft board must be sorted by total points (goals + assists) descending, with goals as the tiebreaker
- FR-2: When `draft.round === 1`, the skaters table must be sorted by regular season points descending instead of playoff points
- FR-3: A "Reg Season Pts" column must be visible in the skaters table only during round 1 drafts
- FR-4: Regular season stats must be fetched from the NHL API using game type 2 (regular season) for the current season
- FR-5: Regular season stats must only be fetched when `draft.round === 1` to avoid unnecessary API calls
- FR-6: The slot selection modal must count the user's current roster slots by position to determine availability
- FR-7: When only the IR variant of a position is available, the modal must pre-select it and disable the regular option
- FR-8: When only the regular variant of a position is available, the modal must pre-select it and disable the IR option
- FR-9: The draft turn display must include bounds checking against the `draftOrder` array length
- FR-10: When `currentPick` exceeds `draftOrder.length`, the UI must display a "Draft Complete" state

## Non-Goals

- No user-configurable sort options or sort-by-column clicking (future enhancement)
- No regular season points display beyond round 1
- No changes to the snake draft order generation logic
- No changes to the draft pick timer or auto-pick functionality
- No changes to the goalie/team drafting flow (goalies have a single G slot with no IR variant)

## Design Considerations

- The "Reg Season Pts" column should match the existing table column styling in the skaters table
- Disabled slot options in the modal should use Mantine's built-in disabled styling for `Radio` or `Select` components
- The "Draft Complete" state should reuse any existing completion UI already in `DraftPage.tsx`

## Technical Considerations

- **NHL API regular season stats:** Use `gameType: 2` parameter in the existing NHL API client. May need a new function like `getRegularSeasonPlayerStats()` or extend the existing `getPlayerGameLog` to accept game type
- **Player stats cache:** Consider whether regular season points should be stored in `player_stats_cache` alongside playoff stats, or fetched on-demand via a separate hook
- **Mock data:** `packages/mock-data` will need regular season points fixtures for round 1 testing — can be static values
- **Roster slot counting:** The draft page already has access to the user's roster entries via the draft picks. Count filled slots by position to determine which slots are available
- **Off-by-one investigation:** The bug may involve `currentPick` (1-based) vs `draftOrder` array indexing (0-based). Check `draftOrder[currentPick - 1]` lookups and ensure the mock draft state update correctly handles the pick after an IR selection
- **State consistency:** The mock draft `MAKE_PICK` action must atomically update `currentPick` and the draft picks array to prevent UI inconsistencies

## Success Metrics

- Players in the draft board are visibly sorted by points/goals as expected
- Round 1 draft shows regular season points column and sorts by it
- IR slot selection requires zero unnecessary clicks when only one option is valid
- A full mock draft (44 picks, 4 members, 11 rounds) completes without any "Unknown" team display

## Open Questions

- Should the player sort order persist if the user navigates away from the draft page and returns? -- No.
- Should we add a visual indicator (arrow icon, column header highlight) showing which column the table is currently sorted by? -- Yes.
- For the draft bug: is the issue specific to mock mode or could it also affect live Supabase mode? -- Investigate.
