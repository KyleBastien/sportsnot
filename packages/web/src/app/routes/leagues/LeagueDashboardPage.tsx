import { Alert, Center, Container, Loader } from '@mantine/core';
import { useNavigate, useParams } from 'react-router-dom';
import { useAuthContext } from '../../context/AuthContext';
import { LeagueDashboardPageView } from './LeagueDashboardPageView';
import { useLeagueDashboardController } from './useLeagueDashboardController';

export function LeagueDashboardPage() {
  const { leagueId } = useParams<{ leagueId: string }>();
  const navigate = useNavigate();
  const { user } = useAuthContext();
  const controller = useLeagueDashboardController(leagueId, user?.id);

  if (controller.isLoading) {
    return (
      <Center h="50vh">
        <Loader size="lg" />
      </Center>
    );
  }

  if (controller.error || !controller.league) {
    return (
      <Container size="md" py="xl">
        <Alert color="red" title="Error">
          League not found or you don't have access.
        </Alert>
      </Container>
    );
  }

  const { league } = controller;

  const handleStartNextDraft = async () => {
    await controller.startNextDraft();
    navigate(`/draft/${leagueId}/transition`);
  };

  return (
    <LeagueDashboardPageView
      league={league}
      statusColor={controller.statusColor}
      members={controller.members}
      sortedMembers={controller.sortedMembers}
      currentUserId={user?.id}
      currentUserTeamName={controller.currentUserTeamName}
      isCommissioner={controller.isCommissioner}
      isMobile={controller.isMobile}
      seasonComplete={controller.seasonComplete}
      roundComplete={controller.roundComplete}
      roundStatusLoading={controller.roundStatusLoading}
      widgetSnapshot={controller.widgetSnapshot}
      widgetSnapshotLoading={controller.widgetSnapshotLoading}
      leagueGameCardsError={controller.leagueGameCardsError}
      onOpenSettings={() => navigate(`/leagues/${leagueId}/settings`)}
      onStartDraft={() => navigate(`/draft/${leagueId}/lobby`)}
      onGoToDraft={() => navigate(`/draft/${leagueId}`)}
      onOpenRoster={() => navigate(`/roster/${leagueId}`)}
      onOpenStandings={() => navigate(`/standings/${leagueId}`)}
      onStartNextDraft={handleStartNextDraft}
    />
  );
}
