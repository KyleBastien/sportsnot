import type { Page } from '@playwright/test';

/**
 * Recorded bridge call. The shape matches the WidgetBridge method args.
 */
export type RecordedWidgetCall =
  | { method: 'setFeaturedLeague'; args: { shareCode: string } }
  | { method: 'isLiveActivitySupported'; args: Record<string, never> }
  | {
      method: 'startLiveActivity';
      args: { shareCode: string; leagueId: string; leagueName: string };
    }
  | { method: 'endLiveActivity'; args: Record<string, never> }
  | { method: 'getFeaturedLeague'; args: Record<string, never> }
  | { method: 'addListener'; args: { eventName: string } };

interface WidgetWindow extends Window {
  __widgetCalls: RecordedWidgetCall[];
}

/**
 * Installs a fake Capacitor environment + WidgetBridge plugin on the
 * page BEFORE any app script loads so isWidgetBridgeAvailable() returns
 * true and calls are captured on window.__widgetCalls.
 */
export async function installWidgetBridgeStub(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const calls: RecordedWidgetCall[] = [];
    (window as unknown as WidgetWindow).__widgetCalls = calls;

    const widgetBridgeStub = {
      setFeaturedLeague: async (args: { shareCode: string }) => {
        calls.push({ method: 'setFeaturedLeague', args });
        return { shareCode: args.shareCode };
      },
      getFeaturedLeague: async () => {
        calls.push({ method: 'getFeaturedLeague', args: {} });
        return { shareCode: null, allShareCodes: [] };
      },
      isLiveActivitySupported: async () => {
        calls.push({ method: 'isLiveActivitySupported', args: {} });
        return { supported: true };
      },
      startLiveActivity: async (args: {
        shareCode: string;
        leagueId: string;
        leagueName: string;
      }) => {
        calls.push({ method: 'startLiveActivity', args });
        return { activityId: 'fake-activity-1' };
      },
      endLiveActivity: async () => {
        calls.push({ method: 'endLiveActivity', args: {} });
      },
      addListener: async (eventName: string) => {
        calls.push({ method: 'addListener', args: { eventName } });
        return { remove: async () => undefined };
      },
    };

    const currentPlatform = {
      name: 'ios',
      getPlatform: () => 'ios',
      isNativePlatform: () => true,
      isPluginAvailable: (name: string) => name === 'WidgetBridge',
      getPluginHeader: () => undefined,
      registerPlugin: (name: string, options: Record<string, unknown>) => {
        if (name === 'WidgetBridge') return widgetBridgeStub;
        const webFactory = options['web'];
        if (typeof webFactory === 'function') {
          const result = (webFactory as () => unknown)();
          if (
            result &&
            typeof (result as Promise<unknown>).then === 'function'
          ) {
            return new Proxy(
              {},
              {
                get: () => () => Promise.resolve(undefined),
              }
            );
          }
          return result;
        }
        return new Proxy({}, { get: () => () => Promise.resolve(undefined) });
      },
    };

    (window as unknown as { CapacitorPlatforms: unknown }).CapacitorPlatforms =
      {
        currentPlatform,
        platforms: new Map([['ios', currentPlatform]]),
        addPlatform: () => undefined,
        setPlatform: () => undefined,
      };
  });
}

/**
 * Reads the recorded WidgetBridge calls from the page.
 */
export async function getWidgetCalls(
  page: Page
): Promise<RecordedWidgetCall[]> {
  return page.evaluate(
    () => (window as unknown as WidgetWindow).__widgetCalls ?? []
  );
}
