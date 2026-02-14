import { describe, it, expect, afterEach } from '@rstest/core';
import { renderHook, cleanup, waitFor, act } from '@testing-library/react';
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useRoster, useLeagueRosters, useActivateIR } from './useRoster';
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
          if (resolveWith.error) {
            resolve({
              data: resolveWith.data ?? null,
              error: resolveWith.error,
              count: resolveWith.count ?? null,
            });
          } else {
            resolve({
              data: resolveWith.data ?? null,
              error: null,
              count: resolveWith.count ?? null,
            });
          }
        };
      }
      return () => chain;
    },
  });
  return chain;
}

// Save originals
const originalFrom = supabase.from.bind(supabase);
const originalRpc = supabase.rpc.bind(supabase);

afterEach(() => {
  supabase.from = originalFrom;
  supabase.rpc = originalRpc;
});

const mockRosterData = [
  {
    id: 'roster-1',
    league_member_id: 'member-1',
    round: 2,
    player_id: 101,
    team_id: 10,
    position: 'C',
    is_active: true,
  },
  {
    id: 'roster-2',
    league_member_id: 'member-1',
    round: 2,
    player_id: 102,
    team_id: 11,
    position: 'LW',
    is_active: true,
  },
];

describe('useRoster', () => {
  it('does not fetch when leagueMemberId is undefined', () => {
    const { result } = renderHook(() => useRoster(undefined, 1), {
      wrapper: createWrapper(),
    });

    expect(result.current.data).toBeUndefined();
    expect(result.current.isFetching).toBe(false);
  });

  it('fetches roster data for a league member and round', async () => {
    supabase.from = (() =>
      mockSupabaseFrom({ data: mockRosterData })) as typeof supabase.from;

    const { result } = renderHook(() => useRoster('member-1', 2), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data).toHaveLength(2);
    expect(result.current.data![0].position).toBe('C');
    expect(result.current.data![1].position).toBe('LW');
  });

  it('returns empty array when roster has no entries', async () => {
    supabase.from = (() =>
      mockSupabaseFrom({ data: [] })) as typeof supabase.from;

    const { result } = renderHook(() => useRoster('member-1', 2), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data).toEqual([]);
  });

  it('returns empty array when data is null', async () => {
    supabase.from = (() =>
      mockSupabaseFrom({ data: null })) as typeof supabase.from;

    const { result } = renderHook(() => useRoster('member-1', 2), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data).toEqual([]);
  });

  it('handles error when fetching roster', async () => {
    supabase.from = (() =>
      mockSupabaseFrom({
        error: { message: 'Database error', code: '500' },
      })) as typeof supabase.from;

    const { result } = renderHook(() => useRoster('member-1', 2), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });

    expect(result.current.error).toBeTruthy();
  });

  it('shows loading state while fetching', () => {
    supabase.from = (() =>
      mockSupabaseFrom({ data: mockRosterData })) as typeof supabase.from;

    const { result } = renderHook(() => useRoster('member-1', 2), {
      wrapper: createWrapper(),
    });

    expect(result.current.isLoading).toBe(true);
  });
});

describe('useLeagueRosters', () => {
  it('does not fetch when leagueId is undefined', () => {
    const { result } = renderHook(() => useLeagueRosters(undefined, 1), {
      wrapper: createWrapper(),
    });

    expect(result.current.data).toBeUndefined();
    expect(result.current.isFetching).toBe(false);
  });

  it('fetches rosters for all league members', async () => {
    const leagueRosters = [
      {
        ...mockRosterData[0],
        league_members: { user_id: 'user-1', team_name: 'Team A' },
      },
      {
        ...mockRosterData[1],
        league_members: { user_id: 'user-2', team_name: 'Team B' },
      },
    ];

    supabase.from = ((table: string) => {
      if (table === 'league_members') {
        return mockSupabaseFrom({
          data: [{ id: 'member-1' }, { id: 'member-2' }],
        });
      }
      if (table === 'rosters') {
        return mockSupabaseFrom({ data: leagueRosters });
      }
      return mockSupabaseFrom({ data: null });
    }) as typeof supabase.from;

    const { result } = renderHook(() => useLeagueRosters('league-1', 2), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data).toHaveLength(2);
  });

  it('returns empty array when no members found', async () => {
    supabase.from = ((table: string) => {
      if (table === 'league_members') {
        return mockSupabaseFrom({ data: [] });
      }
      return mockSupabaseFrom({ data: [] });
    }) as typeof supabase.from;

    const { result } = renderHook(() => useLeagueRosters('league-1', 1), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data).toEqual([]);
  });

  it('handles error when fetching league rosters', async () => {
    supabase.from = ((table: string) => {
      if (table === 'league_members') {
        return mockSupabaseFrom({ data: [{ id: 'member-1' }] });
      }
      return mockSupabaseFrom({
        error: { message: 'Query failed', code: '500' },
      });
    }) as typeof supabase.from;

    const { result } = renderHook(() => useLeagueRosters('league-1', 1), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
  });
});

describe('useActivateIR', () => {
  it('calls rpc to activate IR player', async () => {
    let rpcCalled = false;
    let rpcParams: Record<string, unknown> = {};

    supabase.rpc = ((funcName: string, params: Record<string, unknown>) => {
      rpcCalled = true;
      rpcParams = params;
      return Promise.resolve({ data: null, error: null }) as unknown;
    }) as unknown as typeof supabase.rpc;

    const { result } = renderHook(() => useActivateIR(), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      result.current.mutate({
        leagueMemberId: 'member-1',
        round: 2,
        injuredSlotId: 'roster-1',
        irSlotId: 'roster-2',
      });
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(rpcCalled).toBe(true);
    expect(rpcParams.p_league_member_id).toBe('member-1');
    expect(rpcParams.p_round).toBe(2);
    expect(rpcParams.p_injured_roster_id).toBe('roster-1');
    expect(rpcParams.p_ir_roster_id).toBe('roster-2');
  });

  it('handles error from rpc call', async () => {
    supabase.rpc = (() =>
      Promise.resolve({
        data: null,
        error: { message: 'RPC failed', code: '500' },
      })) as unknown as typeof supabase.rpc;

    const { result } = renderHook(() => useActivateIR(), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      result.current.mutate({
        leagueMemberId: 'member-1',
        round: 2,
        injuredSlotId: 'roster-1',
        irSlotId: 'roster-2',
      });
    });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
  });
});
