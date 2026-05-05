import { CURRENT_SEASON, getRosterComposition } from '@sportsnot/types';
import { buildPlayerNameMap, buildTeamNameMap } from '@sportsnot/utils';
import { useMemo } from 'react';
import { useMockLeague } from '../../../mock/hooks/useMockLeagues';
import {
  useDraft,
  useLeagueInfo,
  useLeagueMembers,
  usePlayoffPlayersForDraft,
  usePlayoffTeamsForDraft,
  useRegularSeasonPlayersForDraft,
} from './draftPageQueries';
import {
  buildDraftTurnState,
  buildMyRosterSlots,
  countMemberSlots,
  createDraftedIdSet,
} from './draftPageHelpers';
import { useDraftPoolSync } from './useDraftPoolSync';
import { useDraftRealtimeChannel } from './useDraftRealtimeChannel';
import type {
  DraftMemberRow,
  DraftPickRow,
  DraftRosterComposition,
  DraftStateRow,
  PlayerStatRow,
  RegSeasonStatRow,
  TeamStatRow,
} from './draftPageTypes';

const IS_MOCK = import.meta.env.VITE_MOCK_MODE === 'true';

export function useDraftPageData(leagueId: string, userId: string | undefined) {
  const { data: draftData, isLoading: draftLoading } = useDraft(leagueId);
  const { data: membersData, isLoading: membersLoading } =
    useLeagueMembers(leagueId);
  const { data: leagueInfo, isLoading: leagueInfoLoading } =
    useLeagueInfo(leagueId);
  const mockLeagueResult = useMockLeague(leagueId);
  const members = useMemo(
    () => ((membersData ?? []) as DraftMemberRow[]) ?? [],
    [membersData]
  );
  const draft = (draftData ?? null) as DraftStateRow | null;
  const allowIrSlots = getLeagueSetting(
    mockLeagueResult.data?.allow_ir_slots ?? true,
    leagueInfo?.allowIrSlots ?? true
  );
  const commissionerId = getLeagueSetting(
    mockLeagueResult.data?.commissioner_id ?? null,
    leagueInfo?.commissionerId ?? null
  );
  const roster = getRosterComposition(allowIrSlots) as DraftRosterComposition;
  const currentRound = draft?.round ?? 1;
  const {
    data: playerStatsData,
    isLoading: playerStatsLoading,
    refetch: refetchPlayerStats,
  } = usePlayoffPlayersForDraft(CURRENT_SEASON, currentRound);
  const {
    data: teamStatsData,
    isLoading: teamStatsLoading,
    refetch: refetchTeamStats,
  } = usePlayoffTeamsForDraft(CURRENT_SEASON, currentRound);
  const { data: regSeasonStatsData } =
    useRegularSeasonPlayersForDraft(CURRENT_SEASON);
  const playerStats = useMemo(
    () => (playerStatsData ?? []) as PlayerStatRow[],
    [playerStatsData]
  );
  const teamStats = useMemo(
    () => (teamStatsData ?? []) as TeamStatRow[],
    [teamStatsData]
  );
  const regSeasonStats = useMemo(
    () => (regSeasonStatsData ?? []) as RegSeasonStatRow[],
    [regSeasonStatsData]
  );
  const picks = useMemo(
    () => ((draft?.draft_picks ?? []) as DraftPickRow[]) ?? [],
    [draft?.draft_picks]
  );
  const turnState = useMemo(
    () => buildDraftTurnState(draft, members, userId, commissionerId),
    [commissionerId, draft, members, userId]
  );
  const draftedPlayerIds = useMemo(
    () => createDraftedIdSet(picks, 'player_id'),
    [picks]
  );
  const draftedTeamIds = useMemo(
    () => createDraftedIdSet(picks, 'team_id'),
    [picks]
  );
  const playerNameMap = useMemo(() => {
    const map = buildPlayerNameMap(regSeasonStats);
    for (const [id, name] of buildPlayerNameMap(playerStats)) {
      map.set(id, name);
    }
    return map;
  }, [playerStats, regSeasonStats]);
  const teamNameMap = useMemo(() => buildTeamNameMap(teamStats), [teamStats]);
  const mySlotCounts = useMemo(
    () =>
      countMemberSlots(
        picks,
        (turnState.pickingMember ?? turnState.myMember)?.user_id
      ),
    [picks, turnState.myMember, turnState.pickingMember]
  );
  const myRosterSlots = useMemo(
    () => buildMyRosterSlots(picks, turnState.myMember?.user_id, roster),
    [picks, roster, turnState.myMember?.user_id]
  );

  useDraftRealtimeChannel(leagueId);
  const isDraftPoolSyncing = useDraftPoolSync({
    draft,
    currentSeason: CURRENT_SEASON,
    playerStatsLength: playerStats.length,
    teamStatsLength: teamStats.length,
    refetchPlayerStats,
    refetchTeamStats,
  });

  return {
    draft,
    draftLoading,
    members,
    membersLoading,
    leagueInfoLoading,
    playerStats,
    playerStatsLoading,
    teamStats,
    teamStatsLoading,
    regSeasonStats,
    roster,
    commissionerId,
    allowIrSlots,
    picks,
    draftedPlayerIds,
    draftedTeamIds,
    playerNameMap,
    teamNameMap,
    mySlotCounts,
    myRosterSlots,
    isRound1: currentRound === 1,
    isDraftPoolSyncing,
    ...turnState,
  };
}

function getLeagueSetting<T>(mockValue: T, realValue: T): T {
  return IS_MOCK ? mockValue : realValue;
}
