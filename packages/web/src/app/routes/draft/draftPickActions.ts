import { supabase } from '@sportsnot/supabase';
import { type Position } from '@sportsnot/types';
import { getInitialDraftRosterPoints } from './draftUtils';
import type {
  DraftMemberRow,
  DraftStateRow,
  DraftablePlayer,
  PlayerStatRow,
  TeamStatRow,
} from './draftPageTypes';

const IS_MOCK = import.meta.env.VITE_MOCK_MODE === 'true';

interface SubmitDraftPickParams {
  confirmPlayer: DraftablePlayer;
  confirmPosition: Position;
  draft: DraftStateRow;
  activeMember: DraftMemberRow;
  members: DraftMemberRow[];
  playerStats: PlayerStatRow[];
  teamStats: TeamStatRow[];
  draftOrder: string[];
  mockMakePick: {
    mutate: (args: {
      draftId: string;
      leagueMemberId: string;
      pickNumber: number;
      playerId: number | null;
      teamId: number | null;
      position: Position;
    }) => void;
  };
}

function buildDraftPickSelection(
  confirmPlayer: DraftablePlayer,
  confirmPosition: Position
) {
  const isGoalie = confirmPosition === 'G';

  return {
    playerId: isGoalie ? null : confirmPlayer.id,
    teamId: isGoalie ? confirmPlayer.teamId : null,
    position: confirmPosition,
  };
}

async function duplicateRoundThreeRosters(members: DraftMemberRow[]) {
  const memberIds = members.map((member) => member.id);
  const { data: roundThreeSlots } = await supabase
    .from('rosters')
    .select('*')
    .eq('round', 3)
    .in('league_member_id', memberIds);

  if (!roundThreeSlots || roundThreeSlots.length === 0) {
    return;
  }

  const roundFourSlots = roundThreeSlots.map(
    ({ id: _id, ...slot }: { id: string; [key: string]: unknown }) => ({
      ...slot,
      round: 4,
      points_earned: 0,
    })
  );

  await supabase.from('rosters').insert(roundFourSlots);
}

async function completeDraft(
  draft: DraftStateRow,
  members: DraftMemberRow[],
  nextPick: number
) {
  await supabase
    .from('drafts')
    .update({
      status: 'completed',
      current_pick: nextPick,
      completed_at: new Date().toISOString(),
    })
    .eq('id', draft.id);

  await supabase
    .from('leagues')
    .update({ status: 'active' })
    .eq('id', draft.league_id);

  await supabase.rpc('refresh_league_standings', {
    p_league_id: draft.league_id,
    p_round: draft.round,
  });

  if (draft.round === 3) {
    await duplicateRoundThreeRosters(members);
  }
}

async function insertRosterSlot(
  draft: DraftStateRow,
  activeMember: DraftMemberRow,
  selection: ReturnType<typeof buildDraftPickSelection>,
  pointsEarned: number
) {
  await supabase.from('rosters').insert({
    league_member_id: activeMember.id,
    round: draft.round,
    player_id: selection.playerId,
    team_id: selection.teamId,
    position: selection.position,
    points_earned: pointsEarned,
  });
}

export async function submitDraftPick({
  confirmPlayer,
  confirmPosition,
  draft,
  activeMember,
  members,
  playerStats,
  teamStats,
  draftOrder,
  mockMakePick,
}: SubmitDraftPickParams): Promise<string | null> {
  const selection = buildDraftPickSelection(confirmPlayer, confirmPosition);
  const initialPoints = getInitialDraftRosterPoints({
    playerId: selection.playerId,
    teamId: selection.teamId,
    playoffRound: draft.round,
    playerStats,
    teamStats,
  });

  if (IS_MOCK) {
    mockMakePick.mutate({
      draftId: draft.id,
      leagueMemberId: activeMember.id,
      pickNumber: draft.current_pick,
      playerId: selection.playerId,
      teamId: selection.teamId,
      position: selection.position,
    });
    return null;
  }

  const { error } = await supabase.from('draft_picks').insert({
    draft_id: draft.id,
    league_member_id: activeMember.id,
    pick_number: draft.current_pick,
    player_id: selection.playerId,
    team_id: selection.teamId,
    position: selection.position,
  });

  if (error) {
    return 'Failed to submit pick. Please try again.';
  }

  await insertRosterSlot(draft, activeMember, selection, initialPoints);

  const nextPick = draft.current_pick + 1;
  if (nextPick > draftOrder.length) {
    await completeDraft(draft, members, nextPick);
    return null;
  }

  await supabase
    .from('drafts')
    .update({ current_pick: nextPick })
    .eq('id', draft.id);
  return null;
}
