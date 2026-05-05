import { supabase } from '@sportsnot/supabase';
import { useState } from 'react';
import { useMockActivateIR } from '../../../mock/hooks/useMockRoster';
import type { IrModalState, RosterSlotRow } from './rosterTypes';
import { useRosterPageData } from './useRosterPageData';

const IS_MOCK = import.meta.env.VITE_MOCK_MODE === 'true';

interface UseRosterPageControllerParams {
  leagueId: string;
  leagueMemberId?: string;
}

export function useRosterPageController({
  leagueId,
  leagueMemberId,
}: UseRosterPageControllerParams) {
  const data = useRosterPageData(leagueId, leagueMemberId);
  const [irModal, setIrModal] = useState<IrModalState | null>(null);
  const [selectedInjuredSlotId, setSelectedInjuredSlotId] = useState<
    string | null
  >(null);
  const [activating, setActivating] = useState(false);
  const mockActivateIR = useMockActivateIR();

  if (data.isLoading) {
    return { status: 'loading' as const };
  }

  if (data.error || !data.data) {
    return { status: 'error' as const };
  }

  if (data.data.slots.length === 0) {
    return {
      status: 'empty' as const,
      emptyProps: data.emptyProps,
    };
  }

  const handleActivateIR = async () => {
    if (!irModal || !selectedInjuredSlotId) {
      return;
    }

    setActivating(true);

    if (IS_MOCK) {
      mockActivateIR.mutate({
        leagueMemberId: data.data.memberId,
        slotId: irModal.irSlotId,
      });
      closeIrModal();
      return;
    }

    const { error } = await supabase.rpc('activate_ir_player', {
      p_league_member_id: data.data.memberId,
      p_round: data.data.round,
      p_injured_roster_id: selectedInjuredSlotId,
      p_ir_roster_id: irModal.irSlotId,
    });

    if (!error) {
      data.queryClient.invalidateQueries({ queryKey: ['roster', leagueId] });
    }

    closeIrModal();
  };

  const closeIrModal = () => {
    setActivating(false);
    setIrModal(null);
    setSelectedInjuredSlotId(null);
  };

  return {
    status: 'ready' as const,
    viewProps: {
      ...data.buildReadyViewProps(
        data.data.slots,
        data.data.round,
        data.data.totalPoints ?? 0
      ),
      onOpenIrModal: (slotId: string, candidates: RosterSlotRow[]) => {
        setIrModal({ irSlotId: slotId, candidates });
        setSelectedInjuredSlotId(candidates[0]?.id ?? null);
      },
      irModal,
      selectedInjuredSlotId,
      onSelectedInjuredSlotIdChange: setSelectedInjuredSlotId,
      onCloseIrModal: closeIrModal,
      onActivateIr: handleActivateIR,
      activating,
    },
  };
}
