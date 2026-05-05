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
import type {
  ComparePlayer,
  DraftMemberRow,
  DraftStateRow,
  DraftablePlayer,
} from './draftPageTypes';

interface ConfirmPickContext {
  confirmPlayer: DraftablePlayer;
  activeMember: DraftMemberRow;
  draft: DraftStateRow;
}

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
    const draft = data.draft;
    const activeMember = data.pickingMember ?? data.myMember;
    const pickContext = getConfirmPickContext(
      confirmPlayer,
      activeMember,
      draft
    );
    if (!pickContext) {
      return;
    }

    setSubmitting(true);
    const errorMessage = await submitDraftPick({
      confirmPlayer: pickContext.confirmPlayer,
      confirmPosition,
      draft: pickContext.draft,
      activeMember: pickContext.activeMember,
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

function getConfirmPickContext(
  confirmPlayer: DraftablePlayer | null,
  activeMember: DraftMemberRow | undefined,
  draft: DraftStateRow | null
): ConfirmPickContext | null {
  if (!isPresent(confirmPlayer)) {
    return null;
  }
  if (!isPresent(activeMember)) {
    return null;
  }
  if (!isPresent(draft)) {
    return null;
  }

  return {
    confirmPlayer,
    activeMember,
    draft,
  };
}

function isPresent<T>(value: T | null | undefined): value is T {
  return value != null;
}
