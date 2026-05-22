import { useQueryClient } from '@tanstack/react-query';
import { CURRENT_SEASON } from '@sportsnot/types';
import { buildPlayerNameMap, buildTeamNameMap } from '@sportsnot/utils';
import { useCallback, useMemo } from 'react';
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { useIsMobile } from '@sportsnot/ui';
import { useAuthContext } from '../../context/AuthContext';
import { buildRoundSearch, clampRoundSelection } from '../../utils/roundUtils';
import {
  buildPlayerTeamAbbreviationMap,
  buildTeamAbbreviationMap,
} from '../../utils/teamLookupMaps';
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
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const { user } = useAuthContext();
  const queryClient = useQueryClient();
  const isMobile = useIsMobile();
  const requestedRoundParam = searchParams.get('round');
  const requestedRound = requestedRoundParam
    ? Number.parseInt(requestedRoundParam, 10)
    : undefined;
  const { data, isLoading, error } = useMemberRoster(
    leagueId,
    leagueMemberId,
    requestedRound
  );
  const currentRound = data?.currentRound ?? 1;
  const selectedRound =
    data?.round ?? clampRoundSelection(requestedRound, currentRound);
  const roundSelection = useRosterRoundSelection({
    currentRound,
    selectedRound,
    navigate,
    pathname: location.pathname,
  });
  const memberSelection = useRosterMemberSelection({
    leagueId,
    leagueMemberId,
    navigate,
    roundSearch: roundSelection.roundSearch,
    userId: user?.id,
  });
  const rosterStats = useRosterStatsData(selectedRound);
  const rosterViewState = useRosterViewState({
    currentRound,
    isMobile,
    memberSelection,
    roundSelection,
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
  roundSearch: string;
  userId: string | undefined;
}) {
  const { leagueId, leagueMemberId, navigate, roundSearch, userId } = params;
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
        `${resolveRosterNavigation(leagueId, value, memberState.myMemberId)}${roundSearch}`
      ),
    [leagueId, memberState.myMemberId, navigate, roundSearch]
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

function useRosterRoundSelection(params: {
  currentRound: number;
  selectedRound: number;
  navigate: ReturnType<typeof useNavigate>;
  pathname: string;
}) {
  const { currentRound, selectedRound, navigate, pathname } = params;
  const roundSearch = buildRoundSearch(selectedRound, currentRound);
  const onRoundChange = useCallback(
    (value: string) => {
      const nextRound = clampRoundSelection(value, currentRound);
      navigate(`${pathname}${buildRoundSearch(nextRound, currentRound)}`, {
        replace: true,
      });
    },
    [currentRound, navigate, pathname]
  );

  return {
    currentRound,
    selectedRound,
    roundSearch,
    onRoundChange,
    isHistorical: selectedRound !== currentRound,
  };
}

function useRosterViewState(params: {
  currentRound: number;
  isMobile: boolean;
  memberSelection: ReturnType<typeof useRosterMemberSelection>;
  roundSelection: ReturnType<typeof useRosterRoundSelection>;
  rosterStats: ReturnType<typeof useRosterStatsData>;
}) {
  const {
    currentRound,
    isMobile,
    memberSelection,
    roundSelection,
    rosterStats,
  } = params;
  const rosterEntityMaps = useRosterEntityMaps(rosterStats);
  const positionOrder = buildPositionOrder(memberSelection.allowIrSlots);

  return {
    isMobile,
    playerStatsLoading: rosterStats.playerStatsLoading,
    ...rosterEntityMaps,
    isOwnRoster: memberSelection.isOwnRoster,
    rosterTitle: memberSelection.rosterTitle,
    positionOrder,
    emptyProps: buildEmptyViewProps(roundSelection, memberSelection),
    buildReadyViewProps: (
      slots: RosterSlotRow[],
      round: number,
      totalPoints: number
    ) =>
      createReadyViewProps({
        slots,
        round,
        currentRound,
        totalPoints,
        memberOptions: memberSelection.memberOptions,
        selectedMemberId: memberSelection.selectedMemberId,
        onMemberChange: memberSelection.onMemberChange,
        onRoundChange: roundSelection.onRoundChange,
        rosterTitle: memberSelection.rosterTitle,
        isOwnRoster: memberSelection.isOwnRoster,
        isHistorical: roundSelection.isHistorical,
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
  roundSelection: ReturnType<typeof useRosterRoundSelection>,
  memberSelection: ReturnType<typeof useRosterMemberSelection>
) {
  return {
    rosterTitle: memberSelection.rosterTitle,
    round: roundSelection.selectedRound,
    currentRound: roundSelection.currentRound,
    memberOptions: memberSelection.memberOptions,
    selectedMemberId: memberSelection.selectedMemberId,
    onMemberChange: memberSelection.onMemberChange,
    isOwnRoster: memberSelection.isOwnRoster,
    onRoundChange: roundSelection.onRoundChange,
    isHistorical: roundSelection.isHistorical,
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
  currentRound: number;
  totalPoints: number;
  memberOptions: ReturnType<typeof buildMemberOptions>;
  selectedMemberId: string;
  onMemberChange: (value: string | null) => void;
  onRoundChange: (value: string) => void;
  rosterTitle: string;
  isOwnRoster: boolean;
  isHistorical: boolean;
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
    currentRound,
    totalPoints,
    memberOptions,
    selectedMemberId,
    onMemberChange,
    onRoundChange,
    rosterTitle,
    isOwnRoster,
    isHistorical,
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
  const rosterSelectionProps = {
    memberOptions,
    selectedMemberId,
    onMemberChange,
    rosterTitle,
    round,
    currentRound,
    onRoundChange,
    totalPoints,
    isOwnRoster,
    isHistorical,
  };
  const rosterEntityProps = {
    playerStatsLoading,
    injuredPlayerIds,
    playerNameMap,
    teamNameMap,
    playerTeamAbbreviationMap,
    teamAbbreviationMap,
    isMobile,
  };

  return {
    ...rosterSelectionProps,
    roundPoints: getRoundPoints(decoratedSlots),
    groupedSlots: groupRosterSlots<RosterSlotRow>(
      decoratedSlots,
      positionOrder
    ),
    slots: decoratedSlots,
    canManageRoster: isOwnRoster && !isHistorical,
    ...rosterEntityProps,
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
