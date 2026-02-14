import { describe, it, expect, afterEach } from '@rstest/core';
import { renderHook, cleanup, waitFor, act } from '@testing-library/react';
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useDraft, useMakePick, useStartDraft } from './useDraft';
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
const originalChannel = supabase.channel.bind(supabase);
const originalRemoveChannel = supabase.removeChannel.bind(supabase);

afterEach(() => {
  supabase.from = originalFrom;
  supabase.channel = originalChannel;
  supabase.removeChannel = originalRemoveChannel;
});

// Mock channel that does nothing
function mockChannel() {
  const channelObj: Record<string, unknown> = {};
  const proxy = new Proxy(channelObj, {
    get(_target, prop) {
      if (prop === 'subscribe') return () => proxy;
      if (prop === 'on') return () => proxy;
      return () => proxy;
    },
  });
  supabase.channel = (() => proxy) as unknown as typeof supabase.channel;
  supabase.removeChannel = (() =>
    Promise.resolve('ok')) as unknown as typeof supabase.removeChannel;
}

const mockDraftData = {
  id: 'draft-1',
  league_id: 'league-1',
  round: 2,
  status: 'active',
  current_pick: 5,
  draft_order: ['member-1', 'member-2'],
  started_at: '2026-01-01T00:00:00Z',
  draft_picks: [
    {
      id: 'pick-1',
      draft_id: 'draft-1',
      pick_number: 1,
      player_id: 101,
      position: 'C',
      league_members: { team_name: 'Team A', user_id: 'user-1' },
    },
  ],
};

describe('useDraft', () => {
  it('does not fetch when leagueId is undefined', () => {
    mockChannel();
    const { result } = renderHook(() => useDraft(undefined), {
      wrapper: createWrapper(),
    });

    expect(result.current.data).toBeUndefined();
    expect(result.current.isFetching).toBe(false);
  });

  it('fetches draft data for a league', async () => {
    mockChannel();
    supabase.from = (() =>
      mockSupabaseFrom({ data: mockDraftData })) as typeof supabase.from;

    const { result } = renderHook(() => useDraft('league-1'), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data?.id).toBe('draft-1');
    expect(result.current.data?.status).toBe('active');
    expect(result.current.data?.draft_picks).toHaveLength(1);
  });

  it('returns null when no draft exists (PGRST116 error)', async () => {
    mockChannel();
    supabase.from = (() =>
      mockSupabaseFrom({
        data: null,
        error: { message: 'No rows', code: 'PGRST116' },
      })) as typeof supabase.from;

    const { result } = renderHook(() => useDraft('league-1'), {
      wrapper: createWrapper(),
    });

    // PGRST116 is handled gracefully - returns null
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data).toBeNull();
  });

  it('handles error when fetching draft', async () => {
    mockChannel();
    supabase.from = (() =>
      mockSupabaseFrom({
        error: { message: 'Database error', code: '500' },
      })) as typeof supabase.from;

    const { result } = renderHook(() => useDraft('league-1'), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });

    expect(result.current.error).toBeTruthy();
  });

  it('shows loading state while fetching', () => {
    mockChannel();
    supabase.from = (() =>
      mockSupabaseFrom({ data: mockDraftData })) as typeof supabase.from;

    const { result } = renderHook(() => useDraft('league-1'), {
      wrapper: createWrapper(),
    });

    expect(result.current.isLoading).toBe(true);
  });

  it('sets up realtime channel subscription', () => {
    let channelCreated = false;
    const channelObj: Record<string, unknown> = {};
    const proxy = new Proxy(channelObj, {
      get(_target, prop) {
        if (prop === 'subscribe') return () => proxy;
        if (prop === 'on') return () => proxy;
        return () => proxy;
      },
    });
    supabase.channel = ((_name: string) => {
      channelCreated = true;
      return proxy;
    }) as unknown as typeof supabase.channel;
    supabase.removeChannel = (() =>
      Promise.resolve('ok')) as unknown as typeof supabase.removeChannel;
    supabase.from = (() =>
      mockSupabaseFrom({ data: mockDraftData })) as typeof supabase.from;

    renderHook(() => useDraft('league-1'), {
      wrapper: createWrapper(),
    });

    expect(channelCreated).toBe(true);
  });

  it('cleans up channel on unmount', () => {
    let removeChannelCalled = false;
    const channelObj: Record<string, unknown> = {};
    const proxy = new Proxy(channelObj, {
      get(_target, prop) {
        if (prop === 'subscribe') return () => proxy;
        if (prop === 'on') return () => proxy;
        return () => proxy;
      },
    });
    supabase.channel = (() => proxy) as unknown as typeof supabase.channel;
    supabase.removeChannel = (() => {
      removeChannelCalled = true;
      return Promise.resolve('ok');
    }) as unknown as typeof supabase.removeChannel;
    supabase.from = (() =>
      mockSupabaseFrom({ data: mockDraftData })) as typeof supabase.from;

    const { unmount } = renderHook(() => useDraft('league-1'), {
      wrapper: createWrapper(),
    });

    unmount();
    expect(removeChannelCalled).toBe(true);
  });
});

