# PRD: Update Manager Name

## Introduction

Allow users to update their manager name (display name) from their profile page. A basic ProfilePage with display name editing already exists, but it lacks input validation (max character limit), mock mode support, proper UI refresh after saving, and test coverage. This PRD covers hardening the existing feature to be production-ready.

## Goals

- Enforce a max character limit (30 characters) on the manager name input
- Ensure the updated name propagates immediately across the app (nav bar, standings, draft) without requiring a page refresh
- Support manager name editing in mock mode for offline development
- Add unit test coverage for the profile update flow

## User Stories

### US-001: Add Max Character Limit to Manager Name Input

**Description:** As a user, I want the manager name field to enforce a 30-character limit so that names stay readable across the app.

**Acceptance Criteria:**

- [ ] Manager name text input enforces a 30-character maximum
- [ ] UI shows character count indicator (e.g., "12/30")
- [ ] Submitting a name longer than 30 characters is prevented client-side
- [ ] Empty/whitespace-only names are still rejected (existing behavior preserved)
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

### US-002: Refresh Display Name Across App After Update

**Description:** As a user, I want my updated manager name to appear immediately in the nav bar and on other pages so that I don't have to refresh my browser.

**Acceptance Criteria:**

- [ ] After a successful profile update, the AuthContext (or user state) refreshes with the new display name
- [ ] The nav bar / header user menu reflects the updated name without a page reload
- [ ] Standings and draft pages show the updated name on next navigation (via fresh query)
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

### US-003: Mock Mode Support for Manager Name Update

**Description:** As a developer, I want profile name editing to work in mock mode so that I can develop and test offline.

**Acceptance Criteria:**

- [ ] A mock profile update handler exists in the mock hooks directory
- [ ] The mock handler updates the in-memory user state with the new display name
- [ ] The mock hooks registry includes the profile update mock
- [ ] Updating the name in mock mode reflects immediately in the nav bar and across the app
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

### US-004: Unit Tests for Profile Update Flow

**Description:** As a developer, I want tests covering the manager name update logic so that regressions are caught.

**Acceptance Criteria:**

- [ ] Test that empty/whitespace-only names are rejected
- [ ] Test that names exceeding 30 characters are rejected
- [ ] Test that a valid name trims whitespace before saving
- [ ] Test that successful update triggers a UI state refresh
- [ ] All Typecheck passes (even if it's outside of your changes)
- [ ] Lint passes (even if it's outside of your changes)
- [ ] Unit tests have been added
- [ ] All Unit tests pass (even if it's outside of your changes)
- [ ] All Playwright tests pass (even if it's outside of your changes)

## Functional Requirements

- FR-1: The manager name input field must enforce a maximum of 30 characters
- FR-2: The manager name input must display a live character count (e.g., "12/30")
- FR-3: The system must reject empty or whitespace-only manager names with an error message
- FR-4: After a successful save, the system must refresh the authenticated user state so the new name appears in the nav bar immediately
- FR-5: The profile update must work in mock mode using the mock hooks registry pattern
- FR-6: The profile page must show a success notification after saving and an error notification on failure (existing behavior — preserve it)

## Non-Goals

- No per-league manager names (name is global across all leagues)
- No avatar/profile picture editing (out of scope)
- No uniqueness constraint on manager names
- No admin/commissioner ability to edit other users' names
- No changes to the database schema or RLS policies (existing `users` table and policies are sufficient)

## Design Considerations

- Reuse existing Mantine `TextInput` component with `maxLength` prop
- Add a small helper text or badge below/beside the input showing character count
- Preserve the existing success/error `Alert` components on the ProfilePage
- The profile page is already at the `/profile` route behind `<ProtectedRoute>`

## Technical Considerations

- **Auth state refresh:** After updating `users.display_name` in Supabase, call `supabase.auth.refreshSession()` or update the AuthContext state directly so the nav bar reflects the change
- **React Query invalidation:** If other pages cache user data via React Query, invalidate relevant query keys after profile update
- **Mock mode:** Follow the existing `mockHooksRegistry` pattern — add a mock handler that updates the in-memory user object held by `useMockAuth`
- **No migration needed:** The `users.display_name` column and UPDATE RLS policy already exist

## Success Metrics

- Manager name updates reflect in the nav bar within 1 second of saving (no page reload)
- Character limit prevents names longer than 30 characters
- Profile update works identically in mock mode and live mode
- Unit tests cover validation and state refresh logic

## Open Questions

- None at this time — scope is well-defined.
