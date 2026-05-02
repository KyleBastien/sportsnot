import { afterEach, beforeEach, describe, expect, it, rs } from '@rstest/core';
import { cleanup, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import type { User } from '@supabase/supabase-js';
import { renderWithAuth } from '../../../test-utils/renderWithAuth';

interface MockHookResult {
  data: unknown;
  isLoading: boolean;
}

const transitionState = rs.hoisted(() => ({
  league: { data: null, isLoading: true } as MockHookResult,
  completedDrafts: { data: null, isLoading: true } as MockHookResult,
}));

rs.mock('./roundTransitionQueries', () => ({
  useTransitionLeague: () => transitionState.league,
  useCompletedDrafts: () => transitionState.completedDrafts,
}));

import { RoundTransitionPage } from './RoundTransitionPage';

const mockCommissioner = {
  id: 'commish-1',
  email: 'commish@example.com',
} as unknown as User;

function buildLeague(overrides: Record<string, unknown> = {}) {
  return {
    id: 'league-1',
    name: 'Test League',
    commissioner_id: mockCommissioner.id,
    current_round: 2,
    league_members: [
      {
        id: 'lm-1',
        user_id: mockCommissioner.id,
        team_name: 'Alpha',
        total_points: 100,
        users: { display_name: 'Commish' },
      },
      {
        id: 'lm-2',
        user_id: 'user-2',
        team_name: 'Bravo',
        total_points: 60,
        users: { display_name: 'Player Two' },
      },
    ],
    ...overrides,
  };
}

function renderHarness() {
  return renderWithAuth(<RoundTransitionPage />, {
    auth: { user: mockCommissioner },
    routerWrapper: (children: ReactNode) => (
      <MemoryRouter initialEntries={['/leagues/league-1/transition']}>
        <Routes>
          <Route path="/leagues/:leagueId/transition" element={children} />
        </Routes>
      </MemoryRouter>
    ),
  });
}

beforeEach(() => {
  transitionState.league = { data: null, isLoading: true };
  transitionState.completedDrafts = { data: null, isLoading: true };
});

afterEach(() => {
  cleanup();
});

describe('RoundTransitionPage', () => {
  it('hides Start Re-Draft button while league query is loading', () => {
    transitionState.league = { data: null, isLoading: true };
    transitionState.completedDrafts = { data: [], isLoading: false };

    renderHarness();

    expect(
      screen.queryByRole('button', { name: /Start Round .* Re-Draft/i })
    ).toBeNull();
  });

  it('hides Start Re-Draft button while completedDrafts query is loading', () => {
    transitionState.league = { data: buildLeague(), isLoading: false };
    transitionState.completedDrafts = { data: null, isLoading: true };

    renderHarness();

    expect(
      screen.queryByRole('button', { name: /Start Round .* Re-Draft/i })
    ).toBeNull();
  });

  it('renders Start Round 3 Re-Draft button after both queries resolve with one completed draft', () => {
    transitionState.league = {
      data: buildLeague({ current_round: 2 }),
      isLoading: false,
    };
    transitionState.completedDrafts = {
      data: [
        { id: 'd1', round: 2, status: 'completed', completed_at: '2025-04-22' },
      ],
      isLoading: false,
    };

    renderHarness();

    const button = screen.getByRole('button', {
      name: /Start Round .* Re-Draft/i,
    });
    expect(button.textContent).toContain('Start Round 3 Re-Draft');
  });
});
