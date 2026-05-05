import { useQuery } from '@tanstack/react-query';
import { supabase } from '@sportsnot/supabase';
import { useIsMobile } from '@sportsnot/ui';
import { useMockLeague } from '../../../mock/hooks/useMockLeagues';
import { useMockData } from '../../../mock/MockDataProvider';
import { useMockLeagueWidgetSnapshot } from '../../../mock/hooks/useMockLeagueWidgetSnapshot';
import { useRoundComplete } from '../../hooks/useRoundComplete';
import { useWinnerConfetti } from '../../hooks/useWinnerConfetti';
import { LeagueMemberRow } from './leagueDashboardTypes';

const IS_MOCK = import.meta.env.VITE_MOCK_MODE === 'true';
const WIDGET_SNAPSHOT_STALE_TIME_MS = 5 * 60 * 1000;

const STATUS_COLORS: Record<string, string> = {
  setup: 'blue',
  drafting: 'orange',
  active: 'green',
  completed: 'gray',
};

function useLeague(leagueId: string) {
  const mockResult = useMockLeague(leagueId);

  const queryResult = useQuery({
    queryKey: ['league', leagueId],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('leagues')
        .select(
          `
          *,
          league_members(
            id, user_id, team_name, total_points,
            users(display_name, avatar_url)
          )
        `
        )
        .eq('id', leagueId)
        .single();

      if (error) {
        throw error;
      }

      return data;
    },
    enabled: !IS_MOCK,
  });

  return IS_MOCK ? mockResult : queryResult;
}

function useLeagueWidgetSnapshot(
  leagueId: string | undefined,
  shareCode: string | null | undefined,
  leagueStatus: string | undefined
) {
  const mockResult = useMockLeagueWidgetSnapshot(leagueId);
  const enabled = leagueStatus === 'active';

  const queryResult = useQuery({
    queryKey: ['league-widget-snapshot', shareCode],
    queryFn: async () => {
      const supabaseUrl = import.meta.env.VITE_SUPABASE_URL as
        | string
        | undefined;
      const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY as
        | string
        | undefined;

      if (!supabaseUrl || !anonKey) {
        throw new Error('Supabase widget config missing');
      }

      if (!shareCode) {
        throw new Error('League widget share code missing');
      }

      const { WidgetApiClient } = await import('@sportsnot/widget-api');
      const client = new WidgetApiClient({ supabaseUrl, anonKey });
      return client.getSnapshot(shareCode);
    },
    enabled: !IS_MOCK && enabled && !!shareCode,
    staleTime: WIDGET_SNAPSHOT_STALE_TIME_MS,
  });

  return IS_MOCK ? mockResult : queryResult;
}

function sortMembersByPoints(members: LeagueMemberRow[]) {
  return [...members].sort(
    (a, b) => (b.total_points ?? 0) - (a.total_points ?? 0)
  );
}

export function useLeagueDashboardController(
  leagueId: string | undefined,
  userId: string | undefined
) {
  const { dispatch } = useMockData();
  const { data: league, isLoading, error } = useLeague(leagueId!);
  const {
    data: widgetSnapshot,
    isLoading: widgetSnapshotLoading,
    error: widgetSnapshotError,
  } = useLeagueWidgetSnapshot(leagueId, league?.share_code, league?.status);

  const currentRound = league?.current_round ?? 0;
  const {
    roundComplete,
    seasonComplete,
    isLoading: roundStatusLoading,
  } = useRoundComplete(currentRound);

  const members = (league?.league_members ?? []) as LeagueMemberRow[];
  const sortedMembers = sortMembersByPoints(members);
  const winnerId = seasonComplete ? sortedMembers[0]?.user_id : undefined;

  useWinnerConfetti({
    seasonComplete,
    isWinner: !!winnerId && winnerId === userId,
    leagueId,
  });

  const currentUserTeamName =
    members.find((member) => member.user_id === userId)?.team_name ?? null;
  const isCommissioner = league?.commissioner_id === userId;
  const leagueGameCardsError =
    league?.status === 'active' && !IS_MOCK && !league.share_code
      ? new Error('League widget share code missing')
      : widgetSnapshotError instanceof Error
        ? widgetSnapshotError
        : null;

  const startNextDraft = async () => {
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
  };

  return {
    league,
    isLoading,
    error,
    isMobile: useIsMobile(),
    members,
    sortedMembers,
    currentUserTeamName,
    isCommissioner,
    statusColor: league ? STATUS_COLORS[league.status] : undefined,
    seasonComplete,
    roundComplete,
    roundStatusLoading,
    widgetSnapshot,
    widgetSnapshotLoading,
    leagueGameCardsError,
    startNextDraft,
  };
}
