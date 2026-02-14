import { describe, it, expect, afterEach } from '@rstest/core';
import { render, screen, cleanup } from '@testing-library/react';
import { MantineProvider } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { RosterPage } from './RosterPage';
import { AuthProvider } from '../../context/AuthContext';
import { CompareProvider } from '../../context/CompareContext';

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
        enabled: false,
      },
    },
  });
}

function renderPage(queryClient?: QueryClient, leagueId = 'test-league-1') {
  const qc = queryClient ?? createTestQueryClient();
  return render(
    <MantineProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={[`/leagues/${leagueId}/roster`]}>
          <AuthProvider>
            <CompareProvider>
              <Routes>
                <Route
                  path="/leagues/:leagueId/roster"
                  element={<RosterPage />}
                />
              </Routes>
            </CompareProvider>
          </AuthProvider>
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>
  );
}

function makeRosterData(overrides: Record<string, unknown> = {}) {
  return {
    memberId: 'member-1',
    round: 2,
    slots: [],
    ...overrides,
  };
}

function makeSlot(overrides: Record<string, unknown> = {}) {
  return {
    id: 'slot-1',
    position: 'F',
    player_id: 101,
    team_id: null,
    is_active: true,
    points_earned: 5,
    activated_from_ir: false,
    ...overrides,
  };
}

