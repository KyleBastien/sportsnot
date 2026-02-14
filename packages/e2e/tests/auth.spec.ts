import { test, expect } from '../fixtures/auth.fixture';
import { mockUser } from '../fixtures/auth.fixture';
import { setupSupabaseMocks } from '../fixtures/supabase-mock.fixture';

const SUPABASE_URL = 'http://localhost:54321';
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

    await unauthenticatedPage
      .getByPlaceholder('you@example.com')
      .fill('user@test.com');
    await unauthenticatedPage
      .getByRole('button', { name: /send magic link/i })
      .click();

    await expect(
      unauthenticatedPage.getByText(/check your email/i)
    ).toBeVisible(NAV_TIMEOUT);
    await expect(
      unauthenticatedPage.getByText(/user@test\.com/)
    ).toBeVisible();
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
    await authenticatedPage.waitForLoadState('networkidle');

    // The user menu trigger is an UnstyledButton containing the user's avatar
    // and display name. Click it to open the dropdown.
    const displayName = mockUser.user_metadata.display_name;
    const menuTrigger = authenticatedPage.getByRole('button').filter({
      has: authenticatedPage.getByText(displayName),
    });

    // If display name text is hidden on small viewports, fall back to avatar
    const triggerCount = await menuTrigger.count();
    if (triggerCount > 0) {
      await menuTrigger.first().click();
    } else {
      // Click the avatar button in the header
      await authenticatedPage
        .locator('header button')
        .filter({ hasText: displayName[0].toUpperCase() })
        .click();
    }

    // Click Sign Out in the dropdown menu
    await authenticatedPage
      .getByRole('menuitem', { name: /sign out/i })
      .click();

    await expect(authenticatedPage).toHaveURL(/\/auth\/login/, NAV_TIMEOUT);
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
