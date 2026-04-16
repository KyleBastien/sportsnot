# PRD: OTP Email Login

## Problem Statement

SportsNot currently supports only magic link email authentication. Users must leave the app, open their email, and click a link to sign in. This creates friction — especially on mobile, where switching between apps interrupts the flow. Adding OTP (one-time passcode) email login gives users a faster, in-app alternative: enter a 6-digit code without leaving the browser.

## Proposed Solution

Add OTP code verification as a login option alongside the existing magic link flow. The login page will include a **"Use OTP Code?" checkbox** (checked by default) next to the submit button. When checked, submitting the email sends a 6-digit OTP code instead of a magic link. The user then enters the code on a verification screen within the app.

## User Flow

### OTP Flow (Default — checkbox checked)

1. User lands on `/auth/login`
2. Enters email address
3. "Use OTP Code?" checkbox is **checked by default**
4. Clicks **"Send Code"** button (label changes based on checkbox state)
5. App calls Supabase `signInWithOtp({ email, options: { shouldCreateUser: true } })` — Supabase sends a 6-digit code via email
6. UI transitions to **OTP verification screen** showing:
   - "Enter the 6-digit code sent to **{email}**"
   - Six individual digit input fields (or a single input with 6-char max)
   - A **"Resend code"** button with a visible **60-second cooldown timer**
   - A **"Use a different email"** link to go back
7. User enters the 6-digit code
8. App calls Supabase `verifyOtp({ email, token, type: 'email' })`
9. On success → session is created, user is redirected to `/` (home/dashboard)
10. On failure → inline error: "Invalid or expired code. Please try again."

### Magic Link Flow (checkbox unchecked)

1. Same as today — user enters email, clicks **"Send Magic Link"**
2. Shows "Check your email" confirmation with the magic link message
3. Clicking the email link redirects to `/auth/callback` which completes sign-in

## UI Design

### Login Page Changes

The existing login form is modified — not replaced. Changes:

- **Checkbox**: A Mantine `<Checkbox>` labeled **"Use OTP Code?"** placed between the email input and the submit button. Checked by default.
- **Submit button label**: Dynamic — shows **"Send Code"** when checkbox is checked, **"Send Magic Link"** when unchecked.
- **Subtitle text**: Dynamic — shows "Enter your email to receive a one-time code" (OTP) or "Enter your email to receive a magic link" (magic link).

### OTP Verification Screen

Shown inline on the same page (replaces the form, similar to how the "Check your email" confirmation works today):

- **Heading**: "Enter your code"
- **Subtext**: "We sent a 6-digit code to **{email}**"
- **Input**: A Mantine `<PinInput>` component with `length={6}`, `type="number"`, `oneTimeCode` autocomplete
- **Submit button**: "Verify Code" — enabled only when all 6 digits are entered
- **Resend section**: "Didn't get a code?" with a **"Resend code"** button
  - After sending, button is disabled for 60 seconds with visible countdown: "Resend code (45s)"
  - Timer resets on each resend
- **Back link**: "Use a different email" returns to the email input form
- **Error display**: Inline `<Alert>` below the code input on verification failure

## Technical Design

### Package Changes

#### 1. `packages/supabase/src/lib/hooks/useAuth.ts`

Add two new methods to the hook return value:

```typescript
signInWithOtp: async (email: string) => {
  const { error } = await supabase.auth.signInWithOtp({
    email,
    options: { shouldCreateUser: true },
  });
  return { error };
};

verifyOtp: async (email: string, token: string) => {
  const { data, error } = await supabase.auth.verifyOtp({
    email,
    token,
    type: 'email',
  });
  return { data, error };
};
```

The existing `signInWithMagicLink` method stays unchanged.

#### 2. `packages/web/src/app/context/AuthContext.tsx`

Extend `AuthContextValue` interface with:

```typescript
signInWithOtp: (email: string) => Promise<{ error: Error | null }>;
verifyOtp: (email: string, token: string) => Promise<{ data: unknown; error: Error | null }>;
```

#### 3. `packages/web/src/app/routes/auth/LoginPage.tsx`

Refactor to support both flows:

