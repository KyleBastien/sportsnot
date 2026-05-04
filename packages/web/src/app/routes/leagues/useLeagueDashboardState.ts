import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { supabase } from '@sportsnot/supabase';
import { WidgetApiClient } from '@sportsnot/widget-api';
import { useIsMobile } from '@sportsnot/ui';
import { useCompletedDrafts } from '../../hooks/useCompletedDrafts';
import { useRoundComplete } from '../../hooks/useRoundComplete';
import { useWinnerConfetti } from '../../hooks/useWinnerConfetti';
import { deriveCurrentRound } from '../../utils/roundUtils';
import { useMockLeague } from '../../../mock/hooks/useMockLeagues';
import { useMockData } from '../../../mock/MockDataProvider';
import { useMockLeagueWidgetSnapshot } from '../../../mock/hooks/useMockLeagueWidgetSnapshot';
import type { LeagueMemberRow } from './LeagueDashboardContent';

const IS_MOCK = import.meta.env.VITE_MOCK_MODE === 'true';
const WIDGET_SNAPSHOT_STALE_TIME_MS = 5 * 60 * 1000;

function getWidgetClientConfig() {
  const supabaseUrl = import.meta.env.VITE_SUPABASE_URL as string | undefined;
  const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined;

  if (!supabaseUrl || !anonKey) {
    throw new Error('Supabase widget config missing');
  }

  return { anonKey, supabaseUrl };
}

function fetchLeagueWidgetSnapshot(shareCode: string) {
  const { anonKey, supabaseUrl } = getWidgetClientConfig();
  const client = new WidgetApiClient({ supabaseUrl, anonKey });
  return client.getSnapshot(shareCode);
}

function useLeague(leagueId: string | undefined) {
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
        .eq('id', leagueId!)
        .single();

      if (error) throw error;
      return data;
    },
    enabled: !IS_MOCK && !!leagueId,
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
      if (!shareCode) {
        throw new Error('League widget share code missing');
      }

      return fetchLeagueWidgetSnapshot(shareCode);
    },
    enabled: !IS_MOCK && enabled && !!shareCode,
    staleTime: WIDGET_SNAPSHOT_STALE_TIME_MS,
  });

  return IS_MOCK ? mockResult : queryResult;
}

function getLeagueGameCardsError(
  leagueStatus: string,
  shareCode: string | null | undefined,
  widgetSnapshotError: Error | null
): Error | null {
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

function getWinnerId(
  members: LeagueMemberRow[],
  seasonComplete: boolean
): string | undefined {
  if (!seasonComplete) {
    return undefined;
  }

  return [...members].sort(
    (a: LeagueMemberRow, b: LeagueMemberRow) =>
      (b.total_points ?? 0) - (a.total_points ?? 0)
  )[0]?.user_id;
}

function getLeagueMembers(
  members: LeagueMemberRow[] | null | undefined
): LeagueMemberRow[] {
  return members ?? [];
}

function getRoundStatusLoading(
  currentRoundValue: number | null | undefined,
  completedDraftsLoading: boolean,
  roundCompleteLoading: boolean
): boolean {
  const needsCurrentRoundFallback =
    !currentRoundValue || currentRoundValue <= 0;

  return (
    roundCompleteLoading ||
    (needsCurrentRoundFallback && completedDraftsLoading)
  );
}

function toError(value: unknown): Error | null {
  return value instanceof Error ? value : null;
}

async function startNextDraftTransition(
  leagueId: string | undefined,
  dispatch: ReturnType<typeof useMockData>['dispatch'],
  navigate: ReturnType<typeof useNavigate>
) {
  if (!leagueId) return;

  if (IS_MOCK) {
    dispatch({ type: 'START_NEXT_DRAFT', payload: { leagueId } });
  } else {
    await supabase
      .from('leagues')
      .update({ status: 'drafting' })
      .eq('id', leagueId);
  }

  navigate(`/draft/${leagueId}/transition`);
}

function useLeagueDashboardActions(leagueId: string | undefined) {
  const navigate = useNavigate();
  const { dispatch } = useMockData();

  return {
    openDraft: () => navigate(`/draft/${leagueId}`),
    openLobby: () => navigate(`/draft/${leagueId}/lobby`),
    openRoster: () => navigate(`/roster/${leagueId}`),
    openSettings: () => navigate(`/leagues/${leagueId}/settings`),
    openStandings: () => navigate(`/standings/${leagueId}`),
    startNextDraft: () =>
      startNextDraftTransition(leagueId, dispatch, navigate),
  };
}

function useLeagueDashboardSummary(
  league:
    | {
        current_round?: number | null;
        league_members?: LeagueMemberRow[] | null;
        share_code?: string | null;
        status?: string;
      }
    | null
    | undefined,
  completedDrafts: { length: number } | null | undefined,
  completedDraftsLoading: boolean,
  widgetSnapshotError: unknown
) {
  const currentRound = deriveCurrentRound(
    league?.current_round,
    completedDrafts?.length ?? 0
  );
  const {
    roundComplete,
    seasonComplete,
    isLoading: roundCompleteLoading,
  } = useRoundComplete(currentRound);
  const roundStatusLoading = getRoundStatusLoading(
    league?.current_round,
    completedDraftsLoading,
    roundCompleteLoading
  );
  const members = getLeagueMembers(league?.league_members);
  const winnerId = getWinnerId(members, seasonComplete);
  const leagueGameCardsError = getLeagueGameCardsError(
    league?.status ?? '',
    league?.share_code,
    toError(widgetSnapshotError)
  );

  return {
    currentRound,
    leagueGameCardsError,
    members,
    roundComplete,
    roundStatusLoading,
    seasonComplete,
    winnerId,
  };
}

function useLeagueDashboardConfetti(
  leagueId: string | undefined,
  seasonComplete: boolean,
  userId: string | undefined,
  winnerId: string | undefined
) {
  useWinnerConfetti({
    seasonComplete,
    isWinner: !!winnerId && winnerId === userId,
    leagueId,
  });
}

export function useLeagueDashboardState(
  leagueId: string | undefined,
  userId: string | undefined
) {
  const isMobile = useIsMobile();
  const actions = useLeagueDashboardActions(leagueId);
  const { data: league, isLoading, error } = useLeague(leagueId);
  const { data: completedDrafts, isLoading: completedDraftsLoading } =
    useCompletedDrafts(leagueId);
  const {
    data: widgetSnapshot,
    isLoading: widgetSnapshotLoading,
    error: widgetSnapshotError,
  } = useLeagueWidgetSnapshot(leagueId, league?.share_code, league?.status);
  const summary = useLeagueDashboardSummary(
    league,
    completedDrafts,
    completedDraftsLoading,
    widgetSnapshotError
  );

  useLeagueDashboardConfetti(
    leagueId,
    summary.seasonComplete,
    userId,
    summary.winnerId
  );

  return {
    ...actions,
    error,
    isLoading,
    isMobile,
    league,
    ...summary,
    widgetSnapshot,
    widgetSnapshotLoading,
  };
}
