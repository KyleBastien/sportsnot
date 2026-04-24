import { test, expect } from '../fixtures/auth.fixture';
import {
  setupSupabaseMocks,
  mockTableData,
  mockTableList,
} from '../fixtures/supabase-mock.fixture';
import { mockUser } from '../fixtures/auth.fixture';

const NAV_TIMEOUT = { timeout: 15000 };
const SWIPE_FRAME_SELECTOR = '[data-native-swipe-back-frame]';
const TRANSITION_LEAGUE_ID = 'swipe-transition-league-1111';

interface TouchPoint {
  clientX: number;
  clientY: number;
}

function buildTransitionLeague() {
  return {
    id: TRANSITION_LEAGUE_ID,
    name: 'Swipe Transition League',
    commissioner_id: mockUser.id,
    invite_code: 'SWIPE1',
    max_participants: 4,
    status: 'active',
    current_round: 1,
    created_at: '2026-01-15T00:00:00.000Z',
    updated_at: '2026-02-14T00:00:00.000Z',
    league_members: [
      {
        id: 'member-1',
        user_id: mockUser.id,
        team_name: 'Swipe Team',
        total_points: 10,
        users: { display_name: 'Test User' },
      },
      {
        id: 'member-2',
        user_id: 'other-user-id',
        team_name: 'Other Team',
        total_points: 8,
        users: { display_name: 'Other Player' },
      },
    ],
  };
}

async function installNativePlatform(
  page: import('@playwright/test').Page,
  platform: 'ios' | 'android'
) {
  await page.addInitScript((platformName) => {
    (
      window as unknown as {
        CapacitorCustomPlatform?: { name: string };
      }
    ).CapacitorCustomPlatform = { name: platformName };
  }, platform);
}

async function dispatchTouch(
  page: import('@playwright/test').Page,
  type: 'touchstart' | 'touchmove' | 'touchend',
  touches: TouchPoint[]
) {
  await page.evaluate(
    ({ selector, eventType, points }) => {
      const element = document.querySelector(selector);

      if (!(element instanceof HTMLElement)) {
        throw new Error('Native swipe frame not found');
      }

      const event = new Event(eventType, {
        bubbles: true,
        cancelable: true,
      });

      const touchList = points.map((point, index) => ({
        identifier: index,
        target: element,
        clientX: point.clientX,
        clientY: point.clientY,
        pageX: point.clientX,
        pageY: point.clientY,
        screenX: point.clientX,
        screenY: point.clientY,
      }));

      Object.defineProperties(event, {
        touches: {
          value: eventType === 'touchend' ? [] : touchList,
        },
        targetTouches: {
          value: eventType === 'touchend' ? [] : touchList,
        },
        changedTouches: {
          value: touchList,
        },
      });

      element.dispatchEvent(event);
    },
    {
      selector: SWIPE_FRAME_SELECTOR,
      eventType: type,
      points: touches,
    }
  );
}

async function performEdgeSwipe(
  page: import('@playwright/test').Page,
  endOffsetPx: number
) {
  const frame = page.locator(SWIPE_FRAME_SELECTOR);
  const box = await frame.boundingBox();

  if (!box) {
    throw new Error('Native swipe frame bounding box missing');
  }

  const startX = box.x + 12;
  const endX = box.x + endOffsetPx;
  const clientY = box.y + Math.min(Math.max(box.height * 0.35, 60), 220);
  const steps = 6;

  await dispatchTouch(page, 'touchstart', [{ clientX: startX, clientY }]);

  for (let step = 1; step <= steps; step += 1) {
    const progress = step / steps;

    await dispatchTouch(page, 'touchmove', [
      {
        clientX: startX + (endX - startX) * progress,
        clientY,
      },
    ]);
    await page.evaluate(
      () => new Promise((resolve) => requestAnimationFrame(resolve))
    );
  }

  await dispatchTouch(page, 'touchend', [{ clientX: endX, clientY }]);
}

test.describe('native edge swipe back', () => {
  test('swipes back on native profile route', async ({ authenticatedPage }) => {
    await installNativePlatform(authenticatedPage, 'ios');
    await setupSupabaseMocks(authenticatedPage);

    await authenticatedPage.goto('/');
    await expect(
      authenticatedPage.getByRole('heading', { name: /^dashboard$/i })
    ).toBeVisible(NAV_TIMEOUT);

    await authenticatedPage.goto('/profile');
    await expect(
      authenticatedPage.getByRole('heading', { name: /^profile$/i })
    ).toBeVisible(NAV_TIMEOUT);
    await expect(
      authenticatedPage.locator(
        '.native-swipe-back-frame__page .mantine-AppShell-header'
      )
    ).toBeVisible(NAV_TIMEOUT);

    await performEdgeSwipe(authenticatedPage, 220);

    await expect(authenticatedPage).toHaveURL(
      /^http:\/\/localhost:\d+\/?$/,
      NAV_TIMEOUT
    );
    await expect(
      authenticatedPage.getByRole('heading', { name: /^dashboard$/i })
    ).toBeVisible(NAV_TIMEOUT);
  });

  test('cancels short swipe on native route', async ({ authenticatedPage }) => {
    await installNativePlatform(authenticatedPage, 'android');
    await setupSupabaseMocks(authenticatedPage);

    await authenticatedPage.goto('/profile');
    await expect(
      authenticatedPage.getByRole('heading', { name: /^profile$/i })
    ).toBeVisible(NAV_TIMEOUT);

    await performEdgeSwipe(authenticatedPage, 72);

    await expect(authenticatedPage).toHaveURL(/\/profile$/, NAV_TIMEOUT);
    await expect(
      authenticatedPage.getByRole('heading', { name: /^profile$/i })
    ).toBeVisible(NAV_TIMEOUT);
  });

  test('does nothing on blocked draft routes', async ({
    authenticatedPage,
  }) => {
    await installNativePlatform(authenticatedPage, 'ios');

    const league = buildTransitionLeague();

    await setupSupabaseMocks(authenticatedPage, {
      leagues: mockTableData([league], league),
      drafts: mockTableList([
        {
          id: 'draft-complete-1',
          round: 1,
          status: 'completed',
          completed_at: '2026-02-14T12:00:00.000Z',
        },
      ]),
    });

    await authenticatedPage.goto(`/draft/${TRANSITION_LEAGUE_ID}/transition`);
    await expect(
      authenticatedPage.getByRole('heading', {
        name: /round \d+ complete/i,
      })
    ).toBeVisible(NAV_TIMEOUT);

    await performEdgeSwipe(authenticatedPage, 220);

    await expect(authenticatedPage).toHaveURL(
      new RegExp(`/draft/${TRANSITION_LEAGUE_ID}/transition$`),
      NAV_TIMEOUT
    );
  });

  test('stays inert on web builds', async ({ authenticatedPage }) => {
    await setupSupabaseMocks(authenticatedPage);

    await authenticatedPage.goto('/profile');
    await expect(
      authenticatedPage.getByRole('heading', { name: /^profile$/i })
    ).toBeVisible(NAV_TIMEOUT);

    await performEdgeSwipe(authenticatedPage, 220);

    await expect(authenticatedPage).toHaveURL(/\/profile$/, NAV_TIMEOUT);
  });
});
