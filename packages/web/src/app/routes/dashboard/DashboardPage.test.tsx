import { describe, it, expect, afterEach } from '@rstest/core';
import { render, screen, cleanup } from '@testing-library/react';
import { MantineProvider } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { DashboardPage } from './DashboardPage';
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
      },
    },
  });
}

function renderPage(queryClient?: QueryClient) {
  const qc = queryClient ?? createTestQueryClient();
  return render(
    <MantineProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <AuthProvider>
            <DashboardPage />
          </AuthProvider>
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>
  );
}

describe('DashboardPage', () => {
  it('renders dashboard title and welcome message', () => {
    renderPage();
    expect(screen.getByText('Dashboard')).toBeTruthy();
    expect(screen.getByText(/Welcome back/)).toBeTruthy();
  });

  it('renders Create League and Join League action buttons', () => {
    renderPage();
    expect(screen.getByText('Create League')).toBeTruthy();
    expect(screen.getByText('Join League')).toBeTruthy();
  });

  it('shows My Leagues heading', () => {
    renderPage();
    expect(screen.getByText('My Leagues')).toBeTruthy();
  });

  it('shows loading indicator when data is being fetched', () => {
    // With no cached data, useQuery will be in loading state
    const { container } = renderPage();
    // Mantine Loader renders a div with role="presentation" or an SVG
    const loader = container.querySelector('.mantine-Loader-root');
    expect(loader).toBeTruthy();
  });

  it('shows empty state message when user has no leagues', () => {
    const qc = createTestQueryClient();
    // Pre-populate cache with empty array (user undefined since auth starts with no user)
    qc.setQueryData(['my-leagues', undefined], []);
    renderPage(qc);
    expect(screen.getByText("You haven't joined any leagues yet")).toBeTruthy();
    // Shows alternate action buttons in empty state
    expect(screen.getByText('Create a League')).toBeTruthy();
    expect(screen.getByText('Join with Invite Code')).toBeTruthy();
  });

  it('renders league cards when leagues data is available', () => {
    const qc = createTestQueryClient();
    const mockLeagues = [
      {
        id: 'league-1',
        name: 'Test League Alpha',
        status: 'active',
        current_round: 2,
        max_participants: 8,
        commissioner_id: 'user-1',
        invite_code: 'ABC123',
        league_members: [
          { team_name: 'Team A', total_points: 10, user_id: 'user-1' },
          { team_name: 'Team B', total_points: 5, user_id: 'user-2' },
        ],
        memberCount: 2,
      },
      {
        id: 'league-2',
        name: 'Winter Cup',
        status: 'drafting',
        current_round: 1,
        max_participants: 6,
        commissioner_id: 'user-1',
        invite_code: 'DEF456',
        league_members: [
          { team_name: 'Team C', total_points: 0, user_id: 'user-1' },
        ],
        memberCount: 1,
      },
    ];
    qc.setQueryData(['my-leagues', undefined], mockLeagues);
    renderPage(qc);
    expect(screen.getByText('Test League Alpha')).toBeTruthy();
    expect(screen.getByText('Winter Cup')).toBeTruthy();
    // Status badges
    expect(screen.getByText('active')).toBeTruthy();
    expect(screen.getByText('drafting')).toBeTruthy();
    // Member count and round info
    expect(screen.getByText('Round 2 · 2 members')).toBeTruthy();
    expect(screen.getByText('Round 1 · 1 members')).toBeTruthy();
  });

  it('does not show empty state when leagues exist', () => {
    const qc = createTestQueryClient();
    qc.setQueryData(
      ['my-leagues', undefined],
      [
        {
          id: 'league-1',
          name: 'My League',
          status: 'active',
          current_round: 1,
          max_participants: 4,
          commissioner_id: 'u1',
          invite_code: 'XYZ',
          league_members: [{ team_name: 'T1', total_points: 0, user_id: 'u1' }],
          memberCount: 1,
        },
      ]
    );
    renderPage(qc);
    expect(screen.queryByText("You haven't joined any leagues yet")).toBeNull();
  });
});
