import { useCallback, useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { getScoresNow } from '@sportsnot/nhl-api';
import { supabase } from '../supabase';

/* eslint-disable no-undef */

/**
 * Polls for active NHL games and triggers stat sync Edge Functions
 * when games are live. Pauses when the browser tab is hidden.
 */
export function useStatSync(leagueId: string | undefined) {
  const queryClient = useQueryClient();
  const [isSyncing, setIsSyncing] = useState(false);
  const [lastSyncedAt, setLastSyncedAt] = useState<Date | null>(null);
  const [isTabVisible, setIsTabVisible] = useState(!document.hidden);
  const syncInProgress = useRef(false);

  // Track tab visibility
  useEffect(() => {
    const handler = () => setIsTabVisible(!document.hidden);
    document.addEventListener('visibilitychange', handler);
    return () => document.removeEventListener('visibilitychange', handler);
  }, []);

  // Poll for active games using React Query's refetchInterval
  const {
    data: games = [],
    isLoading: isCheckingGames,
  } = useQuery({
    queryKey: ['nhl-scores-now'],
    queryFn: () => getScoresNow(),
    refetchInterval: isTabVisible ? 60_000 : false,
    refetchIntervalInBackground: false,
    enabled: !!leagueId && isTabVisible,
    staleTime: 30_000,
  });

  const isLive = games.some(
    (g) => g.gameState === 'LIVE' || g.gameState === 'PRE'
  );

  // Sync function that calls the Edge Functions
  const syncNow = useCallback(async () => {
    if (!leagueId || syncInProgress.current) return;
    syncInProgress.current = true;
    setIsSyncing(true);

    try {
      // Fetch roster player IDs and team abbreviations for this league
      const { data: members } = await supabase
        .from('league_members')
        .select('id')
        .eq('league_id', leagueId);

      if (!members?.length) return;

      const memberIds = members.map((m: { id: string }) => m.id);

      const { data: rosters } = await supabase
        .from('rosters')
        .select('player_id, team_id')
        .in('league_member_id', memberIds)
        .eq('is_active', true);

      if (!rosters?.length) return;

      const playerIds = [
        ...new Set(
          rosters
            .filter((r: { player_id: number | null }) => r.player_id != null)
            .map((r: { player_id: number }) => r.player_id)
        ),
      ];

      const teamIds = [
        ...new Set(
          rosters
            .filter((r: { team_id: number | null }) => r.team_id != null)
            .map((r: { team_id: number }) => r.team_id)
        ),
      ];

      // Call Edge Functions in parallel
      const promises: Promise<unknown>[] = [];

      if (playerIds.length > 0) {
        promises.push(
          supabase.functions.invoke('sync-player-stats', {
            body: { player_ids: playerIds },
          })
        );
      }

      if (teamIds.length > 0) {
        // Fetch team abbreviations from team_stats_cache or use IDs directly
        promises.push(
          supabase.functions.invoke('sync-team-stats', {
            body: { team_ids: teamIds },
          })
        );
      }

      await Promise.all(promises);

      setLastSyncedAt(new Date());

      // Invalidate stat caches so UI refreshes
      queryClient.invalidateQueries({ queryKey: ['playoff-players'] });
      queryClient.invalidateQueries({ queryKey: ['playoff-teams'] });
      queryClient.invalidateQueries({ queryKey: ['roster'] });
      queryClient.invalidateQueries({ queryKey: ['league-rosters'] });
    } catch (err) {
      console.error('Stat sync failed:', err);
    } finally {
      setIsSyncing(false);
      syncInProgress.current = false;
    }
  }, [leagueId, queryClient]);

  // Auto-sync when games are live
  useEffect(() => {
    if (!isLive || !isTabVisible || !leagueId || isCheckingGames) return;

    // Trigger an initial sync
    syncNow();

    // Set up the 60-second polling interval
    const interval = setInterval(syncNow, 60_000);
    return () => clearInterval(interval);
  }, [isLive, isTabVisible, leagueId, isCheckingGames, syncNow]);

  return {
    lastSyncedAt,
    isSyncing,
    syncNow,
    isLive,
  };
}
