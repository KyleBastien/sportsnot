import { describe, expect, it, beforeEach } from '@rstest/core';
import { WidgetBridgeWeb } from './widget-bridge.web';

function installStubWindow() {
  const store = new Map<string, string>();
  const localStorage = {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => {
      store.set(k, v);
    },
    removeItem: (k: string) => store.delete(k),
    clear: () => store.clear(),
    key: () => null,
    length: 0,
  };
  (
    globalThis as unknown as { window: { localStorage: typeof localStorage } }
  ).window = {
    localStorage,
  };
}

describe('WidgetBridgeWeb', () => {
  beforeEach(() => {
    installStubWindow();
  });

  it('persists the featured share code and accumulates all codes', async () => {
    const bridge = new WidgetBridgeWeb();
    await bridge.setFeaturedLeague({ shareCode: 'A1B2C3' });
    await bridge.setFeaturedLeague({ shareCode: 'X9Y8Z7' });
    await bridge.setFeaturedLeague({ shareCode: 'A1B2C3' });

    const result = await bridge.getFeaturedLeague();
    expect(result.shareCode).toBe('A1B2C3');
    expect(result.allShareCodes).toEqual(['A1B2C3', 'X9Y8Z7']);
  });

  it('reports live activities as unsupported on the web', async () => {
    const bridge = new WidgetBridgeWeb();
    const result = await bridge.isLiveActivitySupported();
    expect(result.supported).toBe(false);
  });

  it('rejects startLiveActivity on the web', async () => {
    const bridge = new WidgetBridgeWeb();
    await expect(
      bridge.startLiveActivity({
        shareCode: 'S',
        leagueId: 'L',
        leagueName: 'Name',
      })
    ).rejects.toBeDefined();
  });
});
