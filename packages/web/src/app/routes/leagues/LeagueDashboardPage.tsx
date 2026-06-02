import { useParams } from 'react-router-dom';
import { Alert, Center, Container, Loader } from '@mantine/core';
import { useAuthContext } from '../../context/AuthContext';
import { LeagueDashboardContent } from './LeagueDashboardContent';
import { useLeagueDashboardState } from './useLeagueDashboardState';

function LeagueDashboardLoading() {
  return (
    <Center h="50vh">
      <Loader size="lg" />
    </Center>
  );
}

function LeagueDashboardError() {
  return (
    <Container size="md" py="xl">
      <Alert color="red" title="Error">
        League not found or you don't have access.
      </Alert>
    </Container>
  );
}

export function LeagueDashboardPage() {
  const { leagueId } = useParams<{ leagueId: string }>();
  const { user } = useAuthContext();
  const dashboardState = useLeagueDashboardState(leagueId, user?.id);

  if (dashboardState.isLoading) {
    return <LeagueDashboardLoading />;
  }

  if (dashboardState.error || !dashboardState.league) {
    return <LeagueDashboardError />;
  }

  return (
    <LeagueDashboardContent
      currentRound={dashboardState.currentRound}
      isCommissioner={dashboardState.league.commissioner_id === user?.id}
      isMobile={dashboardState.isMobile}
      league={dashboardState.league}
      leagueGameCardsError={dashboardState.leagueGameCardsError}
      leagueId={leagueId}
      members={dashboardState.members}
      roundComplete={dashboardState.roundComplete}
      roundStatusLoading={dashboardState.roundStatusLoading}
      seasonComplete={dashboardState.seasonComplete}
      userId={user?.id}
      widgetSnapshot={dashboardState.widgetSnapshot}
      widgetSnapshotLoading={dashboardState.widgetSnapshotLoading}
      onOpenDraft={dashboardState.openDraft}
      onOpenLobby={dashboardState.openLobby}
      onOpenRoster={dashboardState.openRoster}
      onOpenSettings={dashboardState.openSettings}
      onOpenStandings={dashboardState.openStandings}
      onStartNextDraft={dashboardState.startNextDraft}
      onOpenTransition={dashboardState.openTransition}
    />
  );
}
