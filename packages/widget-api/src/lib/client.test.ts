import { describe, it, expect } from '@rstest/core';
import { WidgetApiClient } from './client';
import type { WidgetSnapshot } from './types';

function makeSnapshot(): WidgetSnapshot {
  return {
    league: {
      id: 'l1',
      name: 'L',
      shareCode: 'ABC',
      currentRound: 1,
      status: 'active',
    },
    date: '2026-04-16',
    generatedAt: '2026-04-16T17:00:00Z',
    games: [],
    players: [],
  };
}

describe('WidgetApiClient', () => {
  type RequestHeaders = Headers | Record<string, string> | string[][];

  it('getSnapshot passes shareCode + optional date as query params', async () => {
    const snap = makeSnapshot();
    const calls: string[] = [];
    const headers: Array<Record<string, string> | Headers | undefined> = [];
    const client = new WidgetApiClient({
      supabaseUrl: 'https://x.supabase.co',
      anonKey: 'anon',
      fetch: async (input, init) => {
        calls.push(String(input));
        headers.push(init?.headers as Record<string, string> | Headers);
        return new Response(JSON.stringify(snap), { status: 200 });
      },
    });
    const result = await client.getSnapshot('SHARE', '2026-04-16');
    expect(result.league.shareCode).toBe('ABC');
    expect(calls[0]).toContain('shareCode=SHARE');
    expect(calls[0]).toContain('date=2026-04-16');
    expect(calls[0]).toContain('/functions/v1/widget-league-snapshot');
    expect(headers[0]).toEqual({ Accept: 'application/json' });
  });

  it('getSnapshot throws on non-2xx', async () => {
    const client = new WidgetApiClient({
      supabaseUrl: 'https://x.supabase.co',
      anonKey: 'anon',
      fetch: async () => new Response('nope', { status: 404 }),
    });
    await expect(client.getSnapshot('SHARE')).rejects.toThrow(
      /widget-league-snapshot failed/
    );
  });

  it('registerLiveActivityToken POSTs the request body', async () => {
    let capturedBody: unknown;
    let capturedMethod: string | undefined;
    let capturedHeaders: RequestHeaders | undefined;
    const client = new WidgetApiClient({
      supabaseUrl: 'https://x.supabase.co',
      anonKey: 'anon',
      fetch: async (_input, init) => {
        capturedMethod = init?.method;
        capturedBody = init?.body;
        capturedHeaders = init?.headers;
        return new Response(null, { status: 200 });
      },
    });
    await client.registerLiveActivityToken({
      shareCode: 'SHARE',
      token: 'TOKEN',
      kind: 'activity',
      bundleId: 'com.sportsnot.app',
    });
    expect(capturedMethod).toBe('POST');
    const parsed = JSON.parse(String(capturedBody));
    expect(parsed).toEqual({
      shareCode: 'SHARE',
      token: 'TOKEN',
      kind: 'activity',
      bundleId: 'com.sportsnot.app',
    });
    expect(capturedHeaders).toEqual({
      Accept: 'application/json',
      'Content-Type': 'text/plain',
    });
  });
});
