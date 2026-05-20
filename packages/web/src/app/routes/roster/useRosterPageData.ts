import { useQueryClient } from '@tanstack/react-query';
import { CURRENT_SEASON } from '@sportsnot/types';
import { buildPlayerNameMap, buildTeamNameMap } from '@sportsnot/utils';
import { useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useIsMobile } from '@sportsnot/ui';
import { useAuthContext } from '../../context/AuthContext';
import {
  useLeagueForRoster,
  useMemberRoster,
  usePlayoffPlayersForRoster,
  usePlayoffTeamsForRoster,
  useRegularSeasonPlayersForRoster,
} from './rosterPageQueries';
import type { LeagueMemberRow, RosterSlotRow } from './rosterTypes';
import {
  buildMemberOptions,
  buildPositionOrder,
  buildRosterTitle,
  getRoundPoints,
  getSelectedMemberId,
  groupRosterSlots,
  resolveRosterNavigation,
} from './rosterUtils';
import {
  buildPlayerTeamIdMap,
  computeAliveTeamIds,
  decorateSlotsWithElimination,
  type EliminationMaps,
} from './eliminationUtils';

export function useRosterPageData(leagueId: string, leagueMemberId?: string) {
  const navigate = useNavigate();
  const { user } = useAuthContext();
  const queryClient = useQueryClient();
  const isMobile = useIsMobile();
  const { data, isLoading, error } = useMemberRoster(leagueId, leagueMemberId);
  const currentRound = data?.round ?? 1;
  const memberSelection = useRosterMemberSelection({
    leagueId,
    leagueMemberId,
    navigate,
    userId: user?.id,
  });
  const rosterStats = useRosterStatsData(currentRound);
  const rosterViewState = useRosterViewState({
    currentRound,
    isMobile,
    memberSelection,
    rosterStats,
  });

  return {
    data,
    isLoading,
    error,
    queryClient,
    ...rosterViewState,
  };
}

function useRosterMemberSelection(params: {
  leagueId: string;
  leagueMemberId: string | undefined;
  navigate: ReturnType<typeof useNavigate>;
  userId: string | undefined;
}) {
  const { leagueId, leagueMemberId, navigate, userId } = params;
  const leagueData = useLeagueForRoster(leagueId).data;
  const allowIrSlots = (leagueData?.allow_ir_slots ?? true) as boolean;
  const leagueMembers = getLeagueMembers(leagueData?.league_members);
  const memberState = buildRosterMemberState({
    leagueMembers,
    leagueMemberId,
    userId,
  });
  const rosterTitle = buildRosterTitle(
    memberState.isOwnRoster,
    memberState.viewedMember?.team_name
  );
  const memberOptions = buildMemberOptions(leagueMembers, userId);
  const selectedMemberId = getSelectedMemberId(
    leagueMemberId,
    memberState.myMemberId
  );
  const onMemberChange = useCallback(
    (value: string | null) =>
      navigate(
        resolveRosterNavigation(leagueId, value, memberState.myMemberId)
      ),
    [leagueId, memberState.myMemberId, navigate]
  );

  return {
    allowIrSlots,
    rosterTitle,
    memberOptions,
    selectedMemberId,
    onMemberChange,
    isOwnRoster: memberState.isOwnRoster,
  };
}

function useRosterViewState(params: {
  currentRound: number;
  isMobile: boolean;
  memberSelection: ReturnType<typeof useRosterMemberSelection>;
  rosterStats: ReturnType<typeof useRosterStatsData>;
}) {
  const { currentRound, isMobile, memberSelection, rosterStats } = params;
  const rosterEntityMaps = useRosterEntityMaps(rosterStats);
  const positionOrder = buildPositionOrder(memberSelection.allowIrSlots);

  return {
    isMobile,
    playerStatsLoading: rosterStats.playerStatsLoading,
    ...rosterEntityMaps,
    isOwnRoster: memberSelection.isOwnRoster,
    rosterTitle: memberSelection.rosterTitle,
    positionOrder,
    emptyProps: buildEmptyViewProps(currentRound, memberSelection),
    buildReadyViewProps: (
      slots: RosterSlotRow[],
      round: number,
      totalPoints: number
    ) =>
      createReadyViewProps({
        slots,
        round,
        totalPoints,
        memberOptions: memberSelection.memberOptions,
        selectedMemberId: memberSelection.selectedMemberId,
        onMemberChange: memberSelection.onMemberChange,
        rosterTitle: memberSelection.rosterTitle,
        isOwnRoster: memberSelection.isOwnRoster,
        playerStatsLoading: rosterStats.playerStatsLoading,
        injuredPlayerIds: rosterEntityMaps.injuredPlayerIds,
        playerNameMap: rosterEntityMaps.playerNameMap,
        teamNameMap: rosterEntityMaps.teamNameMap,
        playerTeamAbbreviationMap: rosterEntityMaps.playerTeamAbbreviationMap,
        teamAbbreviationMap: rosterEntityMaps.teamAbbreviationMap,
        eliminationMaps: rosterEntityMaps.eliminationMaps,
        isMobile,
        positionOrder,
      }),
  };
}

