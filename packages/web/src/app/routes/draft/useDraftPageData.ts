import { CURRENT_SEASON, getRosterComposition } from '@sportsnot/types';
import { buildPlayerNameMap, buildTeamNameMap } from '@sportsnot/utils';
import { useMemo } from 'react';
import { useMockLeague } from '../../../mock/hooks/useMockLeagues';
import {
  useCumulativePlayoffPlayersForDraft,
  useCumulativePlayoffTeamsForDraft,
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
  const leagueData = useDraftLeagueData(leagueId);
  const currentRound = leagueData.draft?.round ?? 1;
  const roster = getRosterComposition(
    leagueData.allowIrSlots
  ) as DraftRosterComposition;
  const statData = useDraftStatData(currentRound);
  const draftState = useDraftDerivedState({
    draft: leagueData.draft,
    members: leagueData.members,
    userId,
    commissionerId: leagueData.commissionerId,
    playerStats: statData.playerStats,
    teamStats: statData.teamStats,
    regSeasonStats: statData.regSeasonStats,
    roster,
  });

  useDraftRealtimeChannel(leagueId);
  const isDraftPoolSyncing = useDraftPoolSync({
    draft: leagueData.draft,
    currentSeason: CURRENT_SEASON,
    playerStatsLength: statData.playerStats.length,
    teamStatsLength: statData.teamStats.length,
    refetchPlayerStats: statData.refetchPlayerStats,
    refetchTeamStats: statData.refetchTeamStats,
  });

  return {
    ...leagueData,
    ...statData,
    roster,
    isRound1: currentRound === 1,
    isDraftPoolSyncing,
    ...draftState,
  };
}

function getLeagueSetting<T>(mockValue: T, realValue: T): T {
  return IS_MOCK ? mockValue : realValue;
}

function useDraftLeagueData(leagueId: string) {
  const { data: draftData, isLoading: draftLoading } = useDraft(leagueId);
  const { data: membersData, isLoading: membersLoading } =
    useLeagueMembers(leagueId);
  const { data: leagueInfo, isLoading: leagueInfoLoading } =
    useLeagueInfo(leagueId);
  const mockLeagueResult = useMockLeague(leagueId);
  const members = useMemo(
    () => (membersData ?? []) as DraftMemberRow[],
    [membersData]
  );
  const draft = (draftData ?? null) as DraftStateRow | null;

  return {
    draft,
    draftLoading,
    members,
    membersLoading,
    leagueInfoLoading,
    allowIrSlots: getLeagueSetting(
      mockLeagueResult.data?.allow_ir_slots ?? true,
      leagueInfo?.allowIrSlots ?? true
    ),
    commissionerId: getLeagueSetting(
      mockLeagueResult.data?.commissioner_id ?? null,
      leagueInfo?.commissionerId ?? null
    ),
  };
}

function useDraftStatData(currentRound: number) {
  const {
    data: playerStatsData,
    isLoading: playerStatsLoading,
    refetch: refetchPlayerStats,
  } = usePlayoffPlayersForDraft(CURRENT_SEASON, currentRound);
  const {
    data: cumulativePlayerStatsData,
    isLoading: cumulativePlayerStatsLoading,
  } = useCumulativePlayoffPlayersForDraft(CURRENT_SEASON, currentRound);
  const {
    data: teamStatsData,
    isLoading: teamStatsLoading,
    refetch: refetchTeamStats,
  } = usePlayoffTeamsForDraft(CURRENT_SEASON, currentRound);
  const {
    data: cumulativeTeamStatsData,
    isLoading: cumulativeTeamStatsLoading,
  } = useCumulativePlayoffTeamsForDraft(CURRENT_SEASON, currentRound);
  const { data: regSeasonStatsData } =
    useRegularSeasonPlayersForDraft(CURRENT_SEASON);

  return {
    playerStats: useMemo(
      () => (playerStatsData ?? []) as PlayerStatRow[],
      [playerStatsData]
    ),
    playerStatsLoading,
    cumulativePlayerStats: useMemo(
      () => (cumulativePlayerStatsData ?? []) as PlayerStatRow[],
      [cumulativePlayerStatsData]
    ),
    cumulativePlayerStatsLoading,
    teamStats: useMemo(
      () => (teamStatsData ?? []) as TeamStatRow[],
      [teamStatsData]
    ),
    teamStatsLoading,
    cumulativeTeamStats: useMemo(
      () => (cumulativeTeamStatsData ?? []) as TeamStatRow[],
      [cumulativeTeamStatsData]
    ),
    cumulativeTeamStatsLoading,
    regSeasonStats: useMemo(
      () => (regSeasonStatsData ?? []) as RegSeasonStatRow[],
      [regSeasonStatsData]
    ),
    refetchPlayerStats,
    refetchTeamStats,
  };
}

function useDraftDerivedState(params: {
  draft: DraftStateRow | null;
  members: DraftMemberRow[];
  userId: string | undefined;
  commissionerId: string | null;
  playerStats: PlayerStatRow[];
  teamStats: TeamStatRow[];
  regSeasonStats: RegSeasonStatRow[];
  roster: DraftRosterComposition;
}) {
  const {
    draft,
    members,
    userId,
    commissionerId,
    playerStats,
    teamStats,
    regSeasonStats,
    roster,
  } = params;
  const picks = useMemo(
    () => (draft?.draft_picks ?? []) as DraftPickRow[],
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
  const playerNameMap = useMemo(
    () => buildDraftPlayerNameMap(regSeasonStats, playerStats),
    [playerStats, regSeasonStats]
  );
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

  return {
    picks,
    draftedPlayerIds,
    draftedTeamIds,
    playerNameMap,
    teamNameMap,
    mySlotCounts,
    myRosterSlots,
    ...turnState,
  };
}

function buildDraftPlayerNameMap(
  regSeasonStats: RegSeasonStatRow[],
  playerStats: PlayerStatRow[]
) {
  const map = buildPlayerNameMap(regSeasonStats);
  for (const [id, name] of buildPlayerNameMap(playerStats)) {
    map.set(id, name);
  }
  return map;
}