- Add state: `useOtp` (boolean, default `true`), `otpSent` (boolean), `otpToken` (string)
- Checkbox toggles `useOtp`
- Submit handler: if `useOtp`, call `signInWithOtp(email)` and set `otpSent = true`; else call `signInWithMagicLink(email)` and set `sent = true` (existing flow)
- When `otpSent` is true, render OTP verification screen with `<PinInput>`
- OTP verification calls `verifyOtp(email, otpToken)` — on success, Supabase fires `SIGNED_IN` event which triggers navigation via `onAuthStateChange`
- Resend timer: `useEffect` with `setInterval` counting down from 60

#### 4. `packages/web/src/mock/hooks/useMockAuth.ts`

Add mock implementations:

```typescript
signInWithOtp: async (_email: string) => {
  // Mock: always succeeds, simulates sending code
  return { error: null };
};

verifyOtp: async (_email: string, token: string) => {
  // Mock: accepts any 6-digit code (e.g., "123456")
  if (token.length === 6 && /^\d+$/.test(token)) {
    return { data: { user: mockUser, session: mockSession }, error: null };
  }
  return { data: null, error: new Error('Invalid OTP code') };
};
```

#### 5. `packages/web/src/mock/MockAuthProvider.tsx`

Pass `signInWithOtp` and `verifyOtp` from mock auth to the `AuthContext`.

#### 6. `packages/e2e/fixtures/auth.fixture.ts`

Add route mock for OTP verification:

```typescript
// POST /auth/v1/token?grant_type=otp — OTP code verification
await page.route(`${SUPABASE_URL}/auth/v1/verify*`, (route) => {
  return route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(session),
  });
});
```

#### 7. `packages/e2e/tests/auth.spec.ts`

Add new E2E tests:

- **"login page renders OTP checkbox checked by default"** — verify checkbox is present and checked
- **"submitting email with OTP sends code and shows verification screen"** — fill email, submit, verify PinInput appears
- **"entering valid OTP code signs in and redirects to dashboard"** — fill code, verify redirect
- **"resend code button has cooldown timer"** — click resend, verify button disabled with timer text
- **"unchecking OTP checkbox shows magic link flow"** — uncheck, submit, verify "Check your email" appears
- **"invalid OTP shows error message"** — mock verify endpoint to return error, verify error alert

## Supabase Configuration

No backend changes needed. Supabase's `signInWithOtp` already supports sending a 6-digit code when no `emailRedirectTo` is provided in the options. The `verifyOtp` method with `type: 'email'` handles verification. The OTP email template may be customized in the Supabase dashboard (Authentication → Email Templates → Magic Link) but is not required for functionality.

## Edge Cases & Error Handling

| Scenario | Behavior |
|---|---|
| Code expired (>60s by Supabase default) | Show "Invalid or expired code" error, user can resend |
| Wrong code entered | Show "Invalid or expired code" error, input clears |
| User enters code for wrong email | Verification fails, show error |
| Rate limiting (too many OTP requests) | Show Supabase error message as-is |
| Network error during send/verify | Show generic error with retry option |
| User navigates away mid-OTP | State resets, must restart flow |
| Resend while timer active | Button disabled, no action |

## Out of Scope

- SMS/phone OTP — email only
- Remember device / trusted device flow
- Custom OTP email template design (uses Supabase default)
- OTP code length customization (fixed at 6 digits)
- Password-based authentication
- Rate limit configuration (uses Supabase defaults)

## Success Metrics

- OTP login completes without leaving the app (no email client switch required for code entry)
- Both magic link and OTP flows work end-to-end
- Mock mode supports OTP flow for offline development
- All existing auth E2E tests continue to pass
- New OTP E2E tests pass

## Files to Modify

| File | Change |
|---|---|
| `packages/supabase/src/lib/hooks/useAuth.ts` | Add `signInWithOtp` and `verifyOtp` methods |
| `packages/web/src/app/context/AuthContext.tsx` | Extend `AuthContextValue` with new methods |
| `packages/web/src/app/routes/auth/LoginPage.tsx` | Add checkbox, OTP verification screen, resend timer |
| `packages/web/src/mock/hooks/useMockAuth.ts` | Add mock `signInWithOtp` and `verifyOtp` |
| `packages/web/src/mock/MockAuthProvider.tsx` | Pass new mock methods to context |
| `packages/e2e/fixtures/auth.fixture.ts` | Add OTP verify route mock |
| `packages/e2e/tests/auth.spec.ts` | Add OTP flow E2E tests |
