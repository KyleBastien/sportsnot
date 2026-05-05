import { Alert, Center, Container, Loader } from '@mantine/core';
import { useNavigate, useParams } from 'react-router-dom';
import { supabase } from '@sportsnot/supabase';
import { useIsMobile } from '@sportsnot/ui';
import { useState } from 'react';
import { useAuthContext } from '../../context/AuthContext';
import { deriveCurrentRound, deriveNextRound } from '../../utils/roundUtils';
import { useMockStartReDraft } from '../../../mock/hooks/useMockDraft';
import { RoundTransitionPageView } from './RoundTransitionPageView';
import {
  useCompletedDrafts,
  useTransitionLeague,
} from './roundTransitionQueries';

const IS_MOCK = import.meta.env.VITE_MOCK_MODE === 'true';

function sortMembersForReDraft<
  T extends { total_points?: number | null; team_name: string },
>(members: T[]): T[] {
  return [...members].sort((a, b) => {
    const pointsDiff = (a.total_points ?? 0) - (b.total_points ?? 0);
    if (pointsDiff !== 0) {
      return pointsDiff;
    }
    return a.team_name.localeCompare(b.team_name);
  });
}

interface TransitionMemberRow {
  id: string;
  user_id: string;
  team_name: string;
  total_points: number;
  users?: { display_name?: string } | null;
}

interface CompletedDraftRow {
  id: string;
  round: number;
  status: string;
  completed_at: string | null;
}

export function RoundTransitionPage() {
  const { leagueId } = useParams<{ leagueId: string }>();
  const { user } = useAuthContext();
  const navigate = useNavigate();
  const [starting, setStarting] = useState(false);

  const { data: league, isLoading: leagueLoading } =
    useTransitionLeague(leagueId);
  const { data: completedDrafts, isLoading: completedDraftsLoading } =
    useCompletedDrafts(leagueId);
  const mockStartReDraft = useMockStartReDraft();
  const isMobile = useIsMobile();

  if (leagueLoading || completedDraftsLoading) {
    return (
      <Center h="50vh">
        <Loader size="lg" />
      </Center>
    );
  }

  if (!league) {
    return (
      <Container size="md" py="xl">
        <Alert color="red">League not found</Alert>
      </Container>
    );
  }

  const completedCount = completedDrafts?.length ?? 0;
  const currentRound = deriveCurrentRound(league.current_round, completedCount);
  const nextRound = deriveNextRound(league.current_round, completedCount);
  const sortedMembers = sortMembersForReDraft(
    (league.league_members ?? []) as TransitionMemberRow[]
  );
  const isCommissioner = league.commissioner_id === user?.id;

  const handleStartReDraft = async () => {
    if (!leagueId || sortedMembers.length < 2) {
      return;
    }

    setStarting(true);

    const reDraftOrder = sortedMembers.map((member) => member.user_id);

    if (IS_MOCK) {
      await mockStartReDraft.mutateAsync({
        leagueId,
        nextRound,
        draftOrder: reDraftOrder,
      });
      navigate(`/draft/${leagueId}`);
    } else {
      const { error } = await supabase.from('drafts').insert({
        league_id: leagueId,
        round: nextRound,
        status: 'active',
        current_pick: 1,
        draft_order: reDraftOrder,
        started_at: new Date().toISOString(),
      });

      if (!error) {
        await supabase
          .from('leagues')
          .update({ status: 'drafting', current_round: nextRound })
          .eq('id', leagueId);
        navigate(`/draft/${leagueId}`);
      }
    }

    setStarting(false);
  };

  return (
    <RoundTransitionPageView
      leagueName={league.name}
      currentRound={currentRound}
      nextRound={nextRound}
      sortedMembers={sortedMembers}
      currentUserId={user?.id}
      isMobile={isMobile}
      completedDrafts={((completedDrafts ?? []) as CompletedDraftRow[]) ?? []}
      isCommissioner={isCommissioner}
      starting={starting}
      onStartReDraft={handleStartReDraft}
      onBackToLeague={() => navigate(`/leagues/${leagueId}`)}
    />
  );
}
