import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { supabase } from '@sportsnot/supabase';
import { useIsMobile } from '@sportsnot/ui';
import { useCompletedDrafts } from '../../hooks/useCompletedDrafts';
import {
  buildReDraftOrder,
  sortMembersForReDraft,
} from '../../utils/draftOrderUtils';
import { deriveCurrentRound, deriveNextRound } from '../../utils/roundUtils';
import {
  useMockSkipToRound4,
  useMockStartReDraft,
} from '../../../mock/hooks/useMockDraft';
import { useTransitionLeague } from './roundTransitionQueries';

const IS_MOCK = import.meta.env.VITE_MOCK_MODE === 'true';

export interface TransitionMemberRow {
  id: string;
  user_id: string;
  team_name: string;
  total_points: number;
  users?: { display_name?: string } | null;
}

export interface CompletedDraftRow {
  id: string;
  round: number;
  status: string;
  completed_at: string | null;
}

interface RoundTransitionLeague {
  allow_ir_slots?: boolean;
  commissioner_id: string;
  current_round?: number | null;
  league_members?: TransitionMemberRow[] | null;
  name: string;
}

async function insertReDraft(
  leagueId: string,
  nextRound: number,
  draftOrder: string[]
): Promise<void> {
  const { error: draftError } = await supabase.from('drafts').insert({
    league_id: leagueId,
    round: nextRound,
    status: 'active',
    current_pick: 1,
    draft_order: draftOrder,
    started_at: new Date().toISOString(),
  });

  if (draftError) {
    throw draftError;
  }

  const { error: leagueError } = await supabase
    .from('leagues')
    .update({ status: 'drafting', current_round: nextRound })
    .eq('id', leagueId);

  if (leagueError) {
    throw leagueError;
  }
}

async function ensureRoundFourRosters(
  leagueMemberIds: string[]
): Promise<void> {
  if (leagueMemberIds.length === 0) return;

  const { data: roundFourRows, error: roundFourError } = await supabase
    .from('rosters')
    .select('league_member_id')
    .eq('round', 4)
    .in('league_member_id', leagueMemberIds);

  if (roundFourError) {
    throw roundFourError;
  }

  const existing = new Set(
    (roundFourRows ?? []).map((row) => row.league_member_id as string)
  );
  const missingMemberIds = leagueMemberIds.filter((id) => !existing.has(id));
  if (missingMemberIds.length === 0) return;

  const { data: roundThreeRows, error: roundThreeError } = await supabase
    .from('rosters')
    .select('*')
    .eq('round', 3)
    .in('league_member_id', missingMemberIds);

  if (roundThreeError) {
    throw roundThreeError;
  }

  if (!roundThreeRows || roundThreeRows.length === 0) return;

  const roundFourSlots = roundThreeRows.map(({ id: _id, ...slot }) => ({
    ...slot,
    round: 4,
    points_earned: 0,
  }));

  const { error: insertError } = await supabase
    .from('rosters')
    .insert(roundFourSlots as unknown as Record<string, unknown>[]);

  if (insertError) {
    throw insertError;
  }
}

async function advanceToRound4(leagueId: string): Promise<void> {
  const { error: leagueError } = await supabase
    .from('leagues')
    .update({ status: 'active', current_round: 4 })
    .eq('id', leagueId);

  if (leagueError) {
    throw leagueError;
  }
}

export function useRoundTransitionState(
  leagueId: string | undefined,
  userId: string | undefined
) {
  const navigate = useNavigate();
  const [starting, setStarting] = useState(false);
  const {
    data: leagueData,
    isLoading: leagueLoading,
    error,
  } = useTransitionLeague(leagueId);
  const { data: completedDraftsData, isLoading: completedDraftsLoading } =
    useCompletedDrafts(leagueId);
  const mockStartReDraft = useMockStartReDraft();
  const mockSkipToRound4 = useMockSkipToRound4();
  const isMobile = useIsMobile();

  const league = leagueData as RoundTransitionLeague | null | undefined;
  const completedDrafts = (completedDraftsData ?? []) as CompletedDraftRow[];
  const completedCount = completedDrafts.length;
  const currentRound = deriveCurrentRound(
    league?.current_round,
    completedCount
  );
  const nextRound = deriveNextRound(league?.current_round, completedCount);
  const sortedMembers = sortMembersForReDraft(
    (league?.league_members ?? []) as TransitionMemberRow[]
  );
  const isCommissioner = league?.commissioner_id === userId;

  const startReDraft = async () => {
    if (!leagueId) return;
    if (!league) return;
    if (sortedMembers.length < 2) return;

    setStarting(true);

    try {
      const isRoundFourAdvance = nextRound === 4;

      if (isRoundFourAdvance) {
        if (IS_MOCK) {
          await mockSkipToRound4.mutateAsync({ leagueId });
        } else {
          const leagueMemberIds = sortedMembers.map((member) => member.id);
          await ensureRoundFourRosters(leagueMemberIds);
          await advanceToRound4(leagueId);
        }

        navigate(`/leagues/${leagueId}`);
        return;
      }

      const reDraftSeedOrder = sortedMembers.map((member) => member.user_id);

      if (IS_MOCK) {
        await mockStartReDraft.mutateAsync({
          leagueId,
          nextRound,
          draftOrder: reDraftSeedOrder,
        });
      } else {
        const reDraftOrder = buildReDraftOrder(
          sortedMembers,
          league.allow_ir_slots ?? true
        );
        await insertReDraft(leagueId, nextRound, reDraftOrder);
      }

      navigate(`/draft/${leagueId}`);
    } finally {
      setStarting(false);
    }
  };

  return {
    backToLeague: () => navigate(`/leagues/${leagueId}`),
    completedDrafts,
    currentRound,
    error,
    isCommissioner,
    isLoading: leagueLoading || completedDraftsLoading,
    isMobile,
    league,
    nextRound,
    sortedMembers,
    startReDraft,
    starting,
  };
}