describe('useMakePick', () => {
  it('makes a pick and advances the draft', async () => {
    mockChannel();
    let insertCalled = false;
    let updateCalled = false;
    let _callCount = 0;

    supabase.from = ((table: string) => {
      _callCount++;
      if (table === 'draft_picks') {
        insertCalled = true;
        return mockSupabaseFrom({ data: null });
      }
      if (table === 'drafts') {
        updateCalled = true;
        return mockSupabaseFrom({ data: null });
      }
      return mockSupabaseFrom({ data: null });
    }) as typeof supabase.from;

    const { result } = renderHook(() => useMakePick(), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      result.current.mutate({
        draftId: 'draft-1',
        leagueMemberId: 'member-1',
        pickNumber: 5,
        playerId: 101,
        teamId: 10,
        position: 'C',
      });
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(insertCalled).toBe(true);
    expect(updateCalled).toBe(true);
  });

  it('throws error when draft_picks insert fails', async () => {
    mockChannel();
    supabase.from = ((table: string) => {
      if (table === 'draft_picks') {
        return mockSupabaseFrom({
          error: { message: 'Insert failed', code: '500' },
        });
      }
      return mockSupabaseFrom({ data: null });
    }) as typeof supabase.from;

    const { result } = renderHook(() => useMakePick(), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      result.current.mutate({
        draftId: 'draft-1',
        leagueMemberId: 'member-1',
        pickNumber: 5,
        playerId: 101,
        teamId: 10,
        position: 'C',
      });
    });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
  });

  it('throws error when draft advance fails', async () => {
    mockChannel();
    supabase.from = ((table: string) => {
      if (table === 'draft_picks') {
        return mockSupabaseFrom({ data: null });
      }
      if (table === 'drafts') {
        return mockSupabaseFrom({
          error: { message: 'Update failed', code: '500' },
        });
      }
      return mockSupabaseFrom({ data: null });
    }) as typeof supabase.from;

    const { result } = renderHook(() => useMakePick(), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      result.current.mutate({
        draftId: 'draft-1',
        leagueMemberId: 'member-1',
        pickNumber: 5,
        playerId: 101,
        teamId: 10,
        position: 'C',
      });
    });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
  });

  it('supports null playerId and teamId', async () => {
    mockChannel();
    supabase.from = (() =>
      mockSupabaseFrom({ data: null })) as typeof supabase.from;

    const { result } = renderHook(() => useMakePick(), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      result.current.mutate({
        draftId: 'draft-1',
        leagueMemberId: 'member-1',
        pickNumber: 1,
        playerId: null,
        teamId: null,
        position: 'BN',
      });
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
  });
});

describe('useStartDraft', () => {
  it('starts a draft and updates league status', async () => {
    mockChannel();
    const newDraft = {
      id: 'draft-new',
      league_id: 'league-1',
      round: 1,
      status: 'active',
      current_pick: 1,
    };

    supabase.from = ((table: string) => {
      if (table === 'drafts') {
        return mockSupabaseFrom({ data: newDraft });
      }
      if (table === 'leagues') {
        return mockSupabaseFrom({ data: null });
      }
      return mockSupabaseFrom({ data: null });
    }) as typeof supabase.from;

    const { result } = renderHook(() => useStartDraft(), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      result.current.mutate({
        leagueId: 'league-1',
        round: 1,
        draftOrder: ['member-1', 'member-2'],
      });
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data?.id).toBe('draft-new');
  });

  it('throws error when draft creation fails', async () => {
    mockChannel();
    supabase.from = (() =>
      mockSupabaseFrom({
        error: { message: 'Insert failed', code: '500' },
      })) as typeof supabase.from;

    const { result } = renderHook(() => useStartDraft(), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      result.current.mutate({
        leagueId: 'league-1',
        round: 1,
        draftOrder: ['member-1'],
      });
    });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
  });
});
