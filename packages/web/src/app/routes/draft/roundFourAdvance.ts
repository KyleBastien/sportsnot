import { supabase } from '@sportsnot/supabase';

async function loadRosterMemberIdsForRound(
  round: number,
  leagueMemberIds: string[]
): Promise<Set<string>> {
  const { data, error } = await supabase
    .from('rosters')
    .select('league_member_id')
    .eq('round', round)
    .in('league_member_id', leagueMemberIds);

  if (error) {
    throw error;
  }

  return new Set((data ?? []).map((row) => row.league_member_id as string));
}

async function loadRosterRowsForRound(
  round: number,
  leagueMemberIds: string[]
): Promise<Record<string, unknown>[]> {
  const { data, error } = await supabase
    .from('rosters')
    .select('*')
    .eq('round', round)
    .in('league_member_id', leagueMemberIds);

  if (error) {
    throw error;
  }

  return (data ?? []) as unknown as Record<string, unknown>[];
}

function buildRoundFourSlots(
  roundThreeRows: Record<string, unknown>[]
): Record<string, unknown>[] {
  return roundThreeRows.map(({ id: _id, ...slot }) => ({
    ...slot,
    round: 4,
    points_earned: 0,
  }));
}

async function insertRosterSlots(
  slots: Record<string, unknown>[]
): Promise<void> {
  if (slots.length === 0) return;

  const { error } = await supabase.from('rosters').insert(slots);

  if (error) {
    throw error;
  }
}

export async function ensureRoundFourRosters(
  leagueMemberIds: string[]
): Promise<void> {
  if (leagueMemberIds.length === 0) return;

  const roundFourExisting = await loadRosterMemberIdsForRound(
    4,
    leagueMemberIds
  );
  const missingMemberIds = leagueMemberIds.filter(
    (id) => !roundFourExisting.has(id)
  );
  if (missingMemberIds.length === 0) return;

  const roundThreeRows = await loadRosterRowsForRound(3, missingMemberIds);
  if (roundThreeRows.length === 0) return;

  await insertRosterSlots(buildRoundFourSlots(roundThreeRows));
}

export async function advanceLeagueToRound4(params: {
  leagueId: string;
  leagueMemberIds: string[];
}): Promise<void> {
  await ensureRoundFourRosters(params.leagueMemberIds);

  const { error } = await supabase
    .from('leagues')
    .update({ status: 'active', current_round: 4 })
    .eq('id', params.leagueId);

  if (error) {
    throw error;
  }
}
