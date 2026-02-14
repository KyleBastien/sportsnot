import { describe, it, expect, afterEach } from '@rstest/core';
import { renderHook, cleanup, waitFor, act } from '@testing-library/react';
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useLeagues, useLeague, useCreateLeague, useJoinLeague } from './useLeague';
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
    return (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    );
  };
}

// Helper to create a mock chain for supabase.from().select().eq()... patterns
function mockSupabaseFrom(
  resolveWith: { data?: unknown; error?: unknown; count?: number | null }
) {
  const chainMethods: Record<string, unknown> = {};
  const chain = new Proxy(chainMethods, {
    get(_target, prop) {
      if (prop === 'then') {
        // Make it thenable to resolve the final value
        return (
          resolve: (val: unknown) => void,
          reject: (val: unknown) => void
        ) => {
          if (resolveWith.error) {
            // For queries, errors are thrown by the hook
            // Return { data: null, error } to let the hook handle it
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
      // All other methods return the chain itself
      return () => chain;
    },
  });
  return chain;
}

const mockLeagueMembers = [
  {
    id: 'member-1',
    team_name: 'Test Team',
    total_points: 42,
    leagues: {
      id: 'league-1',
      name: 'Test League',
      status: 'active',
      current_round: 3,
      max_participants: 8,
      commissioner_id: 'user-123',
      invite_code: 'ABC123',
    },
  },
  {
    id: 'member-2',
    team_name: 'Another Team',
    total_points: 38,
    leagues: {
      id: 'league-2',
      name: 'Second League',
      status: 'draft',
      current_round: 1,
      max_participants: 10,
      commissioner_id: 'user-456',
      invite_code: 'DEF456',
    },
  },
];

const mockLeague = {
  id: 'league-1',
  name: 'Test League',
  status: 'active',
  current_round: 3,
  max_participants: 8,
  commissioner_id: 'user-123',
  invite_code: 'ABC123',
  league_members: [
    {
      id: 'member-1',
      user_id: 'user-123',
      team_name: 'Test Team',
      total_points: 42,
      users: { display_name: 'TestUser', avatar_url: null },
    },
  ],
};

// Save and restore supabase.from
const originalFrom = supabase.from.bind(supabase);

afterEach(() => {
  supabase.from = originalFrom;
});

describe('useLeagues', () => {
  it('returns empty array when userId is undefined', async () => {
    const { result } = renderHook(() => useLeagues(undefined), {
      wrapper: createWrapper(),
    });

    // With undefined userId, enabled is false, so it stays idle
    expect(result.current.data).toBeUndefined();
    expect(result.current.isFetching).toBe(false);
  });

  it('fetches leagues for a user', async () => {
    supabase.from = (() =>
      mockSupabaseFrom({ data: mockLeagueMembers })) as typeof supabase.from;

    const { result } = renderHook(() => useLeagues('user-123'), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data).toHaveLength(2);
    expect(result.current.data![0].team_name).toBe('Test Team');
    expect(result.current.data![1].leagues.name).toBe('Second League');
  });

  it('handles error when fetching leagues', async () => {
    supabase.from = (() =>
      mockSupabaseFrom({
        error: { message: 'Database error', code: '500' },
      })) as typeof supabase.from;

    const { result } = renderHook(() => useLeagues('user-123'), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });

    expect(result.current.error).toBeTruthy();
  });

  it('returns empty array when user has no leagues', async () => {
    supabase.from = (() =>
      mockSupabaseFrom({ data: [] })) as typeof supabase.from;

    const { result } = renderHook(() => useLeagues('user-123'), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data).toHaveLength(0);
  });

  it('shows loading state initially', () => {
    supabase.from = (() =>
      mockSupabaseFrom({ data: mockLeagueMembers })) as typeof supabase.from;

    const { result } = renderHook(() => useLeagues('user-123'), {
      wrapper: createWrapper(),
    });

    // Initially loading (before query resolves)
    expect(result.current.isLoading).toBe(true);
  });

  it('returns null data when query returns null', async () => {
    supabase.from = (() =>
      mockSupabaseFrom({ data: null })) as typeof supabase.from;

    const { result } = renderHook(() => useLeagues('user-123'), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    // queryFn returns data ?? [] so null becomes []
    expect(result.current.data).toEqual([]);
  });
});

describe('useLeague', () => {
  it('does not fetch when leagueId is undefined', () => {
    const { result } = renderHook(() => useLeague(undefined), {
      wrapper: createWrapper(),
    });

    expect(result.current.data).toBeUndefined();
    expect(result.current.isFetching).toBe(false);
  });

  it('fetches a single league with members', async () => {
    supabase.from = (() =>
      mockSupabaseFrom({ data: mockLeague })) as typeof supabase.from;

    const { result } = renderHook(() => useLeague('league-1'), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data?.name).toBe('Test League');
    expect(result.current.data?.league_members).toHaveLength(1);
    expect(result.current.data?.league_members[0].team_name).toBe('Test Team');
  });

  it('handles error when fetching league', async () => {
    supabase.from = (() =>
      mockSupabaseFrom({
        error: { message: 'Not found', code: '404' },
      })) as typeof supabase.from;

    const { result } = renderHook(() => useLeague('nonexistent'), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });

    expect(result.current.error).toBeTruthy();
  });

  it('shows loading state while fetching', () => {
    supabase.from = (() =>
      mockSupabaseFrom({ data: mockLeague })) as typeof supabase.from;

    const { result } = renderHook(() => useLeague('league-1'), {
      wrapper: createWrapper(),
    });

    expect(result.current.isLoading).toBe(true);
  });
});

describe('useCreateLeague', () => {
  it('creates a league and returns the data', async () => {
    const createdLeague = { id: 'new-league', name: 'My League' };
    let fromCallCount = 0;

    supabase.from = ((table: string) => {
      fromCallCount++;
      if (table === 'leagues') {
        // insert().select().single() chain for leagues
        return mockSupabaseFrom({ data: createdLeague });
      }
      // league_members insert
      return mockSupabaseFrom({ data: null });
    }) as typeof supabase.from;

    const qc = createTestQueryClient();
    const { result } = renderHook(() => useCreateLeague(), {
      wrapper: createWrapper(qc),
    });

    await act(async () => {
      result.current.mutate({
        name: 'My League',
        maxParticipants: 8,
        inviteCode: 'XYZ789',
        commissionerId: 'user-123',
      });
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data?.name).toBe('My League');
  });

  it('throws on league creation error', async () => {
    supabase.from = (() =>
      mockSupabaseFrom({
        error: { message: 'Insert failed', code: '500' },
      })) as typeof supabase.from;

    const { result } = renderHook(() => useCreateLeague(), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      result.current.mutate({
        name: 'My League',
        maxParticipants: 8,
        inviteCode: 'XYZ',
        commissionerId: 'user-123',
      });
    });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
  });
});

describe('useJoinLeague', () => {
  it('joins a league successfully', async () => {
    const foundLeague = { id: 'league-1', name: 'Test League', max_participants: 8 };

    supabase.from = ((table: string) => {
      if (table === 'leagues') {
        return mockSupabaseFrom({ data: foundLeague });
      }
      // league_members - both count check and insert
      return mockSupabaseFrom({ data: null, count: 3 });
    }) as typeof supabase.from;

    const { result } = renderHook(() => useJoinLeague(), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      result.current.mutate({
        inviteCode: 'ABC123',
        userId: 'user-456',
        teamName: 'New Team',
      });
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data?.name).toBe('Test League');
  });

  it('throws error for invalid invite code', async () => {
    supabase.from = (() =>
      mockSupabaseFrom({
        error: { message: 'No rows', code: 'PGRST116' },
      })) as typeof supabase.from;

    const { result } = renderHook(() => useJoinLeague(), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      result.current.mutate({
        inviteCode: 'INVALID',
        userId: 'user-456',
        teamName: 'New Team',
      });
    });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
  });
});
