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

const rosterState = rs.hoisted(() => ({
  roster: { data: null as unknown, isLoading: true } as MockHookResult<unknown>,
  league: {
    data: null as unknown,
    isLoading: false,
  } as MockHookResult<unknown>,
  playerStats: {
    data: null as unknown,
    isLoading: true,
  } as MockHookResult<unknown>,
  teamStats: { data: [], isLoading: false } as MockHookResult<unknown>,
  regSeasonStats: { data: [], isLoading: false } as MockHookResult<unknown>,
}));

rs.mock('./rosterPageQueries', () => ({
  useMemberRoster: () => rosterState.roster,
  useLeagueForRoster: () => rosterState.league,
  usePlayoffPlayersForRoster: () => rosterState.playerStats,
  usePlayoffTeamsForRoster: () => rosterState.teamStats,
  useRegularSeasonPlayersForRoster: () => rosterState.regSeasonStats,
}));

rs.mock('../../../mock/hooks/useMockRoster', () => ({
  useMockActivateIR: () => ({ mutate: () => undefined }),
}));

import { RosterPage } from './RosterPage';

const mockUser = {
  id: 'user-1',
  email: 'me@example.com',
} as unknown as User;

function buildRosterData() {
  return {
    memberId: 'lm-1',
    round: 2,
    totalPoints: 100,
    slots: [
      {
        id: 'slot-f-1',
        league_member_id: 'lm-1',
        round: 2,
        player_id: 100,
        team_id: null,
        position: 'F',
        is_active: true,
        points_earned: 5,
        activated_from_ir: false,
        is_eliminated: false,
      },
      {
        id: 'slot-irf-1',
        league_member_id: 'lm-1',
        round: 2,
        player_id: 200,
        team_id: null,
        position: 'IR_F',
        is_active: true,
        points_earned: 2,
        activated_from_ir: false,
        is_eliminated: false,
      },
    ],
  };
}

function buildLeague() {
  return {
    id: 'league-1',
    allow_ir_slots: true,
    league_members: [
      {
        id: 'lm-1',
        user_id: 'user-1',
        team_name: 'Alpha',
        users: { display_name: 'Me' },
      },
    ],
  };
}

function buildPlayerStatsWithInjured() {
  return [
    {
      player_id: 100,
      player_name: 'Injured Player',
      position: 'F',
      team_abbreviation: 'EDM',
      is_injured: true,
      goals: 0,
      assists: 0,
      games_played: 5,
    },
    {
      player_id: 200,
      player_name: 'IR Bench Player',
      position: 'F',
      team_abbreviation: 'BOS',
      is_injured: false,
      goals: 1,
      assists: 1,
      games_played: 5,
    },
  ];
}

function renderHarness() {
  return renderWithAuth(<RosterPage />, {
    auth: { user: mockUser },
    routerWrapper: (children: ReactNode) => (
      <MemoryRouter initialEntries={['/roster/league-1']}>
        <Routes>
          <Route path="/roster/:leagueId" element={children} />
        </Routes>
      </MemoryRouter>
    ),
  });
}

beforeEach(() => {
  rosterState.roster = { data: buildRosterData(), isLoading: false };
  rosterState.league = { data: buildLeague(), isLoading: false };
  rosterState.playerStats = {
    data: buildPlayerStatsWithInjured(),
    isLoading: false,
  };
  rosterState.teamStats = { data: [], isLoading: false };
  rosterState.regSeasonStats = { data: [], isLoading: false };
});

afterEach(() => {
  cleanup();
});

describe('RosterPage', () => {
  it('hides Activate IR button while playerStats is loading', () => {
    rosterState.playerStats = { data: null, isLoading: true };

    renderHarness();

    expect(screen.queryByRole('button', { name: /Activate IR/i })).toBeNull();
  });

  it('shows Activate IR button after playerStats resolves with injured candidate', () => {
    renderHarness();

    expect(screen.getByRole('button', { name: /Activate IR/i })).toBeTruthy();
  });
});
