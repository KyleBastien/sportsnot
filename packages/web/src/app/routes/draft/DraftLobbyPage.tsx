import { Alert, Center, Container, Loader } from '@mantine/core';
import { Navigate, useNavigate, useParams } from 'react-router-dom';
import { supabase } from '@sportsnot/supabase';
import { getRosterComposition } from '@sportsnot/types';
import { useState } from 'react';
import { useAuthContext } from '../../context/AuthContext';
import { useMockStartDraft } from '../../../mock/hooks/useMockDraft';
import { buildDraftOrder } from '../../utils/draftOrderUtils';
import { DraftLobbyPageView } from './DraftLobbyPageView';
import { useActiveDraftCheck, useLeagueForLobby } from './draftLobbyQueries';

const IS_MOCK = import.meta.env.VITE_MOCK_MODE === 'true';

interface LobbyMember {
  id: string;
  user_id: string;
  team_name: string;
  users?: { display_name?: string } | null;
}

function buildRosterSummary(allowIrSlots: boolean) {
  const roster = getRosterComposition(allowIrSlots);
  return `${roster.forwards}F, ${roster.defensemen}D, ${roster.goalies}G${
    allowIrSlots ? `, ${roster.irForwards}IR_F, ${roster.irDefensemen}IR_D` : ''
  }`;
}

export function DraftLobbyPage() {
  const { leagueId } = useParams<{ leagueId: string }>();
  const { user } = useAuthContext();
  const navigate = useNavigate();
  const [starting, setStarting] = useState(false);

  const { data: league, isLoading: leagueLoading } = useLeagueForLobby(
    leagueId!
  );
  const { data: activeDraft, isLoading: activeDraftLoading } =
    useActiveDraftCheck(leagueId!);
  const mockStartDraft = useMockStartDraft();

  if (leagueLoading || activeDraftLoading) {
    return (
      <Center h="50vh">
        <Loader size="lg" />
      </Center>
    );
  }

  if (activeDraft?.status === 'active') {
    return <Navigate to={`/draft/${leagueId}`} replace />;
  }

  if (!league) {
    return (
      <Container size="md" py="xl">
        <Alert color="red">League not found</Alert>
      </Container>
    );
  }

  const members = (league.league_members ?? []) as LobbyMember[];
  const nextRound = (league.current_round ?? 0) + 1;
  const isCommissioner = league.commissioner_id === user?.id;
  const allowIrSlots = (league.allow_ir_slots ?? true) as boolean;
  const rosterComposition = getRosterComposition(allowIrSlots);
  const picksPerMember =
    rosterComposition.forwards +
    rosterComposition.defensemen +
    rosterComposition.goalies +
    rosterComposition.irForwards +
    rosterComposition.irDefensemen;
  const totalPicks = members.length * picksPerMember;

  const handleStartDraft = async () => {
    if (!leagueId || members.length < 2) {
      return;
    }

    setStarting(true);

    if (IS_MOCK) {
      mockStartDraft.mutate({
        leagueId,
        round: nextRound,
      });
      navigate(`/draft/${leagueId}`);
      setStarting(false);
      return;
    }

    const draftOrder = buildDraftOrder(members, allowIrSlots, nextRound);
    const { error } = await supabase.from('drafts').insert({
      league_id: leagueId,
      round: nextRound,
      status: 'active',
      current_pick: 1,
      draft_order: draftOrder,
      started_at: new Date().toISOString(),
    });

    if (!error) {
      await supabase
        .from('leagues')
        .update({ status: 'drafting', current_round: nextRound })
        .eq('id', leagueId);
      navigate(`/draft/${leagueId}`);
    }

    setStarting(false);
  };

  return (
    <DraftLobbyPageView
      leagueName={league.name}
      nextRound={nextRound}
      members={members}
      rosterSummary={buildRosterSummary(allowIrSlots)}
      totalPicks={totalPicks}
      commissionerId={league.commissioner_id}
      currentUserId={user?.id}
      isCommissioner={isCommissioner}
      starting={starting}
      onStartDraft={handleStartDraft}
    />
  );
}
