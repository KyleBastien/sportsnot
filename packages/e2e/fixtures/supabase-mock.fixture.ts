import { test as authTest } from './auth.fixture';
import type { Page } from '@playwright/test';

const SUPABASE_URL = 'http://localhost:54321';

/** Tables that will be mocked by default */
const TABLES = [
  'leagues',
  'league_members',
  'drafts',
  'draft_picks',
  'rosters',
  'player_stats_cache',
  'team_stats_cache',
  'scoring_events',
] as const;

type TableName = (typeof TABLES)[number];

/** PostgREST error shape */
interface PostgRESTError {
  message: string;
  details: string | null;
  hint: string | null;
  code: string;
}

/** Route override map: table name → handler function */
export type RouteOverrides = Partial<
  Record<TableName, (route: import('@playwright/test').Route) => Promise<void>>
>;

/**
 * Sets up default PostgREST mock routes for all known tables.
 *
 * Default behaviour:
 *   - GET  /rest/v1/TABLE  → 200 with empty array  (list queries)
 *   - GET  /rest/v1/TABLE with Accept: application/vnd.pgrst.object+json → 406 single-row not found
 *   - POST /rest/v1/TABLE  → 201 with empty object
 *   - PATCH /rest/v1/TABLE → 200 with empty object
 *   - DELETE /rest/v1/TABLE → 204
 *
 * Callers can pass `overrides` to replace the handler for specific tables.
 */
export async function setupSupabaseMocks(
  page: Page,
  overrides: RouteOverrides = {}
) {
  for (const table of TABLES) {
    const pattern = `${SUPABASE_URL}/rest/v1/${table}*`;

    if (overrides[table]) {
      await page.route(pattern, overrides[table]!);
      continue;
    }

    await page.route(pattern, async (route) => {
      const request = route.request();
      const method = request.method();
      const accept = request.headers()['accept'] ?? '';

      if (method === 'GET') {
        // .single() sends this Accept header — return 406 (no rows)
        if (accept.includes('vnd.pgrst.object+json')) {
          const error: PostgRESTError = {
            message:
              'JSON object requested, multiple (or no) rows returned',
            details:
              'Results contain 0 rows, application/vnd.pgrst.object+json requires 1 row',
            hint: null,
            code: 'PGRST116',
          };
          return route.fulfill({
            status: 406,
            contentType: 'application/json',
            body: JSON.stringify(error),
          });
        }

        // Default list query — empty array
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([]),
        });
      }

      if (method === 'POST') {
        return route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify({}),
        });
      }

      if (method === 'PATCH') {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({}),
        });
      }

      if (method === 'DELETE') {
        return route.fulfill({ status: 204, body: '' });
      }

      // Fallback for any other method
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
    });
  }

  // Stub Supabase Realtime WebSocket to prevent hanging connections
  await page.routeWebSocket(`${SUPABASE_URL}/realtime/**`, (ws) => {
    // Accept the connection but do nothing — prevents timeouts
    ws.onMessage(() => {
      // Silently consume messages; no realtime events emitted
    });
  });
}

/**
 * Helper to create a route handler that returns a JSON array (list query).
 */
export function mockTableList<T>(data: T[]) {
  return async (route: import('@playwright/test').Route) => {
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(data),
    });
  };
}

/**
 * Helper to create a route handler that returns a single object or a list,
 * depending on the Accept header (handles both .select() and .single()).
 */
export function mockTableData<T>(listData: T[], singleData?: T) {
  return async (route: import('@playwright/test').Route) => {
    const request = route.request();
    const method = request.method();
    const accept = request.headers()['accept'] ?? '';

    if (method === 'GET') {
      if (accept.includes('vnd.pgrst.object+json')) {
        if (singleData) {
          return route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify(singleData),
          });
        }
        // No single data — return PostgREST 406
        const error: PostgRESTError = {
          message:
            'JSON object requested, multiple (or no) rows returned',
          details:
            'Results contain 0 rows, application/vnd.pgrst.object+json requires 1 row',
          hint: null,
          code: 'PGRST116',
        };
        return route.fulfill({
          status: 406,
          contentType: 'application/json',
          body: JSON.stringify(error),
        });
      }
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(listData),
      });
    }

    if (method === 'POST') {
      return route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify(singleData ?? {}),
      });
    }

    if (method === 'PATCH') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(singleData ?? {}),
      });
    }

    if (method === 'DELETE') {
      return route.fulfill({ status: 204, body: '' });
    }

    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(listData),
    });
  };
}

/**
 * Helper to create a route handler that returns a PostgREST error.
 */
export function mockTableError(
  status: number,
  message: string,
  code = 'PGRST000'
) {
  return async (route: import('@playwright/test').Route) => {
    const error: PostgRESTError = {
      message,
      details: null,
      hint: null,
      code,
    };
    return route.fulfill({
      status,
      contentType: 'application/json',
      body: JSON.stringify(error),
    });
  };
}

// ---------------------------------------------------------------------------
// Extended Playwright fixtures with Supabase REST + Realtime mocks
// ---------------------------------------------------------------------------

export const test = authTest.extend<{
  /** Authenticated page with all Supabase REST/Realtime endpoints mocked (empty defaults) */
  supabasePage: Page;
}>({
  supabasePage: async ({ authenticatedPage }, use) => {
    await setupSupabaseMocks(authenticatedPage);
    await use(authenticatedPage);
  },
});

export { expect } from '@playwright/test';
