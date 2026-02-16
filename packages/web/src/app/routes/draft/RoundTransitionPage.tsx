import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Container,
  Title,
  Text,
  Stack,
  Group,
  Card,
  Badge,
  Button,
  Loader,
  Center,
  Alert,
  Table,
} from '@mantine/core';
import { useQuery } from '@tanstack/react-query';
import { supabase } from '@sportsnot/supabase';
import { useAuthContext } from '../../context/AuthContext';
import { deriveCurrentRound, deriveNextRound } from '../../utils/roundUtils';
import { useMockLeague } from '../../../mock/hooks/useMockLeagues';
import {
  useMockCompletedDrafts,
  useMockStartReDraft,
} from '../../../mock/hooks/useMockDraft';
import { sortMembersForReDraft } from '../../../mock/utils';

const IS_MOCK = import.meta.env.VITE_MOCK_MODE === 'true';

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

// ── Hook wrappers for mock/live mode ──────────────────────────────────

function useTransitionLeague(leagueId: string | undefined) {
  const mockResult = useMockLeague(leagueId);

  const queryResult = useQuery({
    queryKey: ['round-transition', leagueId],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('leagues')
        .select(
          '*, league_members(id, user_id, team_name, total_points, users(display_name))'
        )
        .eq('id', leagueId!)
        .single();

      if (error) throw error;
      return data;
    },
    enabled: !IS_MOCK && !!leagueId,
  });

  return IS_MOCK ? mockResult : queryResult;
}

function useCompletedDrafts(leagueId: string | undefined) {
  const mockResult = useMockCompletedDrafts(leagueId);

  const queryResult = useQuery({
    queryKey: ['completed-drafts', leagueId],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('drafts')
        .select('id, round, status, completed_at')
        .eq('league_id', leagueId!)
        .eq('status', 'completed')
        .order('round', { ascending: true });

      if (error) throw error;
      return data ?? [];
    },
    enabled: !IS_MOCK && !!leagueId,
  });

  return IS_MOCK ? mockResult : queryResult;
}

export function RoundTransitionPage() {
  const { leagueId } = useParams<{ leagueId: string }>();
  const { user } = useAuthContext();
  const navigate = useNavigate();
  const [starting, setStarting] = useState(false);

  const { data: league, isLoading } = useTransitionLeague(leagueId);
  const { data: completedDrafts } = useCompletedDrafts(leagueId);
  const mockStartReDraft = useMockStartReDraft();

  const isCommissioner = league?.commissioner_id === user?.id;
  const completedCount = completedDrafts?.length ?? 0;
  const currentRound = deriveCurrentRound(
    league?.current_round,
    completedCount
  );
  const nextRound = deriveNextRound(league?.current_round, completedCount);

  // Sort members by points (worst to best for re-draft order), tiebreak by team name
  const sortedMembers = sortMembersForReDraft(
    (league?.league_members ?? []) as TransitionMemberRow[]
  );

  const handleStartReDraft = async () => {
    if (!league || sortedMembers.length < 2) return;
    setStarting(true);

    // Re-draft order: worst to best by points (snake pattern)
    const reDraftOrder = sortedMembers.map(
      (m: TransitionMemberRow) => m.user_id
    );

    if (IS_MOCK) {
      await mockStartReDraft.mutateAsync({
        leagueId: leagueId!,
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
          .eq('id', leagueId!);

        navigate(`/draft/${leagueId}`);
      }
    }
    setStarting(false);
  };

  if (isLoading) {
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

  return (
    <Container size="md" py="xl">
      <Stack gap="xl">
        <Stack gap="xs">
          <Title order={2}>Round {currentRound} Complete!</Title>
          <Text c="dimmed">{league.name}</Text>
        </Stack>

        <Alert color="blue" title="Full Re-Draft">
          All players return to the pool. A new draft will be conducted for
          Round {nextRound}. Draft order is based on current standings — worst
          to best, snake pattern.
        </Alert>

        {/* Final Standings */}
        <Card shadow="sm" padding="lg" radius="md" withBorder>
          <Stack gap="md">
            <Title order={4}>Round {currentRound} Final Standings</Title>
            <Table>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Rank</Table.Th>
                  <Table.Th>Team</Table.Th>
                  <Table.Th>Player</Table.Th>
                  <Table.Th>Points</Table.Th>
                  <Table.Th>Re-Draft Pick</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {sortMembersForReDraft(
                  (league.league_members ?? []) as TransitionMemberRow[]
                )
                  .reverse()
                  .map((m: TransitionMemberRow, index: number) => (
                    <Table.Tr key={m.id}>
                      <Table.Td>
                        <Badge
                          variant="light"
                          color={index === 0 ? 'yellow' : 'gray'}
                        >
                          #{index + 1}
                        </Badge>
                      </Table.Td>
                      <Table.Td>{m.team_name}</Table.Td>
                      <Table.Td>
                        {m.users?.display_name ?? 'Unknown'}
                        {m.user_id === user?.id && (
                          <Badge
                            size="xs"
                            ml="xs"
                            color="green"
                            variant="light"
                          >
                            You
                          </Badge>
                        )}
                      </Table.Td>
                      <Table.Td fw={700}>{m.total_points ?? 0}</Table.Td>
                      <Table.Td>
                        <Badge variant="outline">
                          #{sortedMembers.length - index}
                        </Badge>
                      </Table.Td>
                    </Table.Tr>
                  ))}
              </Table.Tbody>
            </Table>
          </Stack>
        </Card>

        {/* Draft History */}
        {completedDrafts && completedDrafts.length > 0 && (
          <Card shadow="sm" padding="lg" radius="md" withBorder>
            <Stack gap="md">
              <Title order={4}>Draft History</Title>
              {completedDrafts.map((d: CompletedDraftRow) => (
                <Group key={d.id} justify="space-between">
                  <Text>Round {d.round}</Text>
                  <Badge color="green" variant="light">
                    Completed
                  </Badge>
                </Group>
              ))}
            </Stack>
          </Card>
        )}

        {/* Re-Draft Action */}
        {isCommissioner ? (
          <Button
            size="lg"
            color="green"
            onClick={handleStartReDraft}
            loading={starting}
            fullWidth
          >
            Start Round {nextRound} Re-Draft
          </Button>
        ) : (
          <Alert color="blue" title="Waiting for Commissioner">
            The commissioner will start the re-draft for Round {nextRound} when
            ready.
          </Alert>
        )}

        <Button
          variant="subtle"
          onClick={() => navigate(`/leagues/${leagueId}`)}
        >
          Back to League
        </Button>
      </Stack>
    </Container>
  );
}
