import { useEffect, useRef, useState } from 'react';
import { supabase } from '@sportsnot/supabase';

const IS_MOCK = import.meta.env.VITE_MOCK_MODE === 'true';

interface UseRosterTeamStatsSyncParams {
  season: string;
  selectedRound: number;
  leagueCurrentRound: number;
  currentRoundTeamStatsFetched: boolean;
  nextRoundTeamStatsFetched: boolean;
  currentRoundTeamStatsLength: number;
  nextRoundTeamStatsLength: number;
  refetchCurrentRoundTeamStats: () => Promise<unknown>;
  refetchNextRoundTeamStats: () => Promise<unknown>;
}

export function useRosterTeamStatsSync({
  season,
  selectedRound,
  leagueCurrentRound,
  currentRoundTeamStatsFetched,
  nextRoundTeamStatsFetched,
  currentRoundTeamStatsLength,
  nextRoundTeamStatsLength,
  refetchCurrentRoundTeamStats,
  refetchNextRoundTeamStats,
}: UseRosterTeamStatsSyncParams) {
  const syncedKeyRef = useRef<string | null>(null);
  const [isRosterTeamStatsSyncing, setIsRosterTeamStatsSyncing] =
    useState(false);

  useEffect(() => {
    if (IS_MOCK) {
      return;
    }

    if (selectedRound !== leagueCurrentRound) {
      return;
    }

    const syncRound = resolveTeamStatsRoundToSync({
      selectedRound,
      currentRoundTeamStatsFetched,
      nextRoundTeamStatsFetched,
      currentRoundTeamStatsLength,
      nextRoundTeamStatsLength,
    });

    if (syncRound == null) {
      return;
    }

    const syncKey = `${season}:${syncRound}`;
    if (syncedKeyRef.current === syncKey) {
      return;
    }

    syncedKeyRef.current = syncKey;

    const syncRosterTeamStats = async () => {
      setIsRosterTeamStatsSyncing(true);

      try {
        await supabase.functions.invoke('sync-nhl-stats', {
          body: {
            season,
            playoff_round: syncRound,
          },
        });

        await Promise.all([
          refetchCurrentRoundTeamStats(),
          refetchNextRoundTeamStats(),
        ]);
      } finally {
        setIsRosterTeamStatsSyncing(false);
      }
    };

    void syncRosterTeamStats();
  }, [
    currentRoundTeamStatsFetched,
    currentRoundTeamStatsLength,
    leagueCurrentRound,
    nextRoundTeamStatsFetched,
    nextRoundTeamStatsLength,
    refetchCurrentRoundTeamStats,
    refetchNextRoundTeamStats,
    season,
    selectedRound,
  ]);

  return isRosterTeamStatsSyncing;
}

function resolveTeamStatsRoundToSync(params: {
  selectedRound: number;
  currentRoundTeamStatsFetched: boolean;
  nextRoundTeamStatsFetched: boolean;
  currentRoundTeamStatsLength: number;
  nextRoundTeamStatsLength: number;
}) {
  const {
    selectedRound,
    currentRoundTeamStatsFetched,
    nextRoundTeamStatsFetched,
    currentRoundTeamStatsLength,
    nextRoundTeamStatsLength,
  } = params;

  if (selectedRound === 4) {
    if (!currentRoundTeamStatsFetched) {
      return null;
    }

    if (currentRoundTeamStatsLength !== 0) {
      return null;
    }

    return selectedRound;
  }

  if (selectedRound >= 4) {
    return null;
  }

  if (!nextRoundTeamStatsFetched) {
    return null;
  }

  if (currentRoundTeamStatsLength === 0) {
    return null;
  }

  if (nextRoundTeamStatsLength !== 0) {
    return null;
  }

  return selectedRound + 1;
}
