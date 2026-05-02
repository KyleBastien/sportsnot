import { afterEach, beforeEach, describe, expect, it, rs } from '@rstest/core';
import { cleanup, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import type { User } from '@supabase/supabase-js';
import { renderWithAuth } from '../../../test-utils/renderWithAuth';

interface MockHookResult<T> {
  data: T | null;
  isLoading: boolean;
}

const draftState = rs.hoisted(() => ({
  draft: { data: null as unknown, isLoading: true } as MockHookResult<unknown>,
  members: {
    data: null as unknown,
    isLoading: true,
  } as MockHookResult<unknown>,
  leagueInfo: {
    data: null as unknown,
    isLoading: true,
  } as MockHookResult<unknown>,
  playerStats: {
    data: null as unknown,
    isLoading: true,
  } as MockHookResult<unknown>,
  teamStats: {
    data: null as unknown,
    isLoading: true,
  } as MockHookResult<unknown>,
  regSeasonStats: { data: [], isLoading: false } as MockHookResult<unknown>,
}));

rs.mock('./draftPageQueries', () => ({
  useDraft: () => draftState.draft,
  useLeagueMembers: () => draftState.members,
  useLeagueInfo: () => draftState.leagueInfo,
  usePlayoffPlayersForDraft: () => draftState.playerStats,
  usePlayoffTeamsForDraft: () => draftState.teamStats,
  useRegularSeasonPlayersForDraft: () => draftState.regSeasonStats,
}));

rs.mock('../../../mock/hooks/useMockLeagues', () => ({
  useMockLeague: () => ({ data: null, isLoading: false }),
}));

rs.mock('../../../mock/hooks/useMockDraft', () => ({
  useMockMakePick: () => ({ mutate: () => undefined }),
}));

import { DraftPage } from './DraftPage';

const mockUser = {
  id: 'user-1',
  email: 'me@example.com',
} as unknown as User;

const mockCommissioner = {
  id: 'commish-1',
  email: 'commish@example.com',
} as unknown as User;

function buildDraft(overrides: Record<string, unknown> = {}) {
  return {
    id: 'draft-1',
    league_id: 'league-1',
    round: 2,
    status: 'active',
    current_pick: 1,
    draft_order: ['user-1', 'user-2'],
    draft_picks: [],
    ...overrides,
  };
}

function buildMembers() {
  return [
    {
      id: 'lm-1',
      user_id: 'user-1',
      team_name: 'Alpha',
      total_points: 0,
      users: { display_name: 'Me' },
    },
    {
      id: 'lm-2',
      user_id: 'user-2',
      team_name: 'Bravo',
      total_points: 0,
      users: { display_name: 'You' },
    },
  ];
}

function buildPlayerStats() {
  return [
    {
      player_id: 100,
      player_name: 'Connor McDavid',
      position: 'F',
      team_abbreviation: 'EDM',
      is_injured: false,
      goals: 5,
      assists: 4,
      games_played: 7,
    },
  ];
}

function renderHarness(authUser: User = mockUser) {
  return renderWithAuth(<DraftPage />, {
    auth: { user: authUser },
    routerWrapper: (children: ReactNode) => (
      <MemoryRouter initialEntries={['/draft/league-1']}>
        <Routes>
          <Route path="/draft/:leagueId" element={children} />
        </Routes>
      </MemoryRouter>
    ),
  });
}

beforeEach(() => {
  draftState.draft = {
    data: buildDraft(),
    isLoading: false,
  };
  draftState.members = { data: buildMembers(), isLoading: false };
  draftState.leagueInfo = {
    data: { commissionerId: 'commish-1', allowIrSlots: true },
    isLoading: false,
  };
  draftState.playerStats = { data: buildPlayerStats(), isLoading: false };
  draftState.teamStats = { data: [], isLoading: false };
  draftState.regSeasonStats = { data: [], isLoading: false };
});

afterEach(() => {
  cleanup();
});

describe('DraftPage', () => {
  it('shows page loader (no Draft button, no empty alert) while members query is loading', () => {
    draftState.members = { data: null, isLoading: true };

    renderHarness();

    expect(screen.queryByRole('button', { name: /^Draft$/ })).toBeNull();
    expect(screen.queryByText(/No player data available yet/i)).toBeNull();
  });

  it('shows page loader while leagueInfo query is loading', () => {
    draftState.leagueInfo = { data: null, isLoading: true };

    renderHarness();

    expect(screen.queryByRole('button', { name: /^Draft$/ })).toBeNull();
    expect(screen.queryByText(/No player data available yet/i)).toBeNull();
  });

  it('shows page loader while playerStats query is loading', () => {
    draftState.playerStats = { data: null, isLoading: true };

    renderHarness();

    expect(screen.queryByRole('button', { name: /^Draft$/ })).toBeNull();
    expect(screen.queryByText(/No player data available yet/i)).toBeNull();
  });

  it('shows page loader while teamStats query is loading', () => {
    draftState.teamStats = { data: null, isLoading: true };

    renderHarness();

    expect(screen.queryByRole('button', { name: /^Draft$/ })).toBeNull();
    expect(screen.queryByText(/No player data available yet/i)).toBeNull();
  });

  it('shows the No-player-data alert only when all queries resolved with empty stats', () => {
    draftState.playerStats = { data: [], isLoading: false };
    draftState.teamStats = { data: [], isLoading: false };

    renderHarness();

    expect(screen.getByText(/No player data available yet/i)).toBeTruthy();
  });

  it('renders a Draft button on the first row when it is the user turn', () => {
    renderHarness();

    const draftButtons = screen.getAllByRole('button', { name: /^Draft$/ });
    expect(draftButtons.length).toBeGreaterThan(0);
  });

  it('shows Picking-for badge and Draft buttons when commissioner views another players pick', () => {
    renderHarness(mockCommissioner);

    expect(screen.getByText(/Picking for:/i)).toBeTruthy();
    const draftButtons = screen.getAllByRole('button', { name: /^Draft$/ });
    expect(draftButtons.length).toBeGreaterThan(0);
  });
});
