import { describe, it, expect, afterEach } from '@rstest/core';
import { renderHook, cleanup, waitFor, act } from '@testing-library/react';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useStatSync } from './useStatSync';
import { supabase } from '../supabase';

afterEach(cleanup);

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
        refetchOnMount: false,
        refetchInterval: false,
        refetchOnWindowFocus: false,
      },
      mutations: {
        retry: false,
      },
    },
  });
}

function createWrapper(queryClient?: QueryClient) {
  const qc = queryClient ?? createTestQueryClient();
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

// Proxy-based mock for supabase.from() chain
function mockSupabaseFrom(resolveWith: {
  data?: unknown;
  error?: unknown;
  count?: number | null;
}) {
  const chainMethods: Record<string, unknown> = {};
  const chain = new Proxy(chainMethods, {
    get(_target, prop) {
      if (prop === 'then') {
        return (
          resolve: (val: unknown) => void,
          _reject: (val: unknown) => void
        ) => {
          resolve({
            data: resolveWith.data ?? null,
            error: resolveWith.error ?? null,
            count: resolveWith.count ?? null,
          });
        };
      }
      return () => chain;
    },
  });
  return chain;
}

// Save originals
const originalFrom = supabase.from.bind(supabase);
const _originalFunctionsDescriptor = Object.getOwnPropertyDescriptor(
  Object.getPrototypeOf(supabase),
  'functions'
);
const originalFetch = globalThis.fetch;

afterEach(() => {
  supabase.from = originalFrom;
  // Restore the functions getter: remove any instance override to fall back to prototype
  if (Object.getOwnPropertyDescriptor(supabase, 'functions')) {
    delete (supabase as unknown as Record<string, unknown>).functions;
  }
  globalThis.fetch = originalFetch;
  // Restore document.hidden
  Object.defineProperty(document, 'hidden', {
    configurable: true,
    get: () => false,
  });
});

// Helper to mock supabase.functions.invoke
function mockFunctionsInvoke(
  handler: (
    funcName: string,
    options?: unknown
  ) => Promise<{ data: unknown; error: unknown }>
) {
  Object.defineProperty(supabase, 'functions', {
    configurable: true,
    get: () => ({
      invoke: handler,
    }),
  });
}

// Mock fetch to control getScoresNow responses
function mockFetch(games: unknown[] = []) {
  globalThis.fetch = (() =>
    Promise.resolve({
      ok: true,
      json: () => Promise.resolve({ games }),
    })) as unknown as typeof fetch;
}

describe('useStatSync', () => {
  it('does not sync when leagueId is undefined', () => {
    mockFetch();
    const { result } = renderHook(() => useStatSync(undefined), {
      wrapper: createWrapper(),
    });

    expect(result.current.isSyncing).toBe(false);
    expect(result.current.lastSyncedAt).toBeNull();
    expect(result.current.isLive).toBe(false);
  });

  it('returns isLive false when no games are live', async () => {
    mockFetch([
      { gameState: 'OFF', id: 1 },
      { gameState: 'FINAL', id: 2 },
    ]);

    const { result } = renderHook(() => useStatSync('league-1'), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isLive).toBe(false);
    });
  });

  it('returns isLive true when games are live', async () => {
    mockFetch([
      { gameState: 'LIVE', id: 1 },
      { gameState: 'FINAL', id: 2 },
    ]);

    const { result } = renderHook(() => useStatSync('league-1'), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isLive).toBe(true);
    });
  });

  it('returns isLive true for PRE game state', async () => {
    mockFetch([{ gameState: 'PRE', id: 1 }]);

    const { result } = renderHook(() => useStatSync('league-1'), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isLive).toBe(true);
    });
  });

  it('pauses polling when tab is hidden', async () => {
    mockFetch([]);

    // Make tab hidden
    Object.defineProperty(document, 'hidden', {
      configurable: true,
      get: () => true,
    });

    const { result } = renderHook(() => useStatSync('league-1'), {
      wrapper: createWrapper(),
    });

    // When tab is hidden, query should not be fetching
    // The hook uses enabled: !!leagueId && isTabVisible
    // isTabVisible starts as !document.hidden which is false here
    expect(result.current.isSyncing).toBe(false);
  });

  it('syncNow triggers edge functions and updates lastSyncedAt', async () => {
    mockFetch([{ gameState: 'OFF', id: 1 }]);

    let playerSyncCalled = false;
    let teamSyncCalled = false;
    mockFunctionsInvoke((funcName: string) => {
      if (funcName === 'sync-player-stats') playerSyncCalled = true;
      if (funcName === 'sync-team-stats') teamSyncCalled = true;
      return Promise.resolve({ data: null, error: null });
    });

    // Mock supabase.from for member/roster queries
    supabase.from = ((table: string) => {
      if (table === 'league_members') {
        return mockSupabaseFrom({ data: [{ id: 'member-1' }] });
      }
      if (table === 'rosters') {
        return mockSupabaseFrom({
          data: [
            { player_id: 101, team_id: 10 },
            { player_id: 102, team_id: null },
          ],
        });
      }
      return mockSupabaseFrom({ data: null });
    }) as typeof supabase.from;

    const { result } = renderHook(() => useStatSync('league-1'), {
      wrapper: createWrapper(),
    });

    // Wait for initial query to settle before calling syncNow
    await waitFor(() => {
      expect(result.current.isSyncing).toBe(false);
    });

    // Manually call syncNow
    await act(async () => {
      await result.current.syncNow();
    });

    await waitFor(() => {
      expect(result.current.isSyncing).toBe(false);
    });

    expect(playerSyncCalled).toBe(true);
    expect(teamSyncCalled).toBe(true);
    expect(result.current.lastSyncedAt).toBeTruthy();
  });

  it('syncNow does nothing when leagueId is undefined', async () => {
    mockFetch([]);

    let functionsInvoked = false;
    mockFunctionsInvoke(() => {
      functionsInvoked = true;
      return Promise.resolve({ data: null, error: null });
    });

    const { result } = renderHook(() => useStatSync(undefined), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      await result.current.syncNow();
    });

    expect(functionsInvoked).toBe(false);
    expect(result.current.lastSyncedAt).toBeNull();
  });

  it('syncNow skips when no members found', async () => {
    mockFetch([]);

    supabase.from = ((table: string) => {
      if (table === 'league_members') {
        return mockSupabaseFrom({ data: [] });
      }
      return mockSupabaseFrom({ data: null });
    }) as typeof supabase.from;

    let functionsInvoked = false;
    mockFunctionsInvoke(() => {
      functionsInvoked = true;
      return Promise.resolve({ data: null, error: null });
    });

    const { result } = renderHook(() => useStatSync('league-1'), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      await result.current.syncNow();
    });

    expect(functionsInvoked).toBe(false);
  });

  it('syncNow skips when no rosters found', async () => {
    mockFetch([]);

    supabase.from = ((table: string) => {
      if (table === 'league_members') {
        return mockSupabaseFrom({ data: [{ id: 'member-1' }] });
      }
      if (table === 'rosters') {
        return mockSupabaseFrom({ data: [] });
      }
      return mockSupabaseFrom({ data: null });
    }) as typeof supabase.from;

    let functionsInvoked = false;
    mockFunctionsInvoke(() => {
      functionsInvoked = true;
      return Promise.resolve({ data: null, error: null });
    });

    const { result } = renderHook(() => useStatSync('league-1'), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      await result.current.syncNow();
    });

    expect(functionsInvoked).toBe(false);
  });

  it('syncNow only calls player sync when no teams on roster', async () => {
    mockFetch([]);

    let playerSyncCalled = false;
    let teamSyncCalled = false;
    mockFunctionsInvoke((funcName: string) => {
      if (funcName === 'sync-player-stats') playerSyncCalled = true;
      if (funcName === 'sync-team-stats') teamSyncCalled = true;
      return Promise.resolve({ data: null, error: null });
    });

    supabase.from = ((table: string) => {
      if (table === 'league_members') {
        return mockSupabaseFrom({ data: [{ id: 'member-1' }] });
      }
      if (table === 'rosters') {
        return mockSupabaseFrom({
          data: [{ player_id: 101, team_id: null }],
        });
      }
      return mockSupabaseFrom({ data: null });
    }) as typeof supabase.from;

    const { result } = renderHook(() => useStatSync('league-1'), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSyncing).toBe(false);
    });

    await act(async () => {
      await result.current.syncNow();
    });

    await waitFor(() => {
      expect(result.current.isSyncing).toBe(false);
    });

    expect(playerSyncCalled).toBe(true);
    expect(teamSyncCalled).toBe(false);
  });

  it('handles sync errors gracefully', async () => {
    mockFetch([]);

    supabase.from = ((table: string) => {
      if (table === 'league_members') {
        return mockSupabaseFrom({ data: [{ id: 'member-1' }] });
      }
      if (table === 'rosters') {
        return mockSupabaseFrom({
          data: [{ player_id: 101, team_id: 10 }],
        });
      }
      return mockSupabaseFrom({ data: null });
    }) as typeof supabase.from;

    mockFunctionsInvoke(() => {
      return Promise.reject(new Error('Network error'));
    });

    const { result } = renderHook(() => useStatSync('league-1'), {
      wrapper: createWrapper(),
    });

    // Should not throw
    await act(async () => {
      await result.current.syncNow();
    });

    // isSyncing should be reset to false after error
    expect(result.current.isSyncing).toBe(false);
  });
});
