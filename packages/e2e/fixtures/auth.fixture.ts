import { test as base, type Page } from '@playwright/test';
import { readFileSync } from 'fs';
import { resolve } from 'path';

function getSupabaseUrl(): string {
  if (process.env.VITE_SUPABASE_URL) return process.env.VITE_SUPABASE_URL;
  try {
    const content = readFileSync(resolve(__dirname, '../../../.env'), 'utf-8');
    const match = content.match(/^VITE_SUPABASE_URL=(.+)$/m);
    if (match) return match[1].trim();
  } catch {
    /* ignore */
  }
  return 'http://localhost:54321';
}

export const SUPABASE_URL = getSupabaseUrl();

/** Mock user data matching Supabase auth user shape */
export const mockUser = {
  id: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
  aud: 'authenticated',
  role: 'authenticated',
  email: 'testuser@sportsnot.test',
  email_confirmed_at: '2026-01-01T00:00:00.000Z',
  phone: '',
  confirmed_at: '2026-01-01T00:00:00.000Z',
  last_sign_in_at: '2026-02-14T12:00:00.000Z',
  app_metadata: { provider: 'email', providers: ['email'] },
  user_metadata: {
    display_name: 'Test User',
    avatar_url: 'https://example.com/avatar.png',
  },
  identities: [],
  created_at: '2026-01-01T00:00:00.000Z',
  updated_at: '2026-02-14T12:00:00.000Z',
};

/** Mock session with valid access/refresh tokens */
const mockSession = {
  access_token: 'mock-access-token-for-testing',
  token_type: 'bearer',
  expires_in: 3600,
  expires_at: Math.floor(Date.now() / 1000) + 3600,
  refresh_token: 'mock-refresh-token-for-testing',
  user: mockUser,
};

/**
 * Intercept all Supabase auth endpoints on a page and respond
 * with either an authenticated session or an unauthenticated state.
 */
async function setupAuthMocks(page: Page, authenticated: boolean) {
  const session = authenticated ? mockSession : null;
  const user = authenticated ? mockUser : null;

  // GET /auth/v1/user — Supabase calls this to verify the current user
  await page.route('**/auth/v1/user', (route) => {
    if (!authenticated) {
      return route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({
          message: 'Invalid token',
          status: 401,
        }),
      });
    }
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(user),
    });
  });

  // POST /auth/v1/token?grant_type=refresh_token — token refresh
  await page.route('**/auth/v1/token?grant_type=refresh_token', (route) => {
    if (!authenticated) {
      return route.fulfill({
        status: 400,
        contentType: 'application/json',
        body: JSON.stringify({
          error: 'invalid_grant',
          error_description: 'Invalid Refresh Token',
        }),
      });
    }
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(session),
    });
  });

  // POST /auth/v1/token?grant_type=password — password-based sign-in
  await page.route('**/auth/v1/token?grant_type=password', (route) => {
    if (!authenticated) {
      return route.fulfill({
        status: 400,
        contentType: 'application/json',
        body: JSON.stringify({
          error: 'invalid_grant',
          error_description: 'Invalid credentials',
        }),
      });
    }
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(session),
    });
  });

  // POST /auth/v1/otp — magic link request (glob to match query params like ?redirect_to=...)
  await page.route('**/auth/v1/otp**', (route) => {
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({}),
    });
  });

  // POST /auth/v1/verify — OTP code verification
  await page.route('**/auth/v1/verify*', (route) => {
    if (!authenticated) {
      return route.fulfill({
        status: 400,
        contentType: 'application/json',
        body: JSON.stringify({
          error: 'otp_expired',
          error_description: 'Token has expired or is invalid',
        }),
      });
    }
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(session),
    });
  });

  // POST /auth/v1/signout — sign out
  await page.route('**/auth/v1/signout**', (route) => {
    return route.fulfill({
      status: 204,
      body: '',
    });
  });

  // POST /auth/v1/logout — logout endpoint (needs trailing ** for ?scope= query params)
  await page.route('**/auth/v1/logout**', (route) => {
    return route.fulfill({
      status: 204,
      body: '',
    });
  });

  // Inject auth session into localStorage so Supabase JS picks it up
  if (authenticated) {
    await page.addInitScript(
      ({ url, session }) => {
        const storageKey = `sb-${new URL(url).hostname.split('.')[0]}-auth-token`;
        window.localStorage.setItem(storageKey, JSON.stringify(session));
      },
      { url: SUPABASE_URL, session: mockSession }
    );
  }
}

/** Custom fixtures that extend Playwright's base test */
export const test = base.extend<{
  authenticatedPage: Page;
  unauthenticatedPage: Page;
}>({
  /** A page with mocked Supabase auth returning a valid session */
  authenticatedPage: async ({ page }, use) => {
    await setupAuthMocks(page, true);
    await use(page);
  },
  /** A page with mocked Supabase auth returning no session */
  unauthenticatedPage: async ({ page }, use) => {
    await setupAuthMocks(page, false);
    await use(page);
  },
});

export { expect } from '@playwright/test';
