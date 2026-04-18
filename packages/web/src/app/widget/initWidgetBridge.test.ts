import { describe, it, expect } from '@rstest/core';
import { initWidgetBridge } from './initWidgetBridge';
import type {
  RegisterLiveActivityTokenRequest,
  WidgetApiClient,
} from '@sportsnot/widget-api';
import type { WidgetBridgePlugin } from '@sportsnot/widget-bridge';

type ActivityTokenListener = (event: {
  activityId: string;
  token: string;
  shareCode: string;
}) => void;

interface BridgeStub {
  bridge: Pick<WidgetBridgePlugin, 'addListener'>;
  emit: ActivityTokenListener;
  removeCalls: () => number;
}

function makeBridgeStub(): BridgeStub {
  let listener: ActivityTokenListener | null = null;
  let removeCalls = 0;
  const bridge: Pick<WidgetBridgePlugin, 'addListener'> = {
    addListener: (async (
      eventName: 'activityTokenUpdated',
      fn: ActivityTokenListener
    ) => {
      if (eventName !== 'activityTokenUpdated') {
        throw new Error(`unexpected event: ${eventName}`);
      }
      listener = fn;
      return {
        remove: async () => {
          removeCalls += 1;
        },
      };
    }) as WidgetBridgePlugin['addListener'],
  };
  return {
    bridge,
    emit: (event) => {
      if (!listener) throw new Error('listener not registered yet');
      listener(event);
    },
    removeCalls: () => removeCalls,
  };
}

function makeClientStub(): {
  client: Pick<WidgetApiClient, 'registerLiveActivityToken'>;
  calls: RegisterLiveActivityTokenRequest[];
  fail: (error: Error) => void;
} {
  const calls: RegisterLiveActivityTokenRequest[] = [];
  let nextError: Error | null = null;
  return {
    client: {
      registerLiveActivityToken: async (req) => {
        calls.push(req);
        if (nextError) {
          const e = nextError;
          nextError = null;
          throw e;
        }
      },
    },
    calls,
    fail: (error: Error) => {
      nextError = error;
    },
  };
}

describe('initWidgetBridge', () => {
  it('is a no-op when the native bridge is unavailable', async () => {
    const clientStub = makeClientStub();
    const bridgeStub = makeBridgeStub();
    const handle = await initWidgetBridge({
      supabaseUrl: 'https://x.supabase.co',
      anonKey: 'anon',
      bundleId: 'com.sportsnot.app',
      bridge: bridgeStub.bridge,
      client: clientStub.client,
      isAvailable: () => false,
    });
    await handle.remove();
    expect(clientStub.calls.length).toBe(0);
  });

  it('registers a listener and POSTs on each activityTokenUpdated event', async () => {
    const clientStub = makeClientStub();
    const bridgeStub = makeBridgeStub();
    const handle = await initWidgetBridge({
      supabaseUrl: 'https://x.supabase.co',
      anonKey: 'anon',
      bundleId: 'com.sportsnot.app',
      bridge: bridgeStub.bridge,
      client: clientStub.client,
      isAvailable: () => true,
    });

    bridgeStub.emit({
      activityId: 'activity-1',
      token: 'TOKEN_A',
      shareCode: 'SHARE1',
    });
    bridgeStub.emit({
      activityId: 'activity-2',
      token: 'TOKEN_B',
      shareCode: 'SHARE2',
    });

    // Let the fire-and-forget microtasks resolve.
    await new Promise((r) => setTimeout(r, 0));
    await new Promise((r) => setTimeout(r, 0));

    expect(clientStub.calls).toEqual([
      {
        shareCode: 'SHARE1',
        token: 'TOKEN_A',
        kind: 'activity',
        bundleId: 'com.sportsnot.app',
      },
      {
        shareCode: 'SHARE2',
        token: 'TOKEN_B',
        kind: 'activity',
        bundleId: 'com.sportsnot.app',
      },
    ]);

    await handle.remove();
    expect(bridgeStub.removeCalls()).toBe(1);
  });

  it('reports POST failures via onError and keeps listening', async () => {
    const clientStub = makeClientStub();
    const bridgeStub = makeBridgeStub();
    const errors: unknown[] = [];
    await initWidgetBridge({
      supabaseUrl: 'https://x.supabase.co',
      anonKey: 'anon',
      bundleId: 'com.sportsnot.app',
      bridge: bridgeStub.bridge,
      client: clientStub.client,
      isAvailable: () => true,
      onError: (e) => errors.push(e),
    });

    clientStub.fail(new Error('boom'));
    bridgeStub.emit({
      activityId: 'a',
      token: 'T1',
      shareCode: 'S',
    });
    await new Promise((r) => setTimeout(r, 0));
    await new Promise((r) => setTimeout(r, 0));

    expect(errors.length).toBe(1);
    expect((errors[0] as Error).message).toBe('boom');

    bridgeStub.emit({
      activityId: 'a2',
      token: 'T2',
      shareCode: 'S',
    });
    await new Promise((r) => setTimeout(r, 0));
    expect(clientStub.calls.length).toBe(2);
  });
});
