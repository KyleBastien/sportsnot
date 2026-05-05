import { useDisclosure } from '@mantine/hooks';
import { type Position } from '@sportsnot/types';
import { useState } from 'react';
import { routes } from '../../utils/routes';
import { useMockMakePick } from '../../../mock/hooks/useMockDraft';
import {
  getDefaultConfirmPosition,
  removeComparedPlayer,
  toggleComparePlayers,
} from './draftPageHelpers';
import { submitDraftPick } from './draftPickActions';
import { useDraftPageData } from './useDraftPageData';
import type { ComparePlayer, DraftablePlayer } from './draftPageTypes';

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
  const data = useDraftPageData(leagueId, userId);
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
  const mockMakePick = useMockMakePick();

  const handleToggleCompare = (player: ComparePlayer) => {
    setComparePlayers((previous) => toggleComparePlayers(previous, player));
  };

  const handleRemoveCompare = (playerId: number) => {
    setComparePlayers((previous) => removeComparedPlayer(previous, playerId));
  };

  const handleSelectPlayer = (player: DraftablePlayer) => {
    setConfirmPlayer(player);
    setConfirmPosition(
      getDefaultConfirmPosition(player.position, data.mySlotCounts, data.roster)
    );
  };

  const handleCloseConfirm = () => {
    setConfirmPlayer(null);
    setPickError(null);
  };

  const handleConfirmPick = async () => {
    const activeMember = data.pickingMember ?? data.myMember;
    if (!canConfirmPick(confirmPlayer, activeMember, data.draft)) {
      return;
    }

    setSubmitting(true);
    const errorMessage = await submitDraftPick({
      confirmPlayer,
      confirmPosition,
      draft: data.draft,
      activeMember,
      members: data.members,
      playerStats: data.playerStats,
      teamStats: data.teamStats,
      draftOrder: data.draftOrder,
      mockMakePick,
    });

    setPickError(errorMessage);
    setSubmitting(false);

    if (!errorMessage) {
      setConfirmPlayer(null);
    }
  };

  const status = getDraftPageStatus(data);

  return {
    status,
    completeViewProps: data.draft
      ? {
          draft: data.draft,
          draftOrder: data.draftOrder,
          picks: data.picks,
          playerNameMap: data.playerNameMap,
          teamNameMap: data.teamNameMap,
          onBackToLeague: () => navigate(routes.leagues.dashboard(leagueId)),
        }
      : null,
    readyViewProps: data.draft
      ? {
          draft: data.draft,
          currentPicker: data.currentPicker,
          isMyTurn: data.isMyTurn,
          isCommissioner: data.isCommissioner,
          canPick: data.canPick,
          positionFilter,
          onPositionFilterChange: setPositionFilter,
          searchQuery,
          onSearchQueryChange: setSearchQuery,
          picks: data.picks,
          playerNameMap: data.playerNameMap,
          teamNameMap: data.teamNameMap,
          myTeamOpened,
          onToggleMyTeam: toggleMyTeam,
          myRosterSlots: data.myRosterSlots,
          playerStats: data.playerStats,
          teamStats: data.teamStats,
          isDraftPoolSyncing: data.isDraftPoolSyncing,
          onSelectPlayer: handleSelectPlayer,
          comparePlayers,
          onToggleCompare: handleToggleCompare,
          onRemoveCompare: handleRemoveCompare,
          onClearCompare: () => setComparePlayers([]),
          isRound1: data.isRound1,
          mySlotCounts: data.mySlotCounts,
          regSeasonStats: data.regSeasonStats,
          roster: data.roster,
          confirmPlayer,
          onCloseConfirm: handleCloseConfirm,
          pickError,
          confirmPosition,
          onConfirmPositionChange: setConfirmPosition,
          allowIrSlots: data.allowIrSlots,
          submitting,
          onConfirmPick: handleConfirmPick,
          draftedPlayerIds: data.draftedPlayerIds,
          draftedTeamIds: data.draftedTeamIds,
        }
      : null,
  };
}

function getDraftPageStatus(data: ReturnType<typeof useDraftPageData>) {
  if (isDraftPageLoading(data)) {
    return 'loading' as const;
  }

  if (!data.draft) {
    return 'no-draft' as const;
  }

  return data.isDraftComplete ? ('completed' as const) : ('ready' as const);
}

function isDraftPageLoading(data: ReturnType<typeof useDraftPageData>) {
  return (
    data.draftLoading ||
    data.membersLoading ||
    data.leagueInfoLoading ||
    data.playerStatsLoading ||
    data.teamStatsLoading
  );
}

function canConfirmPick(
  confirmPlayer: DraftablePlayer | null,
  activeMember: unknown,
  draft: unknown
): confirmPlayer is DraftablePlayer {
  return Boolean(confirmPlayer && activeMember && draft);
}
