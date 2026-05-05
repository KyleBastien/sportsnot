import { useQueryClient } from '@tanstack/react-query';
import { supabase } from '@sportsnot/supabase';
import { CURRENT_SEASON } from '@sportsnot/types';
import { buildPlayerNameMap, buildTeamNameMap } from '@sportsnot/utils';
import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useIsMobile } from '@sportsnot/ui';
import { useMockActivateIR } from '../../../mock/hooks/useMockRoster';
import { useAuthContext } from '../../context/AuthContext';
import {
  useLeagueForRoster,
  useMemberRoster,
  usePlayoffPlayersForRoster,
  usePlayoffTeamsForRoster,
  useRegularSeasonPlayersForRoster,
} from './rosterPageQueries';
import type {
  IrModalState,
  LeagueMemberRow,
  RosterSlotRow,
} from './rosterTypes';
import {
  buildMemberOptions,
  buildPositionOrder,
  buildRosterTitle,
  getRoundPoints,
  getSelectedMemberId,
  groupRosterSlots,
  resolveRosterNavigation,
} from './rosterUtils';

const IS_MOCK = import.meta.env.VITE_MOCK_MODE === 'true';

interface UseRosterPageControllerParams {
  leagueId: string;
  leagueMemberId?: string;
}

export function useRosterPageController({
  leagueId,
  leagueMemberId,
}: UseRosterPageControllerParams) {
  const navigate = useNavigate();
  const { user } = useAuthContext();
  const { data, isLoading, error } = useMemberRoster(leagueId, leagueMemberId);
  const queryClient = useQueryClient();

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
  const rosterTitle = buildRosterTitle(isOwnRoster, viewedMember?.team_name);
  const positionOrder = buildPositionOrder(allowIrSlots);

  const [irModal, setIrModal] = useState<IrModalState | null>(null);
  const [selectedInjuredSlotId, setSelectedInjuredSlotId] = useState<
    string | null
  >(null);
  const [activating, setActivating] = useState(false);
  const mockActivateIR = useMockActivateIR();
  const isMobile = useIsMobile();

  const currentSeason = CURRENT_SEASON;
  const currentRound = data?.round ?? 1;
  const nameResolutionRound = currentRound >= 4 ? 3 : currentRound;
  const { data: playerStats, isLoading: playerStatsLoading } =
    usePlayoffPlayersForRoster(currentSeason, nameResolutionRound);
  const { data: teamStats } = usePlayoffTeamsForRoster(
    currentSeason,
    nameResolutionRound
  );
  const isRound1 = currentRound === 1;
  const { data: regSeasonStats } = useRegularSeasonPlayersForRoster(
    currentSeason,
    isRound1
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

  const playerTeamAbbreviationMap = useMemo(() => {
    const map = new Map<number, string>();
    for (const player of regSeasonStats ?? []) {
      if (player.team_abbreviation) {
        map.set(player.player_id, player.team_abbreviation);
      }
    }
    for (const player of playerStats ?? []) {
      if (player.team_abbreviation) {
        map.set(player.player_id, player.team_abbreviation);
      }
    }
    return map;
  }, [playerStats, regSeasonStats]);

  const teamAbbreviationMap = useMemo(() => {
    const map = new Map<number, string>();
    for (const team of teamStats ?? []) {
      if (team.team_abbreviation) {
        map.set(team.team_id, team.team_abbreviation);
      }
    }
    return map;
  }, [teamStats]);

  const injuredPlayerIds = useMemo(() => {
    const ids = new Set<number>();
    for (const player of playerStats ?? []) {
      if (player.is_injured) {
        ids.add(player.player_id);
      }
    }
    return ids;
  }, [playerStats]);

  const status = isLoading ? 'loading' : error || !data ? 'error' : 'ready';

  if (status !== 'ready') {
    return { status } as const;
  }

  const { slots, round } = data;
  const memberOptions = buildMemberOptions(leagueMembers, user?.id);
  const selectedMemberId = getSelectedMemberId(leagueMemberId, myMemberId);

  if (slots.length === 0) {
    return {
      status: 'empty' as const,
      emptyProps: {
        rosterTitle,
        round,
        memberOptions,
        selectedMemberId,
        onMemberChange: (value: string | null) =>
          navigate(resolveRosterNavigation(leagueId, value, myMemberId)),
        isOwnRoster,
      },
    };
  }

  const groupedSlots = groupRosterSlots<RosterSlotRow>(slots, positionOrder);
  const roundPoints = getRoundPoints(slots);
  const totalPoints = data.totalPoints ?? 0;

  const handleActivateIR = async () => {
    if (!irModal || !selectedInjuredSlotId) {
      return;
    }

    setActivating(true);

    if (IS_MOCK) {
      mockActivateIR.mutate({
        leagueMemberId: data.memberId,
        slotId: irModal.irSlotId,
      });
      setActivating(false);
      setIrModal(null);
      setSelectedInjuredSlotId(null);
      return;
    }

    const { error: activateError } = await supabase.rpc('activate_ir_player', {
      p_league_member_id: data.memberId,
      p_round: round,
      p_injured_roster_id: selectedInjuredSlotId,
      p_ir_roster_id: irModal.irSlotId,
    });

    if (!activateError) {
      queryClient.invalidateQueries({ queryKey: ['roster', leagueId] });
    }

    setActivating(false);
    setIrModal(null);
    setSelectedInjuredSlotId(null);
  };

  return {
    status: 'ready' as const,
    viewProps: {
      memberOptions,
      selectedMemberId,
      onMemberChange: (value: string | null) =>
        navigate(resolveRosterNavigation(leagueId, value, myMemberId)),
      rosterTitle,
      round,
      roundPoints,
      totalPoints,
      groupedSlots,
      slots,
      isOwnRoster,
      playerStatsLoading,
      injuredPlayerIds,
      playerNameMap,
      teamNameMap,
      playerTeamAbbreviationMap,
      teamAbbreviationMap,
      isMobile,
      onOpenIrModal: (slotId: string, candidates: RosterSlotRow[]) => {
        setIrModal({ irSlotId: slotId, candidates });
        setSelectedInjuredSlotId(candidates[0]?.id ?? null);
      },
      irModal,
      selectedInjuredSlotId,
      onSelectedInjuredSlotIdChange: setSelectedInjuredSlotId,
      onCloseIrModal: () => {
        setIrModal(null);
        setSelectedInjuredSlotId(null);
      },
      onActivateIr: handleActivateIR,
      activating,
    },
  };
}
