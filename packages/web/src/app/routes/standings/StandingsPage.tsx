import { useParams } from 'react-router-dom';
import {
  Container,
  Title,
  Text,
  Stack,
  Card,
  Table,
  Badge,
  Loader,
  Center,
  Alert,
  Button,
  Group,
} from '@mantine/core';
import { useQuery } from '@tanstack/react-query';
import { supabase } from '@sportsnot/supabase';
import { useAuthContext } from '../../context/AuthContext';
import { useMockStandings } from '../../../mock/hooks/useMockStandings';

const IS_MOCK = import.meta.env.VITE_MOCK_MODE === 'true';

interface StandingsMemberRow {
  id: string;
  user_id: string;
  team_name: string;
  total_points: number;
  player_points?: number | null;
  goalie_points?: number | null;
  round_points?: Record<string, number> | null;
  users?: { display_name?: string } | null;
}

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

function downloadCSV(members: StandingsMemberRow[], leagueName: string) {
  const header = 'Rank,Team,Manager,Points\n';
  const rows = members
    .map(
      (m, i: number) =>
        `${i + 1},"${m.team_name}","${m.users?.display_name ?? 'Unknown'}",${m.total_points ?? 0}`
    )
    .join('\n');

  const blob = new Blob([header + rows], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${leagueName?.replace(/[^a-z0-9]/gi, '_') ?? 'standings'}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

export function StandingsPage() {
  const { leagueId } = useParams<{ leagueId: string }>();
  const { user } = useAuthContext();
  const { data, isLoading, error } = useStandings(leagueId!);

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

  const { league, members } = data;
  const currentRound = league?.current_round ?? 0;

  // Check if breakdown data exists
  const hasBreakdown = members.some(
    (m: StandingsMemberRow) =>
      m.player_points != null || m.goalie_points != null
  );

  // Check if round-by-round data exists
  const hasRoundPoints = members.some(
    (m: StandingsMemberRow) =>
      m.round_points && Object.keys(m.round_points).length > 0
  );

  // Collect all round numbers across all members
  const roundNumbers = hasRoundPoints
    ? [
        ...new Set(
          members.flatMap((m: StandingsMemberRow) =>
            m.round_points ? Object.keys(m.round_points).map(Number) : []
          )
        ),
      ].sort((a, b) => a - b)
    : [];

  return (
    <Container size="lg" py="xl">
      <Stack gap="xl">
        <Group justify="space-between" align="flex-end">
          <div>
            <Title order={2}>Standings</Title>
            <Text c="dimmed">
              {league?.name} · Round {currentRound}
            </Text>
          </div>
          <Button
            variant="light"
            onClick={() => downloadCSV(members, league?.name)}
          >
            Export CSV
          </Button>
        </Group>

        <Card shadow="sm" padding="md" radius="md" withBorder>
          <Table striped highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th style={{ width: 60 }}>Rank</Table.Th>
                <Table.Th>Team</Table.Th>
                <Table.Th>Manager</Table.Th>
                {hasBreakdown && (
                  <>
                    <Table.Th style={{ textAlign: 'right' }}>
                      Player Pts
                    </Table.Th>
                    <Table.Th style={{ textAlign: 'right' }}>
                      Goalie Pts
                    </Table.Th>
                  </>
                )}
                {roundNumbers.map((r) => (
                  <Table.Th key={r} style={{ textAlign: 'right' }}>
                    R{r}
                  </Table.Th>
                ))}
                <Table.Th style={{ textAlign: 'right' }}>Points</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {members.map((member: StandingsMemberRow, index: number) => {
                const isMe = member.user_id === user?.id;
                return (
                  <Table.Tr
                    key={member.id}
                    style={{
                      fontWeight: isMe ? 700 : undefined,
                      backgroundColor: isMe
                        ? 'var(--mantine-color-blue-0)'
                        : undefined,
                    }}
                  >
                    <Table.Td>
                      {index === 0 ? (
                        <Badge color="gold" variant="filled">
                          1st
                        </Badge>
                      ) : index === 1 ? (
                        <Badge color="gray" variant="filled">
                          2nd
                        </Badge>
                      ) : index === 2 ? (
                        <Badge color="orange" variant="filled">
                          3rd
                        </Badge>
                      ) : (
                        index + 1
                      )}
                    </Table.Td>
                    <Table.Td>{member.team_name}</Table.Td>
                    <Table.Td>
                      {member.users?.display_name ?? 'Unknown'}
                      {isMe && (
                        <Badge size="xs" ml="xs" variant="light">
                          You
                        </Badge>
                      )}
                    </Table.Td>
                    {hasBreakdown && (
                      <>
                        <Table.Td
                          style={{
                            textAlign: 'right',
                            fontVariantNumeric: 'tabular-nums',
                          }}
                        >
                          {member.player_points ?? 0}
                        </Table.Td>
                        <Table.Td
                          style={{
                            textAlign: 'right',
                            fontVariantNumeric: 'tabular-nums',
                          }}
                        >
                          {member.goalie_points ?? 0}
                        </Table.Td>
                      </>
                    )}
                    {roundNumbers.map((r) => (
                      <Table.Td
                        key={r}
                        style={{
                          textAlign: 'right',
                          fontVariantNumeric: 'tabular-nums',
                        }}
                      >
                        {member.round_points?.[r] ?? 0}
                      </Table.Td>
                    ))}
                    <Table.Td
                      style={{
                        textAlign: 'right',
                        fontVariantNumeric: 'tabular-nums',
                      }}
                    >
                      {member.total_points ?? 0}
                    </Table.Td>
                  </Table.Tr>
                );
              })}
            </Table.Tbody>
          </Table>
        </Card>
      </Stack>
    </Container>
  );
}
