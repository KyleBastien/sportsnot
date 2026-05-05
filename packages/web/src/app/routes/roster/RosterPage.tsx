import { Center, Loader } from '@mantine/core';
import { useParams } from 'react-router-dom';
import {
  RosterPageEmptyState,
  RosterPageErrorState,
  RosterPageView,
} from './RosterPageView';
import { useRosterPageController } from './useRosterPageController';

export function RosterPage() {
  const { leagueId, leagueMemberId } = useParams<{
    leagueId: string;
    leagueMemberId?: string;
  }>();

  const controller = useRosterPageController({
    leagueId: leagueId ?? '',
    leagueMemberId,
  });

  if (!leagueId) {
    return <RosterPageErrorState />;
  }

  if (controller.status === 'loading') {
    return (
      <Center h="50vh">
        <Loader size="lg" />
      </Center>
    );
  }

  if (controller.status === 'error') {
    return <RosterPageErrorState />;
  }

  if (controller.status === 'empty') {
    return <RosterPageEmptyState {...controller.emptyProps} />;
  }

  return <RosterPageView {...controller.viewProps} />;
}