function useRosterEntityMaps(
  rosterStats: ReturnType<typeof useRosterStatsData>
) {
  const playerNameMap = useMemo(
    () =>
      buildMergedPlayerNameMap(
        rosterStats.regSeasonStats,
        rosterStats.playerStats
      ),
    [rosterStats.playerStats, rosterStats.regSeasonStats]
  );
  const teamNameMap = useMemo(
    () => buildTeamNameMap(rosterStats.teamStats),
    [rosterStats.teamStats]
  );
  const playerTeamAbbreviationMap = useMemo(
    () =>
      buildPlayerTeamAbbreviationMap(
        rosterStats.regSeasonStats,
        rosterStats.playerStats
      ),
    [rosterStats.playerStats, rosterStats.regSeasonStats]
  );
  const teamAbbreviationMap = useMemo(
    () => buildTeamAbbreviationMap(rosterStats.teamStats),
    [rosterStats.teamStats]
  );
  const injuredPlayerIds = useMemo(
    () => buildInjuredPlayerIds(rosterStats.playerStats),
    [rosterStats.playerStats]
  );
  const eliminationMaps = useMemo<EliminationMaps>(() => {
    const { aliveTeamIds, hasEliminationData } = computeAliveTeamIds({
      round: rosterStats.currentRound,
      currentRoundTeamStats: rosterStats.currentRoundTeamStats,
      nextRoundTeamStats: rosterStats.nextRoundTeamStats,
    });
    const playerTeamIdByPlayerId = buildPlayerTeamIdMap(
      [...rosterStats.playerStats, ...rosterStats.regSeasonStats],
      rosterStats.teamStats,
      rosterStats.currentRoundTeamStats,
      rosterStats.nextRoundTeamStats
    );
    return { aliveTeamIds, playerTeamIdByPlayerId, hasEliminationData };
  }, [
    rosterStats.currentRound,
    rosterStats.currentRoundTeamStats,
    rosterStats.nextRoundTeamStats,
    rosterStats.playerStats,
    rosterStats.regSeasonStats,
    rosterStats.teamStats,
  ]);

  return {
    injuredPlayerIds,
    playerNameMap,
    teamNameMap,
    playerTeamAbbreviationMap,
    teamAbbreviationMap,
    eliminationMaps,
  };
}

function buildEmptyViewProps(
  currentRound: number,
  memberSelection: ReturnType<typeof useRosterMemberSelection>
) {
  return {
    rosterTitle: memberSelection.rosterTitle,
    round: currentRound,
    memberOptions: memberSelection.memberOptions,
    selectedMemberId: memberSelection.selectedMemberId,
    onMemberChange: memberSelection.onMemberChange,
    isOwnRoster: memberSelection.isOwnRoster,
  };
}

function useRosterStatsData(currentRound: number) {
  const nameResolutionRound = currentRound >= 4 ? 3 : currentRound;
  const { data: playerStats, isLoading: playerStatsLoading } =
    usePlayoffPlayersForRoster(CURRENT_SEASON, nameResolutionRound);
  const { data: teamStats } = usePlayoffTeamsForRoster(
    CURRENT_SEASON,
    nameResolutionRound
  );
  const { data: currentRoundTeamStats } = usePlayoffTeamsForRoster(
    CURRENT_SEASON,
    currentRound
  );
  const { data: nextRoundTeamStats } = usePlayoffTeamsForRoster(
    CURRENT_SEASON,
    currentRound + 1
  );
  const { data: regSeasonStats } = useRegularSeasonPlayersForRoster(
    CURRENT_SEASON,
    currentRound === 1
  );

  return {
    playerStats: playerStats ?? [],
    playerStatsLoading,
    teamStats: teamStats ?? [],
    currentRoundTeamStats: currentRoundTeamStats ?? [],
    nextRoundTeamStats: nextRoundTeamStats ?? [],
    regSeasonStats: regSeasonStats ?? [],
    currentRound,
  };
}

