import { supabase } from '@sportsnot/supabase';
import { LeagueMemberRow } from './leagueDashboardTypes';

const IS_MOCK = import.meta.env.VITE_MOCK_MODE === 'true';

export const STATUS_COLORS: Record<string, string> = {
  setup: 'blue',
  drafting: 'orange',
  active: 'green',
  completed: 'gray',
};

export function sortMembersByPoints(members: LeagueMemberRow[]) {
  return [...members].sort(
    (a, b) => (b.total_points ?? 0) - (a.total_points ?? 0)
  );
}

export function getCurrentUserTeamName(
  members: LeagueMemberRow[],
  userId: string | undefined
): string | null {
  return members.find((member) => member.user_id === userId)?.team_name ?? null;
}

export function getLeagueGameCardsError(params: {
  leagueStatus: string | undefined;
  shareCode: string | null | undefined;
  widgetSnapshotError: Error | null;
}) {
  const { leagueStatus, shareCode, widgetSnapshotError } = params;
  if (leagueStatus !== 'active') {
    return widgetSnapshotError;
  }

  if (IS_MOCK) {
    return widgetSnapshotError;
  }

  if (shareCode) {
    return widgetSnapshotError;
  }

  return new Error('League widget share code missing');
}

export async function startNextDraftForLeague(params: {
  leagueId: string | undefined;
  dispatch: (action: {
    type: 'START_NEXT_DRAFT';
    payload: { leagueId: string };
  }) => void;
}) {
  const { leagueId, dispatch } = params;
  if (!leagueId) {
    return;
  }

  if (IS_MOCK) {
    dispatch({ type: 'START_NEXT_DRAFT', payload: { leagueId } });
    return;
  }

  await supabase
    .from('leagues')
    .update({ status: 'drafting' })
    .eq('id', leagueId);
}

export function buildLeagueDashboardState(params: {
  league:
    | ({
        league_members?: LeagueMemberRow[];
        commissioner_id?: string | null;
        status: string;
        share_code?: string | null;
      } & Record<string, unknown>)
    | null
    | undefined;
  userId: string | undefined;
  widgetSnapshotError: Error | null;
  seasonComplete: boolean;
}) {
  const { league, userId, widgetSnapshotError, seasonComplete } = params;
  const members = (league?.league_members ?? []) as LeagueMemberRow[];
  const sortedMembers = sortMembersByPoints(members);

  return {
    members,
    sortedMembers,
    winnerId: seasonComplete ? sortedMembers[0]?.user_id : undefined,
    currentUserTeamName: getCurrentUserTeamName(members, userId),
    isCommissioner: league?.commissioner_id === userId,
    statusColor: league ? STATUS_COLORS[league.status] : undefined,
    leagueGameCardsError: getLeagueGameCardsError({
      leagueStatus: league?.status,
      shareCode: league?.share_code,
      widgetSnapshotError,
    }),
  };
}
