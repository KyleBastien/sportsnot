import { afterEach, beforeEach, describe, expect, it, rs } from '@rstest/core';
import { cleanup, fireEvent, screen, waitFor } from '@testing-library/react';
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

const supabaseState = rs.hoisted(() => ({
  draftInsertPayload: null as Record<string, unknown> | null,
  leagueUpdatePayload: null as Record<string, unknown> | null,
  leagueUpdateId: null as string | null,
}));

rs.mock('./roundTransitionQueries', () => ({
  useTransitionLeague: () => transitionState.league,
}));

rs.mock('../../hooks/useCompletedDrafts', () => ({
  useCompletedDrafts: () => transitionState.completedDrafts,
}));

rs.mock('@sportsnot/supabase', () => ({
  supabase: {
    from: (table: string) => {
      if (table === 'drafts') {
        return {
          insert: async (payload: Record<string, unknown>) => {
            supabaseState.draftInsertPayload = payload;
            return { error: null };
          },
        };
      }

      if (table === 'leagues') {
        return {
          update: (payload: Record<string, unknown>) => {
            supabaseState.leagueUpdatePayload = payload;
            return {
              eq: async (_column: string, value: string) => {
                supabaseState.leagueUpdateId = value;
                return { error: null };
              },
            };
          },
        };
      }

      if (table === 'rosters') {
        return {
          select: () => ({
            eq: () => ({
              in: async () => ({
                data: [
                  { league_member_id: 'lm-1' },
                  { league_member_id: 'lm-2' },
                ],
                error: null,
              }),
            }),
          }),
          insert: async () => ({ error: null }),
        };
      }

      throw new Error(`Unexpected table: ${table}`);
    },
  },
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
    allow_ir_slots: true,
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
  supabaseState.draftInsertPayload = null;
  supabaseState.leagueUpdatePayload = null;
  supabaseState.leagueUpdateId = null;
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

  it('renders Advance to Round 4 button when next round is 4', () => {
    transitionState.league = {
      data: buildLeague({ current_round: 3 }),
      isLoading: false,
    };
    transitionState.completedDrafts = {
      data: [
        { id: 'd1', round: 1, status: 'completed', completed_at: '2025-04-22' },
        { id: 'd2', round: 2, status: 'completed', completed_at: '2025-04-22' },
        { id: 'd3', round: 3, status: 'completed', completed_at: '2025-04-22' },
      ],
      isLoading: false,
    };

    renderHarness();

    expect(
      screen.getByRole('button', { name: /Advance to Round 4/i })
    ).toBeTruthy();
  });

  it('creates a full snake re-draft order based on roster size', async () => {
    transitionState.league = {
      data: buildLeague({
        current_round: 1,
        league_members: [
          {
            id: 'lm-1',
            user_id: 'user-1',
            team_name: 'Alpha',
            total_points: 44,
            users: { display_name: 'Player One' },
          },
          {
            id: 'lm-2',
            user_id: 'user-2',
            team_name: 'Bravo',
            total_points: 45,
            users: { display_name: 'Player Two' },
          },
          {
            id: 'lm-3',
            user_id: 'user-3',
            team_name: 'Charlie',
            total_points: 50,
            users: { display_name: 'Player Three' },
          },
          {
            id: 'lm-4',
            user_id: 'user-4',
            team_name: 'Delta',
            total_points: 59,
            users: { display_name: 'Player Four' },
          },
        ],
      }),
      isLoading: false,
    };
    transitionState.completedDrafts = {
      data: [
        { id: 'd1', round: 1, status: 'completed', completed_at: '2025-04-22' },
      ],
      isLoading: false,
    };

    renderHarness();

    fireEvent.click(
      screen.getByRole('button', { name: /Start Round .* Re-Draft/i })
    );

    await waitFor(() => expect(supabaseState.draftInsertPayload).toBeTruthy());

    const draftOrder = supabaseState.draftInsertPayload
      ?.draft_order as string[];
    expect(draftOrder).toHaveLength(44);
    expect(draftOrder.slice(0, 8)).toEqual([
      'user-1',
      'user-2',
      'user-3',
      'user-4',
      'user-4',
      'user-3',
      'user-2',
      'user-1',
    ]);
    expect(supabaseState.leagueUpdatePayload).toEqual({
      status: 'drafting',
      current_round: 2,
    });
    expect(supabaseState.leagueUpdateId).toBe('league-1');
  });
});
