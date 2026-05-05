import { useQueryClient } from '@tanstack/react-query';
import { CURRENT_SEASON } from '@sportsnot/types';
import { buildPlayerNameMap, buildTeamNameMap } from '@sportsnot/utils';
import { useMemo } from 'react';
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

export function useRosterPageData(leagueId: string, leagueMemberId?: string) {
  const navigate = useNavigate();
  const { user } = useAuthContext();
  const queryClient = useQueryClient();
  const isMobile = useIsMobile();
  const { data, isLoading, error } = useMemberRoster(leagueId, leagueMemberId);
  const leagueResult = useLeagueForRoster(leagueId);
  const leagueData = leagueResult.data;
  const allowIrSlots = (leagueData?.allow_ir_slots ?? true) as boolean;
  const leagueMembers =
    ((leagueData?.league_members ?? []) as LeagueMemberRow[]) ?? [];
  const myMemberId = leagueMembers.find(
    (member) => member.user_id === user?.id
  )?.id;
  const isOwnRoster = !leagueMemberId || leagueMemberId === myMemberId;
  const viewedMember = leagueMemberId
    ? leagueMembers.find((member) => member.id === leagueMemberId)
    : undefined;
  const currentRound = data?.round ?? 1;
  const nameResolutionRound = currentRound >= 4 ? 3 : currentRound;
  const { data: playerStats, isLoading: playerStatsLoading } =
    usePlayoffPlayersForRoster(CURRENT_SEASON, nameResolutionRound);
  const { data: teamStats } = usePlayoffTeamsForRoster(
    CURRENT_SEASON,
    nameResolutionRound
  );
  const { data: regSeasonStats } = useRegularSeasonPlayersForRoster(
    CURRENT_SEASON,
    currentRound === 1
  );
  const playerNameMap = useMemo(() => {
    const map = buildPlayerNameMap(regSeasonStats ?? []);
    for (const [id, name] of buildPlayerNameMap(playerStats ?? [])) {
      map.set(id, name);
    }
    return map;
  }, [playerStats, regSeasonStats]);
  const teamNameMap = useMemo(
    () => buildTeamNameMap(teamStats ?? []),
    [teamStats]
  );
  const playerTeamAbbreviationMap = useMemo(
    () =>
      buildPlayerTeamAbbreviationMap(regSeasonStats ?? [], playerStats ?? []),
    [playerStats, regSeasonStats]
  );
  const teamAbbreviationMap = useMemo(
    () => buildTeamAbbreviationMap(teamStats ?? []),
    [teamStats]
  );
  const injuredPlayerIds = useMemo(
    () => buildInjuredPlayerIds(playerStats ?? []),
    [playerStats]
  );

  return {
    data,
    isLoading,
    error,
    queryClient,
    isMobile: useIsMobile(),
    playerStatsLoading,
    injuredPlayerIds,
    playerNameMap,
    teamNameMap,
    playerTeamAbbreviationMap,
    teamAbbreviationMap,
    isOwnRoster,
    rosterTitle: buildRosterTitle(isOwnRoster, viewedMember?.team_name),
    positionOrder: buildPositionOrder(allowIrSlots),
    emptyProps: {
      rosterTitle: buildRosterTitle(isOwnRoster, viewedMember?.team_name),
      round: data?.round ?? 1,
      memberOptions: buildMemberOptions(leagueMembers, user?.id),
      selectedMemberId: getSelectedMemberId(leagueMemberId, myMemberId),
      onMemberChange: (value: string | null) =>
        navigate(resolveRosterNavigation(leagueId, value, myMemberId)),
      isOwnRoster,
    },
    buildReadyViewProps: (
      slots: RosterSlotRow[],
      round: number,
      totalPoints: number
    ) => ({
      memberOptions: buildMemberOptions(leagueMembers, user?.id),
      selectedMemberId: getSelectedMemberId(leagueMemberId, myMemberId),
      onMemberChange: (value: string | null) =>
        navigate(resolveRosterNavigation(leagueId, value, myMemberId)),
      rosterTitle: buildRosterTitle(isOwnRoster, viewedMember?.team_name),
      round,
      roundPoints: getRoundPoints(slots),
      totalPoints,
      groupedSlots: groupRosterSlots<RosterSlotRow>(
        slots,
        buildPositionOrder(allowIrSlots)
      ),
      slots,
      isOwnRoster,
      playerStatsLoading,
      injuredPlayerIds,
      playerNameMap,
      teamNameMap,
      playerTeamAbbreviationMap,
      teamAbbreviationMap,
      isMobile,
    }),
  };
}

function buildPlayerTeamAbbreviationMap(
  regSeasonStats: Array<{
    player_id: number;
    team_abbreviation?: string | null;
  }>,
  playerStats: Array<{ player_id: number; team_abbreviation?: string | null }>
) {
  const map = new Map<number, string>();
  for (const player of regSeasonStats) {
    if (player.team_abbreviation) {
      map.set(player.player_id, player.team_abbreviation);
    }
  }
  for (const player of playerStats) {
    if (player.team_abbreviation) {
      map.set(player.player_id, player.team_abbreviation);
    }
  }
  return map;
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
