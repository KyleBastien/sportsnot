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
} from '@mantine/core';
import { useQuery } from '@tanstack/react-query';
import { supabase } from '@sportsnot/supabase';
import { useAuthContext } from '../../context/AuthContext';

function useStandings(leagueId: string) {
  return useQuery({
    queryKey: ['standings', leagueId],
    queryFn: async () => {
      const { data: league } = await supabase
        .from('leagues')
        .select('name, current_round')
        .eq('id', leagueId)
        .single();

      const { data: members, error } = await supabase
        .from('league_members')
        .select('id, user_id, team_name, total_points, users(display_name)')
        .eq('league_id', leagueId)
        .order('total_points', { ascending: false });

      if (error) throw error;

      return {
        league,
        members: members ?? [],
      };
    },
  });
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

  return (
    <Container size="lg" py="xl">
      <Stack gap="xl">
        <div>
          <Title order={2}>Standings</Title>
          <Text c="dimmed">
            {league?.name} · Round {league?.current_round ?? 0}
          </Text>
        </div>

        <Card shadow="sm" padding="md" radius="md" withBorder>
          <Table striped highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th style={{ width: 60 }}>Rank</Table.Th>
                <Table.Th>Team</Table.Th>
                <Table.Th>Manager</Table.Th>
                <Table.Th style={{ textAlign: 'right' }}>Points</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {members.map((member: any, index: number) => {
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
                    <Table.Td
                      style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}
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
