import { test, expect, SUPABASE_URL } from '../fixtures/auth.fixture';
import { mockUser } from '../fixtures/auth.fixture';
import { setupSupabaseMocks } from '../fixtures/supabase-mock.fixture';

const NAV_TIMEOUT = { timeout: 15000 };

test.describe('Authentication Flow', () => {
  test('unauthenticated user visiting / is redirected to /auth/login', async ({
    unauthenticatedPage,
  }) => {
    await setupSupabaseMocks(unauthenticatedPage);
    await unauthenticatedPage.goto('/');
    await expect(unauthenticatedPage).toHaveURL(/\/auth\/login/, NAV_TIMEOUT);
  });

  test('login page renders magic link email form', async ({
    unauthenticatedPage,
  }) => {
    await setupSupabaseMocks(unauthenticatedPage);
    await unauthenticatedPage.goto('/auth/login');

    await expect(
      unauthenticatedPage.getByRole('heading', {
        name: /sign in to sportsnot/i,
      })
    ).toBeVisible(NAV_TIMEOUT);

    await expect(
      unauthenticatedPage.getByPlaceholder('you@example.com')
    ).toBeVisible();

    // OTP checkbox is checked by default, so button reads "Send Code"
    await expect(
      unauthenticatedPage.getByRole('button', { name: /send code/i })
    ).toBeVisible();

    // Uncheck OTP to get magic link flow
    await unauthenticatedPage
      .getByRole('checkbox', { name: /use otp code/i })
      .uncheck();

    await expect(
      unauthenticatedPage.getByRole('button', { name: /send magic link/i })
    ).toBeVisible();
  });

  test('submitting email shows check your email confirmation', async ({
    unauthenticatedPage,
  }) => {
    await setupSupabaseMocks(unauthenticatedPage);
    await unauthenticatedPage.goto('/auth/login');

    // Wait for the form to render
    await expect(
      unauthenticatedPage.getByPlaceholder('you@example.com')
    ).toBeVisible(NAV_TIMEOUT);

    // Uncheck OTP to use magic link flow
    await unauthenticatedPage
      .getByRole('checkbox', { name: /use otp code/i })
      .uncheck();

    await unauthenticatedPage
      .getByPlaceholder('you@example.com')
      .fill('user@test.com');
    await unauthenticatedPage
      .getByRole('button', { name: /send magic link/i })
      .click();

    await expect(
      unauthenticatedPage.getByText(/check your email/i)
    ).toBeVisible(NAV_TIMEOUT);
    await expect(unauthenticatedPage.getByText(/user@test\.com/)).toBeVisible();
  });

  test('auth callback with valid token sets session and redirects to dashboard', async ({
    authenticatedPage,
  }) => {
    await setupSupabaseMocks(authenticatedPage);

    // Simulate magic link redirect with hash params containing token data.
    // Supabase JS reads the hash, validates tokens, fires SIGNED_IN event,
    // and AuthCallbackPage navigates to /.
    const hashParams = new URLSearchParams({
      access_token: 'mock-access-token-for-testing',
      refresh_token: 'mock-refresh-token-for-testing',
      expires_in: '3600',
      expires_at: String(Math.floor(Date.now() / 1000) + 3600),
      token_type: 'bearer',
      type: 'magiclink',
    });
    await authenticatedPage.goto(`/auth/callback#${hashParams.toString()}`);

    // Should redirect to dashboard (root)
    await expect(authenticatedPage).toHaveURL(
      /^http:\/\/localhost:\d+\/?$/,
      NAV_TIMEOUT
    );
  });

  test('authenticated user can sign out and is redirected to login', async ({
    authenticatedPage,
  }) => {
    await setupSupabaseMocks(authenticatedPage);
    await authenticatedPage.goto('/');

    // Wait for the authenticated dashboard to load
    await authenticatedPage.waitForLoadState('domcontentloaded');

    // The user menu trigger is an UnstyledButton containing the user's avatar
    // and display name. Use .or() to handle small viewports where text is hidden.
    const displayName = mockUser.user_metadata.display_name;
    const menuTrigger = authenticatedPage
      .getByRole('button')
      .filter({ has: authenticatedPage.getByText(displayName) })
      .or(
        authenticatedPage
          .locator('header button')
          .filter({ hasText: displayName[0].toUpperCase() })
      );
    await menuTrigger.first().click();

    // Click Sign Out in the dropdown menu
    await authenticatedPage
      .getByRole('menuitem', { name: /sign out/i })
      .click();

    await expect(authenticatedPage).toHaveURL(/\/auth\/login/, NAV_TIMEOUT);
  });

  test('submitting email with OTP sends code and shows verification screen', async ({
    unauthenticatedPage,
  }) => {
    await setupSupabaseMocks(unauthenticatedPage);
    await unauthenticatedPage.goto('/auth/login');

    await expect(
      unauthenticatedPage.getByPlaceholder('you@example.com')
    ).toBeVisible(NAV_TIMEOUT);

    // OTP checkbox is checked by default — fill email and submit
    await unauthenticatedPage
      .getByPlaceholder('you@example.com')
      .fill('user@test.com');
    await unauthenticatedPage
      .getByRole('button', { name: /send code/i })
      .click();

    // Verification screen should appear
    await expect(
      unauthenticatedPage.getByRole('heading', { name: /enter your code/i })
    ).toBeVisible(NAV_TIMEOUT);
    await expect(unauthenticatedPage.getByText(/user@test\.com/)).toBeVisible();

    // PinInput renders 6 individual input fields
    const pinInputs = unauthenticatedPage.locator('input[type="tel"]');
    await expect(pinInputs.first()).toBeVisible();

    // Verify Code button should be visible but disabled (no digits entered)
    const verifyButton = unauthenticatedPage.getByRole('button', {
      name: /verify code/i,
    });
    await expect(verifyButton).toBeVisible();
    await expect(verifyButton).toBeDisabled();
  });

  test('entering valid OTP code signs in and redirects to dashboard', async ({
    unauthenticatedPage,
  }) => {
    // Override verify endpoint to return a valid session
    // (registered after fixture mocks, so takes precedence)
    await unauthenticatedPage.route('**/auth/v1/verify*', (route) => {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          access_token: 'mock-access-token-for-testing',
          token_type: 'bearer',
          expires_in: 3600,
          expires_at: Math.floor(Date.now() / 1000) + 3600,
          refresh_token: 'mock-refresh-token-for-testing',
          user: mockUser,
        }),
      });
    });

    await setupSupabaseMocks(unauthenticatedPage);
    await unauthenticatedPage.goto('/auth/login');

    await expect(
      unauthenticatedPage.getByPlaceholder('you@example.com')
    ).toBeVisible(NAV_TIMEOUT);

    // Fill email and submit OTP
    await unauthenticatedPage
      .getByPlaceholder('you@example.com')
      .fill('user@test.com');
    await unauthenticatedPage
      .getByRole('button', { name: /send code/i })
      .click();

    // Wait for verification screen
    await expect(
      unauthenticatedPage.getByRole('heading', { name: /enter your code/i })
    ).toBeVisible(NAV_TIMEOUT);

    // Fill in 6-digit OTP code via the pin input fields
    const pinInputs = unauthenticatedPage.locator('input[type="tel"]');
    for (let i = 0; i < 6; i++) {
      await pinInputs.nth(i).fill(String(i + 1));
    }

    // Click Verify Code
    await unauthenticatedPage
      .getByRole('button', { name: /verify code/i })
      .click();

    // Should redirect to dashboard (root) after successful verification
    await expect(unauthenticatedPage).toHaveURL(
      /^http:\/\/localhost:\d+\/?$/,
      NAV_TIMEOUT
    );
  });

  test('resend code button has cooldown timer', async ({
    unauthenticatedPage,
  }) => {
    await setupSupabaseMocks(unauthenticatedPage);
    await unauthenticatedPage.goto('/auth/login');

    await expect(
      unauthenticatedPage.getByPlaceholder('you@example.com')
    ).toBeVisible(NAV_TIMEOUT);

    // Submit email with OTP
    await unauthenticatedPage
      .getByPlaceholder('you@example.com')
      .fill('user@test.com');
    await unauthenticatedPage
      .getByRole('button', { name: /send code/i })
      .click();

    // Wait for verification screen
    await expect(
      unauthenticatedPage.getByRole('heading', { name: /enter your code/i })
    ).toBeVisible(NAV_TIMEOUT);

    // Resend button should be disabled with countdown text
    const resendButton = unauthenticatedPage.getByRole('button', {
      name: /resend code/i,
    });
    await expect(resendButton).toBeVisible();
    await expect(resendButton).toBeDisabled();
    await expect(resendButton).toHaveText(/resend code \(\d+s\)/i);

    // "Didn't get a code?" text should be visible
    await expect(
      unauthenticatedPage.getByText(/didn.t get a code/i)
    ).toBeVisible();
  });

  test('unchecking OTP checkbox shows magic link flow', async ({
    unauthenticatedPage,
  }) => {
    await setupSupabaseMocks(unauthenticatedPage);
    await unauthenticatedPage.goto('/auth/login');

    await expect(
      unauthenticatedPage.getByPlaceholder('you@example.com')
    ).toBeVisible(NAV_TIMEOUT);

    // Uncheck OTP checkbox
    await unauthenticatedPage
      .getByRole('checkbox', { name: /use otp code/i })
      .uncheck();

    // Fill email and submit magic link
    await unauthenticatedPage
      .getByPlaceholder('you@example.com')
      .fill('user@test.com');
    await unauthenticatedPage
      .getByRole('button', { name: /send magic link/i })
      .click();

    // Should show check your email confirmation
    await expect(
      unauthenticatedPage.getByText(/check your email/i)
    ).toBeVisible(NAV_TIMEOUT);
  });

  test('expired/invalid session redirects to login page', async ({
    unauthenticatedPage,
  }) => {
    await setupSupabaseMocks(unauthenticatedPage);

    // Seed an expired session in localStorage — Supabase will try to refresh
    // and fail (unauthenticatedPage mock returns 400 for token refresh),
    // resulting in a null session and redirect to login.
    await unauthenticatedPage.addInitScript(
      ({ url }) => {
        const storageKey = `sb-${new URL(url).hostname}-auth-token`;
        window.localStorage.setItem(
          storageKey,
          JSON.stringify({
            access_token: 'expired-token',
            token_type: 'bearer',
            expires_in: 0,
            expires_at: Math.floor(Date.now() / 1000) - 3600,
            refresh_token: 'invalid-refresh-token',
            user: null,
          })
        );
      },
      { url: SUPABASE_URL }
    );

    await unauthenticatedPage.goto('/');
    await expect(unauthenticatedPage).toHaveURL(/\/auth\/login/, NAV_TIMEOUT);
  });
});
