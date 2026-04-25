import { afterEach, beforeEach, describe, expect, it, rs } from '@rstest/core';
import { cleanup, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import type { User } from '@supabase/supabase-js';
import { renderWithAuth } from '../../../test-utils/renderWithAuth';

interface MockHookResult {
  data: unknown;
  isLoading: boolean;
}

const lobbyState = rs.hoisted(() => ({
  league: { data: null, isLoading: true } as MockHookResult,
  activeDraft: { data: null, isLoading: true } as MockHookResult,
}));

rs.mock('./draftLobbyQueries', () => ({
  useLeagueForLobby: () => lobbyState.league,
  useActiveDraftCheck: () => lobbyState.activeDraft,
}));

import { DraftLobbyPage } from './DraftLobbyPage';

const mockCommissioner = {
  id: 'commish-1',
  email: 'commish@example.com',
} as unknown as User;

function buildLeague(overrides: Record<string, unknown> = {}) {
  return {
    id: 'league-1',
    name: 'Test League',
    commissioner_id: mockCommissioner.id,
    current_round: 0,
    allow_ir_slots: true,
    status: 'pending',
    league_members: [
      {
        id: 'lm-1',
        user_id: mockCommissioner.id,
        team_name: 'Alpha',
        users: { display_name: 'Commish' },
      },
      {
        id: 'lm-2',
        user_id: 'user-2',
        team_name: 'Bravo',
        users: { display_name: 'Player Two' },
      },
    ],
    ...overrides,
  };
}

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="probe-location">{location.pathname}</div>;
}

function renderHarness() {
  return renderWithAuth(<DraftLobbyPage />, {
    auth: { user: mockCommissioner },
    routerWrapper: (children: ReactNode) => (
      <MemoryRouter initialEntries={['/draft-lobby/league-1']}>
        <Routes>
          <Route path="/draft-lobby/:leagueId" element={children} />
          <Route
            path="/draft/:leagueId"
            element={<div data-testid="active-draft-route">draft-page</div>}
          />
        </Routes>
        <LocationProbe />
      </MemoryRouter>
    ),
  });
}

beforeEach(() => {
  lobbyState.league = { data: null, isLoading: true };
  lobbyState.activeDraft = { data: null, isLoading: true };
});

afterEach(() => {
  cleanup();
});

describe('DraftLobbyPage', () => {
  it('hides Start Draft button while league query is loading', () => {
    lobbyState.league = { data: null, isLoading: true };
    lobbyState.activeDraft = { data: null, isLoading: false };

    renderHarness();

    expect(
      screen.queryByRole('button', { name: /Start Round .* Draft/i })
    ).toBeNull();
  });

  it('hides Start Draft button while activeDraft query is loading', () => {
    lobbyState.league = { data: buildLeague(), isLoading: false };
    lobbyState.activeDraft = { data: null, isLoading: true };

    renderHarness();

    expect(
      screen.queryByRole('button', { name: /Start Round .* Draft/i })
    ).toBeNull();
  });

  it('redirects to draft route when activeDraft.status is active', () => {
    lobbyState.league = { data: buildLeague(), isLoading: false };
    lobbyState.activeDraft = {
      data: { id: 'draft-1', status: 'active' },
      isLoading: false,
    };

    renderHarness();

    expect(
      screen.queryByRole('button', { name: /Start Round .* Draft/i })
    ).toBeNull();
    expect(screen.getByTestId('active-draft-route')).toBeTruthy();
    expect(screen.getByTestId('probe-location').textContent).toBe(
      '/draft/league-1'
    );
  });

  it('shows Start Round X Draft button for commissioner once both queries resolve with no active draft', () => {
    lobbyState.league = {
      data: buildLeague({ current_round: 1 }),
      isLoading: false,
    };
    lobbyState.activeDraft = { data: null, isLoading: false };

    renderHarness();

    expect(
      screen.getByRole('button', { name: /Start Round 2 Draft/i })
    ).toBeTruthy();
  });
});
