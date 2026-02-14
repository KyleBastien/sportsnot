import { describe, it, expect, afterEach } from '@rstest/core';
import { render, screen, cleanup } from '@testing-library/react';
import { MantineProvider } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { DraftPage } from './DraftPage';
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
        <MemoryRouter initialEntries={[`/leagues/${leagueId}/draft`]}>
          <AuthProvider>
            <CompareProvider>
              <Routes>
                <Route path="/leagues/:leagueId/draft" element={<DraftPage />} />
              </Routes>
            </CompareProvider>
          </AuthProvider>
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>
  );
}

// Mock draft data matching the shape from useDraft query
function makeDraftData(overrides: Record<string, unknown> = {}) {
  return {
    id: 'draft-1',
    league_id: 'test-league-1',
    round: 1,
    current_pick: 1,
    status: 'in_progress',
    draft_order: ['user-1', 'user-2'],
    draft_picks: [],
    ...overrides,
  };
}

function makeMemberData() {
  return [
    { id: 'member-1', user_id: 'user-1', team_name: 'Team Alpha', total_points: 0, users: { display_name: 'Alice' } },
    { id: 'member-2', user_id: 'user-2', team_name: 'Team Beta', total_points: 0, users: { display_name: 'Bob' } },
  ];
}

describe('DraftPage', () => {
  it('shows loading state when draft data is being fetched', () => {
    // With queries disabled, draft data starts as undefined -> draftLoading is true
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

  it('shows no active draft alert when draft is null', () => {
    const qc = createTestQueryClient();
    // Set draft data to null (no draft exists)
    qc.setQueryData(['draft', 'test-league-1'], null);
    renderPage(qc);
    expect(screen.getByText('No Active Draft')).toBeTruthy();
    expect(screen.getByText(/No draft has been started/)).toBeTruthy();
  });

  it('renders Draft Room header when draft data exists', () => {
    const qc = createTestQueryClient();
    qc.setQueryData(['draft', 'test-league-1'], makeDraftData());
    qc.setQueryData(['league-members', 'test-league-1'], makeMemberData());
    renderPage(qc);
    expect(screen.getByText('Draft Room')).toBeTruthy();
  });

  it('shows round number in header', () => {
    const qc = createTestQueryClient();
    qc.setQueryData(['draft', 'test-league-1'], makeDraftData({ round: 2 }));
    qc.setQueryData(['league-members', 'test-league-1'], makeMemberData());
    renderPage(qc);
    expect(screen.getByText('Round 2')).toBeTruthy();
  });

  it('shows current pick number', () => {
    const qc = createTestQueryClient();
    qc.setQueryData(['draft', 'test-league-1'], makeDraftData({ current_pick: 3 }));
    qc.setQueryData(['league-members', 'test-league-1'], makeMemberData());
    renderPage(qc);
    expect(screen.getByText('Pick #3')).toBeTruthy();
  });

  it('shows turn indicator for current picker', () => {
    const qc = createTestQueryClient();
    qc.setQueryData(['draft', 'test-league-1'], makeDraftData({
      current_pick: 1,
      draft_order: ['user-1', 'user-2'],
    }));
    qc.setQueryData(['league-members', 'test-league-1'], makeMemberData());
    renderPage(qc);
    // Current picker is user-1 (index 0), their team_name is "Team Alpha"
    expect(screen.getByText('Team Alpha')).toBeTruthy();
  });

  it('renders draft board section with no picks message', () => {
    const qc = createTestQueryClient();
    qc.setQueryData(['draft', 'test-league-1'], makeDraftData({ draft_picks: [] }));
    qc.setQueryData(['league-members', 'test-league-1'], makeMemberData());
    renderPage(qc);
    expect(screen.getByText('Draft History')).toBeTruthy();
    expect(screen.getByText('No picks yet')).toBeTruthy();
  });

  it('renders draft board with existing picks', () => {
    const qc = createTestQueryClient();
    const picks = [
      {
        id: 'pick-1',
        pick_number: 1,
        player_id: 101,
        team_id: null,
        position: 'F',
        league_members: { team_name: 'Team Alpha', user_id: 'user-1' },
      },
      {
        id: 'pick-2',
        pick_number: 2,
        player_id: null,
        team_id: 5,
        position: 'G',
        league_members: { team_name: 'Team Beta', user_id: 'user-2' },
      },
    ];
    qc.setQueryData(['draft', 'test-league-1'], makeDraftData({
      draft_picks: picks,
      current_pick: 3,
    }));
    qc.setQueryData(['league-members', 'test-league-1'], makeMemberData());
    renderPage(qc);
    // Desktop layout shows picks in Draft History as "#pickNumber - teamName"
    expect(screen.getByText('#1 - Team Alpha')).toBeTruthy();
    expect(screen.getByText('#2 - Team Beta')).toBeTruthy();
  });

  it('renders position filter controls', () => {
    const qc = createTestQueryClient();
    qc.setQueryData(['draft', 'test-league-1'], makeDraftData());
    qc.setQueryData(['league-members', 'test-league-1'], makeMemberData());
    renderPage(qc);
    // Desktop layout shows filter labels
    expect(screen.getByText('Forwards')).toBeTruthy();
    expect(screen.getByText('Defense')).toBeTruthy();
    expect(screen.getByText('Goalies')).toBeTruthy();
  });

  it('renders search input', () => {
    const qc = createTestQueryClient();
    qc.setQueryData(['draft', 'test-league-1'], makeDraftData());
    qc.setQueryData(['league-members', 'test-league-1'], makeMemberData());
    renderPage(qc);
    expect(screen.getByPlaceholderText('Search players...')).toBeTruthy();
  });

  it('shows available players section', () => {
    const qc = createTestQueryClient();
    qc.setQueryData(['draft', 'test-league-1'], makeDraftData());
    qc.setQueryData(['league-members', 'test-league-1'], makeMemberData());
    renderPage(qc);
    expect(screen.getByText('Available Players')).toBeTruthy();
  });

  it('shows no player data message when stats are empty', () => {
    const qc = createTestQueryClient();
    qc.setQueryData(['draft', 'test-league-1'], makeDraftData());
    qc.setQueryData(['league-members', 'test-league-1'], makeMemberData());
    // No player/team stats cached
    renderPage(qc);
    expect(screen.getByText(/No player data available yet/)).toBeTruthy();
  });

  it('renders player list when player stats are cached', () => {
    const qc = createTestQueryClient();
    qc.setQueryData(['draft', 'test-league-1'], makeDraftData());
    qc.setQueryData(['league-members', 'test-league-1'], makeMemberData());
    qc.setQueryData(['playoff-players', '20242025', 1], [
      {
        player_id: 97,
        player_name: 'Connor McDavid',
        position: 'F',
        team_abbreviation: 'EDM',
        goals: 10,
        assists: 15,
        games_played: 8,
        is_injured: false,
      },
    ]);
    qc.setQueryData(['playoff-teams', '20242025', 1], []);
    renderPage(qc);
    expect(screen.getByText('Connor McDavid')).toBeTruthy();
  });
});