function getLeagueMembers(
  leagueMembers: LeagueMemberRow[] | null | undefined
): LeagueMemberRow[] {
  return (leagueMembers ?? []) as LeagueMemberRow[];
}

function buildRosterMemberState(params: {
  leagueMembers: LeagueMemberRow[];
  leagueMemberId: string | undefined;
  userId: string | undefined;
}) {
  const { leagueMembers, leagueMemberId, userId } = params;
  const myMemberId = leagueMembers.find(
    (member) => member.user_id === userId
  )?.id;
  const viewedMember = leagueMemberId
    ? leagueMembers.find((member) => member.id === leagueMemberId)
    : undefined;

  return {
    myMemberId,
    viewedMember,
    isOwnRoster: !leagueMemberId || leagueMemberId === myMemberId,
  };
}

function createReadyViewProps(params: {
  slots: RosterSlotRow[];
  round: number;
  totalPoints: number;
  memberOptions: ReturnType<typeof buildMemberOptions>;
  selectedMemberId: string;
  onMemberChange: (value: string | null) => void;
  rosterTitle: string;
  isOwnRoster: boolean;
  playerStatsLoading: boolean;
  injuredPlayerIds: Set<number>;
  playerNameMap: Map<number, string>;
  teamNameMap: Map<number, string>;
  playerTeamAbbreviationMap: Map<number, string>;
  teamAbbreviationMap: Map<number, string>;
  eliminationMaps: EliminationMaps;
  isMobile: boolean;
  positionOrder: string[];
}) {
  const {
    slots,
    round,
    totalPoints,
    memberOptions,
    selectedMemberId,
    onMemberChange,
    rosterTitle,
    isOwnRoster,
    playerStatsLoading,
    injuredPlayerIds,
    playerNameMap,
    teamNameMap,
    playerTeamAbbreviationMap,
    teamAbbreviationMap,
    eliminationMaps,
    isMobile,
    positionOrder,
  } = params;

  const decoratedSlots = decorateSlotsWithElimination(slots, eliminationMaps);

  return {
    memberOptions,
    selectedMemberId,
    onMemberChange,
    rosterTitle,
    round,
    roundPoints: getRoundPoints(decoratedSlots),
    totalPoints,
    groupedSlots: groupRosterSlots<RosterSlotRow>(
      decoratedSlots,
      positionOrder
    ),
    slots: decoratedSlots,
    isOwnRoster,
    playerStatsLoading,
    injuredPlayerIds,
    playerNameMap,
    teamNameMap,
    playerTeamAbbreviationMap,
    teamAbbreviationMap,
    isMobile,
  };
}

function buildMergedPlayerNameMap(
  regSeasonStats: Array<{ player_id: number; player_name?: string | null }>,
  playerStats: Array<{ player_id: number; player_name?: string | null }>
) {
  const map = buildPlayerNameMap(regSeasonStats);
  for (const [id, name] of buildPlayerNameMap(playerStats)) {
    map.set(id, name);
  }
  return map;
}

function buildPlayerTeamAbbreviationMap(
  regSeasonStats: Array<{
    player_id: number;
    team_abbreviation?: string | null;
  }>,
  playerStats: Array<{ player_id: number; team_abbreviation?: string | null }>
) {
  const map = new Map<number, string>();
  setPlayerTeamAbbreviations(map, regSeasonStats);
  setPlayerTeamAbbreviations(map, playerStats);
  return map;
}

function setPlayerTeamAbbreviations(
  map: Map<number, string>,
  players: Array<{ player_id: number; team_abbreviation?: string | null }>
) {
  for (const player of players) {
    const abbreviation = player.team_abbreviation;
    if (!abbreviation) {
      continue;
    }

    map.set(player.player_id, abbreviation);
  }
}

function buildTeamAbbreviationMap(
  teamStats: Array<{ team_id: number; team_abbreviation?: string | null }>
) {
  const map = new Map<number, string>();
  for (const team of teamStats) {
    if (team.team_abbreviation) {
      map.set(team.team_id, team.team_abbreviation);
    }
  }
  return map;
}

function buildInjuredPlayerIds(
  playerStats: Array<{ player_id: number; is_injured?: boolean | null }>
) {
  const ids = new Set<number>();
  for (const player of playerStats) {
    if (player.is_injured) {
      ids.add(player.player_id);
    }
  }
  return ids;
}
