import { useDisclosure } from '@mantine/hooks';
import { supabase } from '@sportsnot/supabase';
import {
  CURRENT_SEASON,
  getRosterComposition,
  type Position,
} from '@sportsnot/types';
import { buildPlayerNameMap, buildTeamNameMap } from '@sportsnot/utils';
import { useEffect, useMemo, useRef, useState } from 'react';
import { routes } from '../../utils/routes';
import { useMockMakePick } from '../../../mock/hooks/useMockDraft';
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
  buildMyRosterSlots,
  buildDraftTurnState,
  countMemberSlots,
  createDraftedIdSet,
  getDefaultConfirmPosition,
  removeComparedPlayer,
  toggleComparePlayers,
} from './draftPageHelpers';
import { submitDraftPick } from './draftPickActions';
import type {
  ComparePlayer,
  DraftMemberRow,
  DraftPickRow,
  DraftRosterComposition,
  DraftStateRow,
  DraftablePlayer,
  PlayerStatRow,
  RegSeasonStatRow,
  TeamStatRow,
} from './draftPageTypes';

interface UseDraftPageControllerParams {
  leagueId: string;
  userId: string | undefined;
  navigate: (path: string) => void;
}

export function useDraftPageController({
  leagueId,
  userId,
  navigate,
}: UseDraftPageControllerParams) {
  const { data: draftData, isLoading: draftLoading } = useDraft(leagueId);
  const { data: membersData, isLoading: membersLoading } =
    useLeagueMembers(leagueId);
  const { data: leagueInfo, isLoading: leagueInfoLoading } =
    useLeagueInfo(leagueId);
  const mockLeagueResult = useMockLeague(leagueId);
  const commissionerId =
    import.meta.env.VITE_MOCK_MODE === 'true'
      ? (mockLeagueResult.data?.commissioner_id ?? null)
      : (leagueInfo?.commissionerId ?? null);
  const allowIrSlots =
    import.meta.env.VITE_MOCK_MODE === 'true'
      ? (mockLeagueResult.data?.allow_ir_slots ?? true)
      : (leagueInfo?.allowIrSlots ?? true);
  const roster = getRosterComposition(allowIrSlots) as DraftRosterComposition;
  const [positionFilter, setPositionFilter] = useState('ALL');
  const [searchQuery, setSearchQuery] = useState('');
  const [confirmPlayer, setConfirmPlayer] = useState<DraftablePlayer | null>(
    null
  );
  const [confirmPosition, setConfirmPosition] = useState<Position>('F');
  const [submitting, setSubmitting] = useState(false);
  const [pickError, setPickError] = useState<string | null>(null);
  const [comparePlayers, setComparePlayers] = useState<ComparePlayer[]>([]);
  const [myTeamOpened, { toggle: toggleMyTeam }] = useDisclosure(false);
  const draftPoolSyncDraftIdRef = useRef<string | null>(null);
  const [isDraftPoolSyncing, setIsDraftPoolSyncing] = useState(false);
  const mockMakePick = useMockMakePick();

  const draft = (draftData ?? null) as DraftStateRow | null;
  const members = useMemo(
    () => ((membersData ?? []) as DraftMemberRow[]) ?? [],
    [membersData]
  );
  const currentSeason = CURRENT_SEASON;
  const currentRound = draft?.round ?? 1;
  const {
    data: playerStatsData,
    isLoading: playerStatsLoading,
    refetch: refetchPlayerStats,
  } = usePlayoffPlayersForDraft(currentSeason, currentRound);
  const {
    data: teamStatsData,
    isLoading: teamStatsLoading,
    refetch: refetchTeamStats,
  } = usePlayoffTeamsForDraft(currentSeason, currentRound);
  const isRound1 = currentRound === 1;
  const { data: regSeasonStatsData } =
    useRegularSeasonPlayersForDraft(currentSeason);

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
  const {
    draftOrder,
    isDraftComplete,
    currentPicker,
    isMyTurn,
    myMember,
    isCommissioner,
    canPick,
    pickingMember,
  } = useMemo(
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
    () => countMemberSlots(picks, (pickingMember ?? myMember)?.user_id),
    [myMember, pickingMember, picks]
  );
  const myRosterSlots = useMemo(
    () => buildMyRosterSlots(picks, myMember?.user_id, roster),
    [myMember?.user_id, picks, roster]
  );

  useEffect(() => {
    if (import.meta.env.VITE_MOCK_MODE === 'true') {
      return;
    }

    const channel = supabase
      .channel(`draft-${leagueId}`)
      .on(
        'postgres_changes',
        { event: '*', schema: 'public', table: 'draft_picks' },
        () => undefined
      )
      .on(
        'postgres_changes',
        { event: '*', schema: 'public', table: 'drafts' },
        () => undefined
      )
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, [leagueId]);

  useEffect(() => {
    if (
      import.meta.env.VITE_MOCK_MODE === 'true' ||
      !draft ||
      draftPoolSyncDraftIdRef.current === draft.id
    ) {
      return;
    }

    const needsPlayerPool = playerStats.length === 0;
    const needsTeamPool = teamStats.length === 0;

    if (!needsPlayerPool && !needsTeamPool) {
      return;
    }

    draftPoolSyncDraftIdRef.current = draft.id;

    const syncDraftPool = async () => {
      setIsDraftPoolSyncing(true);

      try {
        await supabase.functions.invoke('sync-nhl-stats', {
          body: {
            season: currentSeason,
            playoff_round: draft.round,
          },
        });
        await Promise.all([refetchPlayerStats(), refetchTeamStats()]);
      } finally {
        setIsDraftPoolSyncing(false);
      }
    };

    void syncDraftPool();
  }, [
    currentSeason,
    draft,
    playerStats.length,
    refetchPlayerStats,
    refetchTeamStats,
    teamStats.length,
  ]);

  const handleToggleCompare = (player: ComparePlayer) => {
    setComparePlayers((previous) => toggleComparePlayers(previous, player));
  };

  const handleRemoveCompare = (playerId: number) => {
    setComparePlayers((previous) => removeComparedPlayer(previous, playerId));
  };

  const handleSelectPlayer = (player: DraftablePlayer) => {
    setConfirmPlayer(player);
    setConfirmPosition(
      getDefaultConfirmPosition(player.position, mySlotCounts, roster)
    );
  };

  const handleCloseConfirm = () => {
    setConfirmPlayer(null);
    setPickError(null);
  };

  const handleConfirmPick = async () => {
    const activeMember = pickingMember ?? myMember;
    if (!confirmPlayer || !activeMember || !draft) {
      return;
    }

    setSubmitting(true);
    const errorMessage = await submitDraftPick({
      confirmPlayer,
      confirmPosition,
      draft,
      activeMember,
      members,
      playerStats,
      teamStats,
      draftOrder,
      mockMakePick,
    });

    setPickError(errorMessage);
    setSubmitting(false);

    if (!errorMessage) {
      setConfirmPlayer(null);
    }
  };

  const isPageLoading =
    draftLoading ||
    membersLoading ||
    leagueInfoLoading ||
    playerStatsLoading ||
    teamStatsLoading;

  const status = isPageLoading
    ? 'loading'
    : !draft
      ? 'no-draft'
      : isDraftComplete
        ? 'completed'
        : 'ready';

  return {
    status,
    completeViewProps: draft
      ? {
          draft,
          draftOrder,
          picks,
          playerNameMap,
          teamNameMap,
          onBackToLeague: () => navigate(routes.leagues.dashboard(leagueId)),
        }
      : null,
    readyViewProps: draft
      ? {
          draft,
          currentPicker,
          isMyTurn,
          isCommissioner,
          canPick,
          positionFilter,
          onPositionFilterChange: setPositionFilter,
          searchQuery,
          onSearchQueryChange: setSearchQuery,
          picks,
          playerNameMap,
          teamNameMap,
          myTeamOpened,
          onToggleMyTeam: toggleMyTeam,
          myRosterSlots,
          playerStats,
          teamStats,
          isDraftPoolSyncing,
          onSelectPlayer: handleSelectPlayer,
          comparePlayers,
          onToggleCompare: handleToggleCompare,
          onRemoveCompare: handleRemoveCompare,
          onClearCompare: () => setComparePlayers([]),
          isRound1,
          mySlotCounts,
          regSeasonStats,
          roster,
          confirmPlayer,
          onCloseConfirm: handleCloseConfirm,
          pickError,
          confirmPosition,
          onConfirmPositionChange: setConfirmPosition,
          allowIrSlots,
          submitting,
          onConfirmPick: handleConfirmPick,
          draftedPlayerIds,
          draftedTeamIds,
        }
      : null,
  };
}
