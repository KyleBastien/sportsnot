import { useParams, useSearchParams } from 'react-router-dom';
import { Container, Stack, Loader, Center, Alert } from '@mantine/core';
import { useQuery } from '@tanstack/react-query';
import { supabase } from '@sportsnot/supabase';
import { useAuthContext } from '../../context/AuthContext';
import { useMockStandings } from '../../../mock/hooks/useMockStandings';
import { useRoundComplete } from '../../hooks/useRoundComplete';
import { useWinnerConfetti } from '../../hooks/useWinnerConfetti';
import { useIsMobile } from '@sportsnot/ui';
import { buildRoundSearch, clampRoundSelection } from '../../utils/roundUtils';
import {
  buildStandingsMembers,
  getVisibleRoundNumbers,
} from './standingsUtils';
import {
  buildNextSearchParams,
  collectRoundNumbers,
  hasBreakdownData,
  StandingsContent,
  StandingsHeader,
  type StandingsMemberRow,
  StandingsRoundSelector,
} from './StandingsPageSections';

const IS_MOCK = import.meta.env.VITE_MOCK_MODE === 'true';

function useStandings(leagueId: string) {
  const mockResult = useMockStandings(leagueId);

  const queryResult = useQuery({
    queryKey: ['standings', leagueId],
    queryFn: async () => {
      const { data: league } = await supabase
        .from('leagues')
        .select('name, current_round')
        .eq('id', leagueId)
        .single();

      const { data: members, error } = await supabase
        .from('league_members')
        .select(
          'id, user_id, team_name, total_points, player_points, goalie_points, round_points, users(display_name)'
        )
        .eq('league_id', leagueId)
        .order('total_points', { ascending: false });

      if (error) throw error;

      return {
        league,
        members: members ?? [],
      };
    },
    enabled: !IS_MOCK,
  });

  return IS_MOCK ? mockResult : queryResult;
}

export function StandingsPage() {
  const { leagueId } = useParams<{ leagueId: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const { user } = useAuthContext();
  const { data, isLoading, error } = useStandings(leagueId!);

  const currentRound = Math.max(data?.league?.current_round ?? 1, 1);
  const selectedRound = clampRoundSelection(
    searchParams.get('round'),
    currentRound
  );
  const { seasonComplete } = useRoundComplete(currentRound);

  const typedMembers = (data?.members ?? []) as StandingsMemberRow[];
  const winnerId = seasonComplete ? typedMembers[0]?.user_id : undefined;
  const displayedMembers = buildStandingsMembers(
    typedMembers,
    selectedRound,
    currentRound
  );
  const rosterRoundSearch = buildRoundSearch(selectedRound, currentRound);

  useWinnerConfetti({
    seasonComplete,
    isWinner: !!winnerId && winnerId === user?.id,
    leagueId,
  });

  const isMobile = useIsMobile();
  const isCurrentUser = (memberUserId: string) => memberUserId === user?.id;

  if (isLoading) {
    return (
      <Center h="50vh">
        <Loader size="lg" />
      </Center>
    );
  }

  if (error || !data) {
    return (
      <Container size="md" py="xl">
        <Alert color="red" title="Error">
          Could not load standings.
        </Alert>
      </Container>
    );
  }

  const { league } = data;
  const hasBreakdown = hasBreakdownData(typedMembers);
  const showBreakdown = hasBreakdown && selectedRound === currentRound;
  const visibleRoundNumbers = getVisibleRoundNumbers(
    collectRoundNumbers(typedMembers),
    selectedRound
  );
  const showSeasonWinner = seasonComplete && selectedRound === currentRound;
  const handleRoundChange = (value: string) => {
    const nextRound = clampRoundSelection(value, currentRound);
    setSearchParams(
      buildNextSearchParams(searchParams, nextRound, currentRound),
      { replace: true }
    );
  };

  return (
    <Container size="lg" py="xl">
      <Stack gap="xl">
        <StandingsHeader
          currentRound={currentRound}
          displayedMembers={displayedMembers}
          leagueName={league?.name}
          selectedRound={selectedRound}
        />
        <StandingsRoundSelector
          currentRound={currentRound}
          selectedRound={selectedRound}
          onRoundChange={handleRoundChange}
        />
        <StandingsContent
          displayedMembers={displayedMembers}
          isCurrentUser={isCurrentUser}
          isMobile={isMobile}
          leagueId={leagueId!}
          rosterRoundSearch={rosterRoundSearch}
          showBreakdown={showBreakdown}
          showSeasonWinner={showSeasonWinner}
          userId={user?.id}
          visibleRoundNumbers={visibleRoundNumbers}
        />
      </Stack>
    </Container>
  );
}
