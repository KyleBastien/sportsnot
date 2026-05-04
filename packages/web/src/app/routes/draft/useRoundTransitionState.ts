import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { supabase } from '@sportsnot/supabase';
import { getRosterComposition } from '@sportsnot/types';
import { useIsMobile } from '@sportsnot/ui';
import { generateSnakeDraftOrder } from '@sportsnot/utils';
import { useCompletedDrafts } from '../../hooks/useCompletedDrafts';
import { deriveCurrentRound, deriveNextRound } from '../../utils/roundUtils';
import { useMockStartReDraft } from '../../../mock/hooks/useMockDraft';
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

/** Sort league members worst-to-best by total_points (tiebreak: team name). */
function sortMembersForReDraft<
  T extends { total_points?: number | null; team_name: string },
>(members: T[]): T[] {
  return [...members].sort((a, b) => {
    const ptsDiff = (a.total_points ?? 0) - (b.total_points ?? 0);
    if (ptsDiff !== 0) return ptsDiff;
    return a.team_name.localeCompare(b.team_name);
  });
}

function getPicksPerMember(allowIrSlots: boolean): number {
  const rosterComp = getRosterComposition(allowIrSlots);
  return (
    rosterComp.forwards +
    rosterComp.defensemen +
    rosterComp.goalies +
    rosterComp.irForwards +
    rosterComp.irDefensemen
  );
}

function buildReDraftOrder(
  memberUserIds: string[],
  allowIrSlots: boolean
): string[] {
  return generateSnakeDraftOrder(
    memberUserIds,
    getPicksPerMember(allowIrSlots)
  );
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
      const reDraftSeedOrder = sortedMembers.map((member) => member.user_id);

      if (IS_MOCK) {
        await mockStartReDraft.mutateAsync({
          leagueId,
          nextRound,
          draftOrder: reDraftSeedOrder,
        });
      } else {
        const reDraftOrder = buildReDraftOrder(
          reDraftSeedOrder,
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
