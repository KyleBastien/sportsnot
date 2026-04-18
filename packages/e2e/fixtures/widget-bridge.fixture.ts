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

    // Capacitor's getPlatform() reads from window.CapacitorCustomPlatform.
    // Setting this to { name: 'ios' } makes Capacitor.isNativePlatform()
    // return true and Capacitor.getPlatform() return 'ios', which is what
    // isWidgetBridgeAvailable() checks.
    (
      window as unknown as { CapacitorCustomPlatform: { name: string } }
    ).CapacitorCustomPlatform = { name: 'ios' };

    // For native plugins, registerPlugin() returns a Proxy whose method
    // wrappers call cap.nativePromise(pluginName, methodName, args) — but
    // only when there's a matching PluginHeader entry on window.Capacitor.
    // We seed a PluginHeader for WidgetBridge and replace nativePromise
    // with a recorder that delegates to our stub.
    const cap =
      (
        window as unknown as {
          Capacitor?: Record<string, unknown>;
        }
      ).Capacitor ?? {};

    cap.PluginHeaders = [
      {
        name: 'WidgetBridge',
        methods: [
          { name: 'setFeaturedLeague', rtype: 'promise' },
          { name: 'getFeaturedLeague', rtype: 'promise' },
          { name: 'isLiveActivitySupported', rtype: 'promise' },
          { name: 'startLiveActivity', rtype: 'promise' },
          { name: 'endLiveActivity', rtype: 'promise' },
        ],
      },
    ];

    cap.nativePromise = (
      pluginName: string,
      methodName: string,
      options: unknown
    ) => {
      if (pluginName !== 'WidgetBridge') return Promise.resolve(undefined);
      const stub = widgetBridgeStub as Record<
        string,
        (args: unknown) => Promise<unknown>
      >;
      const fn = stub[methodName];
      if (typeof fn === 'function') return fn(options ?? {});
      return Promise.resolve(undefined);
    };

    (window as unknown as { Capacitor: typeof cap }).Capacitor = cap;
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
