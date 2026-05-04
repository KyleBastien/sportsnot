import { useParams } from 'react-router-dom';
import { Alert, Center, Container, Loader } from '@mantine/core';
import { useAuthContext } from '../../context/AuthContext';
import { RoundTransitionContent } from './RoundTransitionContent';
import { useRoundTransitionState } from './useRoundTransitionState';

function RoundTransitionLoading() {
  return (
    <Center h="50vh">
      <Loader size="lg" />
    </Center>
  );
}

function RoundTransitionError() {
  return (
    <Container size="md" py="xl">
      <Alert color="red">League not found</Alert>
    </Container>
  );
}

export function RoundTransitionPage() {
  const { leagueId } = useParams<{ leagueId: string }>();
  const { user } = useAuthContext();
  const transitionState = useRoundTransitionState(leagueId, user?.id);

  if (transitionState.isLoading) {
    return <RoundTransitionLoading />;
  }

  if (transitionState.error || !transitionState.league) {
    return <RoundTransitionError />;
  }

  return (
    <RoundTransitionContent
      completedDrafts={transitionState.completedDrafts}
      currentRound={transitionState.currentRound}
      isCommissioner={transitionState.isCommissioner}
      isMobile={transitionState.isMobile}
      league={transitionState.league}
      nextRound={transitionState.nextRound}
      sortedMembers={transitionState.sortedMembers}
      starting={transitionState.starting}
      userId={user?.id}
      onBackToLeague={transitionState.backToLeague}
      onStartReDraft={transitionState.startReDraft}
    />
  );
}
