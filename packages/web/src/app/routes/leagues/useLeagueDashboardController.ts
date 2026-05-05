import { useQuery } from '@tanstack/react-query';
import { supabase } from '@sportsnot/supabase';
import { useIsMobile } from '@sportsnot/ui';
import { useMockLeague } from '../../../mock/hooks/useMockLeagues';
import { useMockData } from '../../../mock/MockDataProvider';
import { useMockLeagueWidgetSnapshot } from '../../../mock/hooks/useMockLeagueWidgetSnapshot';
import { useRoundComplete } from '../../hooks/useRoundComplete';
import { useWinnerConfetti } from '../../hooks/useWinnerConfetti';
import {
  buildLeagueDashboardState,
  startNextDraftForLeague,
} from './leagueDashboardControllerHelpers';

const IS_MOCK = import.meta.env.VITE_MOCK_MODE === 'true';
const WIDGET_SNAPSHOT_STALE_TIME_MS = 5 * 60 * 1000;

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
  const {
    roundComplete,
    seasonComplete,
    isLoading: roundStatusLoading,
  } = useRoundComplete(league?.current_round ?? 0);
  const state = buildLeagueDashboardState({
    league,
    userId,
    widgetSnapshotError:
      widgetSnapshotError instanceof Error ? widgetSnapshotError : null,
    seasonComplete,
  });

  useWinnerConfetti({
    seasonComplete,
    isWinner: !!state.winnerId && state.winnerId === userId,
    leagueId,
  });

  return {
    league,
    isLoading,
    error,
    isMobile: useIsMobile(),
    members: state.members,
    sortedMembers: state.sortedMembers,
    currentUserTeamName: state.currentUserTeamName,
    isCommissioner: state.isCommissioner,
    statusColor: state.statusColor,
    seasonComplete,
    roundComplete,
    roundStatusLoading,
    widgetSnapshot,
    widgetSnapshotLoading,
    leagueGameCardsError: state.leagueGameCardsError,
    startNextDraft: async () => startNextDraftForLeague({ leagueId, dispatch }),
  };
}
