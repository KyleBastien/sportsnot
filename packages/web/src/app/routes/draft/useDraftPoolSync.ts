import { useEffect, useRef, useState } from 'react';
import { supabase } from '@sportsnot/supabase';
import type { DraftStateRow } from './draftPageTypes';

const IS_MOCK = import.meta.env.VITE_MOCK_MODE === 'true';

interface UseDraftPoolSyncParams {
  draft: DraftStateRow | null;
  currentSeason: string;
  playerStatsLength: number;
  teamStatsLength: number;
  refetchPlayerStats: () => Promise<unknown>;
  refetchTeamStats: () => Promise<unknown>;
}

export function useDraftPoolSync({
  draft,
  currentSeason,
  playerStatsLength,
  teamStatsLength,
  refetchPlayerStats,
  refetchTeamStats,
}: UseDraftPoolSyncParams) {
  const draftPoolSyncDraftIdRef = useRef<string | null>(null);
  const [isDraftPoolSyncing, setIsDraftPoolSyncing] = useState(false);

  useEffect(() => {
    if (!shouldSyncDraftPool(draft, draftPoolSyncDraftIdRef.current)) {
      return;
    }

    if (!isDraftPoolMissing(playerStatsLength, teamStatsLength)) {
      return;
    }

    draftPoolSyncDraftIdRef.current = draft.id;

    const syncDraftPool = async () => {
      setIsDraftPoolSyncing(true);

      try {
        await supabase.functions.invoke('sync-nhl-stats', {
          body: {
            season: currentSeason,
            playoff_round: draft.round,
          },
        });
        await Promise.all([refetchPlayerStats(), refetchTeamStats()]);
      } finally {
        setIsDraftPoolSyncing(false);
      }
    };

    void syncDraftPool();
  }, [
    currentSeason,
    draft,
    playerStatsLength,
    refetchPlayerStats,
    refetchTeamStats,
    teamStatsLength,
  ]);

  return isDraftPoolSyncing;
}

function shouldSyncDraftPool(
  draft: DraftStateRow | null,
  syncedDraftId: string | null
): draft is DraftStateRow {
  return !IS_MOCK && Boolean(draft && syncedDraftId !== draft.id);
}

function isDraftPoolMissing(
  playerStatsLength: number,
  teamStatsLength: number
): boolean {
  return playerStatsLength === 0 || teamStatsLength === 0;
}