describe('RosterPage', () => {
  it('shows error when user is not authenticated', () => {
    // useMyRoster has enabled: !!user, with no user it returns undefined data
    // which triggers the error state
    const qc = createTestQueryClient();
    renderPage(qc);
    expect(screen.getByText('Could not load your roster.')).toBeTruthy();
  });

  it('shows error alert when roster fails to load', () => {
    const qc = createTestQueryClient();
    // Set roster data to null to simulate error
    qc.setQueryData(['roster', 'test-league-1', undefined], null);
    renderPage(qc);
    expect(screen.getByText('Could not load your roster.')).toBeTruthy();
  });

  it('renders My Roster title when data is loaded', () => {
    const qc = createTestQueryClient();
    qc.setQueryData(['roster', 'test-league-1', undefined], makeRosterData());
    renderPage(qc);
    expect(screen.getByText('My Roster')).toBeTruthy();
  });

  it('shows round number', () => {
    const qc = createTestQueryClient();
    qc.setQueryData(
      ['roster', 'test-league-1', undefined],
      makeRosterData({ round: 3 })
    );
    renderPage(qc);
    expect(screen.getByText('Round 3')).toBeTruthy();
  });

  it('shows scoring rules text', () => {
    const qc = createTestQueryClient();
    qc.setQueryData(['roster', 'test-league-1', undefined], makeRosterData());
    renderPage(qc);
    expect(screen.getByText(/Goal = 1pt/)).toBeTruthy();
    expect(screen.getByText(/Assist = 1pt/)).toBeTruthy();
    expect(screen.getByText(/Win = 2pts/)).toBeTruthy();
    expect(screen.getByText(/Shutout = 4pts/)).toBeTruthy();
  });

  it('renders position group headers', () => {
    const qc = createTestQueryClient();
    qc.setQueryData(['roster', 'test-league-1', undefined], makeRosterData());
    renderPage(qc);
    expect(screen.getByText('Forward')).toBeTruthy();
    expect(screen.getByText('Defenseman')).toBeTruthy();
    expect(screen.getByText('Goalie')).toBeTruthy();
    expect(screen.getByText('IR Forward')).toBeTruthy();
    expect(screen.getByText('IR Defenseman')).toBeTruthy();
  });

  it('shows "No player drafted in this slot" for empty groups', () => {
    const qc = createTestQueryClient();
    qc.setQueryData(
      ['roster', 'test-league-1', undefined],
      makeRosterData({ slots: [] })
    );
    renderPage(qc);
    const emptyMessages = screen.getAllByText('No player drafted in this slot');
    // All 5 position groups should be empty
    expect(emptyMessages.length).toBe(5);
  });

  it('renders roster slots with player names from cached stats', () => {
    const qc = createTestQueryClient();
    const slots = [
      makeSlot({ id: 's1', position: 'F', player_id: 97, points_earned: 15 }),
      makeSlot({ id: 's2', position: 'D', player_id: 88, points_earned: 8 }),
    ];
    qc.setQueryData(
      ['roster', 'test-league-1', undefined],
      makeRosterData({ slots })
    );
    qc.setQueryData(
      ['playoff-players', '20242025', 2],
      [
        {
          player_id: 97,
          player_name: 'Connor McDavid',
          position: 'F',
          team_abbreviation: 'EDM',
          goals: 10,
          assists: 15,
          games_played: 8,
        },
        {
          player_id: 88,
          player_name: 'Cale Makar',
          position: 'D',
          team_abbreviation: 'COL',
          goals: 3,
          assists: 12,
          games_played: 8,
        },
      ]
    );
    qc.setQueryData(['playoff-teams', '20242025', 2], []);
    renderPage(qc);
    expect(screen.getByText('Connor McDavid')).toBeTruthy();
    expect(screen.getByText('Cale Makar')).toBeTruthy();
  });

  it('shows total points card', () => {
    const qc = createTestQueryClient();
    const slots = [
      makeSlot({ id: 's1', position: 'F', is_active: true, points_earned: 10 }),
      makeSlot({ id: 's2', position: 'D', is_active: true, points_earned: 5 }),
      makeSlot({ id: 's3', position: 'G', is_active: false, points_earned: 3 }),
    ];
    qc.setQueryData(
      ['roster', 'test-league-1', undefined],
      makeRosterData({ slots })
    );
    renderPage(qc);
    expect(screen.getByText('Total Points')).toBeTruthy();
    // Only active slots count: 10 + 5 = 15
    expect(screen.getByText('15')).toBeTruthy();
  });

  it('shows Active and Inactive status badges', () => {
    const qc = createTestQueryClient();
    const slots = [
      makeSlot({ id: 's1', position: 'F', is_active: true, points_earned: 5 }),
      makeSlot({ id: 's2', position: 'D', is_active: false, points_earned: 0 }),
    ];
    qc.setQueryData(
      ['roster', 'test-league-1', undefined],
      makeRosterData({ slots })
    );
    renderPage(qc);
    expect(screen.getByText('Active')).toBeTruthy();
    expect(screen.getByText('Inactive')).toBeTruthy();
  });

  it('shows player count badge for each position group', () => {
    const qc = createTestQueryClient();
    const slots = [
      makeSlot({ id: 's1', position: 'F', player_id: 1 }),
      makeSlot({ id: 's2', position: 'F', player_id: 2 }),
      makeSlot({ id: 's3', position: 'D', player_id: 3 }),
    ];
    qc.setQueryData(
      ['roster', 'test-league-1', undefined],
      makeRosterData({ slots })
    );
    renderPage(qc);
    expect(screen.getByText('2 players')).toBeTruthy();
    expect(screen.getByText('1 player')).toBeTruthy();
  });

  it('shows Activate IR button for IR slots', () => {
    const qc = createTestQueryClient();
    const slots = [
      makeSlot({ id: 's1', position: 'F', player_id: 1, is_active: true }),
      makeSlot({
        id: 's2',
        position: 'IR_F',
        player_id: 2,
        is_active: false,
        activated_from_ir: false,
      }),
    ];
    qc.setQueryData(
      ['roster', 'test-league-1', undefined],
      makeRosterData({ slots })
    );
    renderPage(qc);
    expect(screen.getByText('Activate IR')).toBeTruthy();
  });

  it('shows fallback player ID when player stats are not cached', () => {
    const qc = createTestQueryClient();
    const slots = [makeSlot({ id: 's1', position: 'F', player_id: 999 })];
    qc.setQueryData(
      ['roster', 'test-league-1', undefined],
      makeRosterData({ slots })
    );
    // No playoff-players cached, so fallback name used
    renderPage(qc);
    expect(screen.getByText('Player #999')).toBeTruthy();
  });
});
