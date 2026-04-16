import { test, expect } from '../fixtures/auth.fixture';
import { setupSupabaseMocks } from '../fixtures/supabase-mock.fixture';
import { mockUser } from '../fixtures/auth.fixture';
import {
  installWidgetBridgeStub,
  getWidgetCalls,
} from '../fixtures/widget-bridge.fixture';

const NAV_TIMEOUT = { timeout: 15000 };
const LEAGUE_ID = 'bbbbbbbb-cccc-dddd-eeee-ffffffffffff';
const SHARE_CODE = 'SHARE123';

function buildLeague() {
  return {
    id: LEAGUE_ID,
    name: 'Widget League',
    commissioner_id: mockUser.id,
    invite_code: 'WIDGETCD',
    share_code: SHARE_CODE,
    max_participants: 8,
    status: 'active',
    current_round: 1,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    league_members: [
      {
        id: 'member-1',
        user_id: mockUser.id,
        team_name: 'Alpha',
        total_points: 10,
        users: {
          display_name: mockUser.user_metadata.display_name,
          avatar_url: mockUser.user_metadata.avatar_url,
        },
      },
      {
        id: 'member-2',
        user_id: '99999999-8888-7777-6666-555555555555',
        team_name: 'Beta',
        total_points: 12,
        users: {
          display_name: 'Other Player',
          avatar_url: 'https://example.com/other.png',
        },
      },
    ],
  };
}

test.describe('FeatureOnWidgetButton', () => {
  test('native iOS shell: setFeaturedLeague + startLiveActivity are called with the league share code', async ({
    authenticatedPage,
  }) => {
    await installWidgetBridgeStub(authenticatedPage);
    const league = buildLeague();
    await setupSupabaseMocks(authenticatedPage, {
      leagues: async (route) => {
        const req = route.request();
        const accept = req.headers()['accept'] ?? '';
        if (
          req.method() === 'GET' &&
          accept.includes('vnd.pgrst.object+json')
        ) {
          return route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify(league),
          });
        }
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([]),
        });
      },
    });

    await authenticatedPage.goto(`/leagues/${LEAGUE_ID}`);

    await expect(
      authenticatedPage.getByRole('heading', { name: 'Widget League' })
    ).toBeVisible(NAV_TIMEOUT);

    const button = authenticatedPage.getByRole('button', {
      name: /feature on iOS widget/i,
    });
    await expect(button).toBeVisible();
    await button.click();

    await expect(
      authenticatedPage.getByRole('button', { name: /widget updated/i })
    ).toBeVisible(NAV_TIMEOUT);

    const calls = await getWidgetCalls(authenticatedPage);
    const methods = calls.map((c) => c.method);

    expect(methods).toContain('setFeaturedLeague');
    expect(methods).toContain('isLiveActivitySupported');
    expect(methods).toContain('startLiveActivity');

    const setFeatured = calls.find((c) => c.method === 'setFeaturedLeague');
    expect(setFeatured?.args).toEqual({ shareCode: SHARE_CODE });

    const startLive = calls.find((c) => c.method === 'startLiveActivity');
    expect(startLive?.args).toEqual({
      shareCode: SHARE_CODE,
      leagueId: LEAGUE_ID,
      leagueName: 'Widget League',
    });
  });
});
