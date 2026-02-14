import { describe, it, expect, afterEach } from '@rstest/core';
import { render, screen, cleanup } from '@testing-library/react';
import { MantineProvider } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { StandingsPage } from './StandingsPage';
import { AuthProvider } from '../../context/AuthContext';

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
        <MemoryRouter initialEntries={[`/leagues/${leagueId}/standings`]}>
          <AuthProvider>
            <Routes>
              <Route
                path="/leagues/:leagueId/standings"
                element={<StandingsPage />}
              />
            </Routes>
          </AuthProvider>
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>
  );
}

describe('StandingsPage', () => {
  it('shows loading state when data is being fetched', () => {
    const qc = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
          gcTime: 0,
          refetchOnMount: false,
          refetchInterval: false,
        },
      },
    });
    const { container } = renderPage(qc);
    const loader = container.querySelector('.mantine-Loader-root');
    expect(loader).toBeTruthy();
  });

  it('shows error alert when data fails to load', () => {
    const qc = createTestQueryClient();
    // Set standings data to null (simulates error/no data)
    qc.setQueryData(['standings', 'test-league-1'], null);
    renderPage(qc);
    // The page checks error || !data, with null data it shows error
    expect(screen.getByText('Could not load standings.')).toBeTruthy();
  });

  it('renders Standings title when data is loaded', () => {
    const qc = createTestQueryClient();
    qc.setQueryData(['standings', 'test-league-1'], {
      league: { name: 'Test League', current_round: 2 },
      members: [],
    });
    renderPage(qc);
    expect(screen.getByText('Standings')).toBeTruthy();
  });

  it('shows league name and round number', () => {
    const qc = createTestQueryClient();
    qc.setQueryData(['standings', 'test-league-1'], {
      league: { name: 'Winter Cup', current_round: 3 },
      members: [],
    });
    renderPage(qc);
    expect(screen.getByText(/Winter Cup/)).toBeTruthy();
    expect(screen.getByText(/Round 3/)).toBeTruthy();
  });

  it('renders standings table with point totals', () => {
    const qc = createTestQueryClient();
    qc.setQueryData(['standings', 'test-league-1'], {
      league: { name: 'My League', current_round: 1 },
      members: [
        {
          id: 'm1',
          user_id: 'u1',
          team_name: 'Team Alpha',
          total_points: 42,
          users: { display_name: 'Alice' },
        },
        {
          id: 'm2',
          user_id: 'u2',
          team_name: 'Team Beta',
          total_points: 35,
          users: { display_name: 'Bob' },
        },
        {
          id: 'm3',
          user_id: 'u3',
          team_name: 'Team Gamma',
          total_points: 28,
          users: { display_name: 'Carol' },
        },
      ],
    });
    renderPage(qc);
    expect(screen.getByText('Team Alpha')).toBeTruthy();
    expect(screen.getByText('Team Beta')).toBeTruthy();
    expect(screen.getByText('Team Gamma')).toBeTruthy();
    expect(screen.getByText('42')).toBeTruthy();
    expect(screen.getByText('35')).toBeTruthy();
    expect(screen.getByText('28')).toBeTruthy();
  });

  it('renders rank badges for top 3 positions', () => {
    const qc = createTestQueryClient();
    qc.setQueryData(['standings', 'test-league-1'], {
      league: { name: 'Ranked League', current_round: 1 },
      members: [
        {
          id: 'm1',
          user_id: 'u1',
          team_name: 'First',
          total_points: 100,
          users: { display_name: 'A' },
        },
        {
          id: 'm2',
          user_id: 'u2',
          team_name: 'Second',
          total_points: 80,
          users: { display_name: 'B' },
        },
        {
          id: 'm3',
          user_id: 'u3',
          team_name: 'Third',
          total_points: 60,
          users: { display_name: 'C' },
        },
      ],
    });
    renderPage(qc);
    expect(screen.getByText('1st')).toBeTruthy();
    expect(screen.getByText('2nd')).toBeTruthy();
    expect(screen.getByText('3rd')).toBeTruthy();
  });

  it('shows manager names in standings table', () => {
    const qc = createTestQueryClient();
    qc.setQueryData(['standings', 'test-league-1'], {
      league: { name: 'League', current_round: 1 },
      members: [
        {
          id: 'm1',
          user_id: 'u1',
          team_name: 'Team A',
          total_points: 10,
          users: { display_name: 'Alice Johnson' },
        },
        {
          id: 'm2',
          user_id: 'u2',
          team_name: 'Team B',
          total_points: 5,
          users: { display_name: 'Bob Smith' },
        },
      ],
    });
    renderPage(qc);
    expect(screen.getByText(/Alice Johnson/)).toBeTruthy();
    expect(screen.getByText(/Bob Smith/)).toBeTruthy();
  });

  it('shows Unknown for manager when users data is null', () => {
    const qc = createTestQueryClient();
    qc.setQueryData(['standings', 'test-league-1'], {
      league: { name: 'League', current_round: 1 },
      members: [
        {
          id: 'm1',
          user_id: 'u1',
          team_name: 'No Manager Team',
          total_points: 10,
          users: null,
        },
      ],
    });
    renderPage(qc);
    expect(screen.getByText(/Unknown/)).toBeTruthy();
  });

  it('renders table column headers', () => {
    const qc = createTestQueryClient();
    qc.setQueryData(['standings', 'test-league-1'], {
      league: { name: 'League', current_round: 1 },
      members: [
        {
          id: 'm1',
          user_id: 'u1',
          team_name: 'T1',
          total_points: 0,
          users: { display_name: 'A' },
        },
      ],
    });
    renderPage(qc);
    expect(screen.getByText('Rank')).toBeTruthy();
    expect(screen.getByText('Team')).toBeTruthy();
    expect(screen.getByText('Manager')).toBeTruthy();
    // Points header includes sort indicator ↕
    expect(screen.getByText(/Points/)).toBeTruthy();
  });
});
