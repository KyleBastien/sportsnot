import { useEffect, useRef, useState, useCallback } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { supabase } from '../supabase';

/* eslint-disable no-undef */

interface PointDelta {
  id: string;
  delta: number;
  timestamp: number;
}

/**
 * Subscribes to Supabase Realtime on rosters and league_members tables,
 * tracks point changes for animations, and exposes live-scoring state.
 */
export function useLiveScoring(leagueId: string | undefined) {
  const queryClient = useQueryClient();
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [memberDeltas, setMemberDeltas] = useState<Record<string, PointDelta>>({});
  const [slotDeltas, setSlotDeltas] = useState<Record<string, PointDelta>>({});
  const deltaTimers = useRef<number[]>([]);

  // Clear a delta after animation duration (2 seconds)
  const scheduleDeltaClear = useCallback(
    (
      id: string,
      setter: React.Dispatch<React.SetStateAction<Record<string, PointDelta>>>
    ) => {
      const timer = window.setTimeout(() => {
        setter((prev) => {
          const next = { ...prev };
          delete next[id];
          return next;
        });
      }, 2000);
      deltaTimers.current.push(timer);
    },
    []
  );

  useEffect(() => {
    if (!leagueId) return;

    const channel = supabase
      .channel(`live-scoring-${leagueId}`)
      .on(
        'postgres_changes',
        {
          event: 'UPDATE',
          schema: 'public',
          table: 'league_members',
          filter: `league_id=eq.${leagueId}`,
        },
        (payload) => {
          const oldPoints = (payload.old as any)?.total_points ?? 0;
          const newPoints = (payload.new as any)?.total_points ?? 0;
          const delta = newPoints - oldPoints;
          const memberId = (payload.new as any)?.id;

          if (delta !== 0 && memberId) {
            setMemberDeltas((prev) => ({
              ...prev,
              [memberId]: { id: memberId, delta, timestamp: Date.now() },
            }));
            scheduleDeltaClear(memberId, setMemberDeltas);
          }

          setLastUpdated(new Date());
          queryClient.invalidateQueries({ queryKey: ['standings', leagueId] });
        }
      )
      .on(
        'postgres_changes',
        {
          event: 'UPDATE',
          schema: 'public',
          table: 'rosters',
        },
        (payload) => {
          const oldPoints = (payload.old as any)?.points_earned ?? 0;
          const newPoints = (payload.new as any)?.points_earned ?? 0;
          const delta = newPoints - oldPoints;
          const slotId = (payload.new as any)?.id;

          if (delta !== 0 && slotId) {
            setSlotDeltas((prev) => ({
              ...prev,
              [slotId]: { id: slotId, delta, timestamp: Date.now() },
            }));
            scheduleDeltaClear(slotId, setSlotDeltas);
          }

          setLastUpdated(new Date());
          queryClient.invalidateQueries({ queryKey: ['roster', leagueId] });
        }
      )
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
      deltaTimers.current.forEach((t) => window.clearTimeout(t));
      deltaTimers.current = [];
    };
  }, [leagueId, queryClient, scheduleDeltaClear]);

  return {
    lastUpdated,
    memberDeltas,
    slotDeltas,
  };
}
