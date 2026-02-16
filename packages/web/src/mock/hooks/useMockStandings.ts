import { useMockData } from '../MockDataProvider';
import { calculateMemberPoints } from '../utils';

// ── Mock TanStack query helper ─────────────────────────────────────────
interface MockQueryResult<T> {
  data: T;
  isLoading: false;
  isError: false;
  error: null;
  isFetching: false;
  isSuccess: true;
  status: 'success';
  refetch: () => Promise<MockQueryResult<T>>;
}

function makeMockQuery<T>(data: T): MockQueryResult<T> {
  const result: MockQueryResult<T> = {
    data,
    isLoading: false,
    isError: false,
    error: null,
    isFetching: false,
    isSuccess: true,
    status: 'success',
    refetch: () => Promise.resolve(result),
  };
  return result;
}

// ── useMockStandings ───────────────────────────────────────────────────
// Returns data matching the inline useStandings hook in StandingsPage.tsx:
// { league: { name, current_round }, members: [{ id, user_id, team_name, total_points, ... }] }
export function useMockStandings(leagueId: string) {
  const { state } = useMockData();

  const league = state.leagues.find((l) => l.id === leagueId);
  if (!league) {
    return makeMockQuery({ league: null, members: [] });
  }

  const members = league.members.map((member) => {
    const pts = calculateMemberPoints(state, member.id);

    return {
      id: member.id,
      user_id: member.userId,
      team_name: member.teamName,
      total_points: pts.totalPoints,
      player_points: pts.playerPoints,
      goalie_points: pts.goaliePoints,
      round_points: pts.roundPoints,
      users: { display_name: member.user?.displayName ?? 'Unknown' },
    };
  });

  // Sort by total_points descending
  members.sort((a, b) => b.total_points - a.total_points);

  return makeMockQuery({
    league: { name: league.name, current_round: state.currentRound },
    members,
  });
}
