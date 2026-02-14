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
  Group,
  Box,
} from '@mantine/core';
import { useQuery } from '@tanstack/react-query';
import { supabase, useStatSync, useLiveScoring } from '@sportsnot/supabase';
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

function formatTimeAgo(date: Date): string {
  const seconds = Math.floor((Date.now() - date.getTime()) / 1000);
  if (seconds < 60) return 'just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ago`;
}

const pulseKeyframes = `
@keyframes scorePulse {
  0% { background-color: transparent; }
  50% { background-color: var(--mantine-color-green-1); }
  100% { background-color: transparent; }
}
@keyframes deltaFade {
  0% { opacity: 1; transform: translateY(0); }
  100% { opacity: 0; transform: translateY(-12px); }
}
`;

export function StandingsPage() {
  const { leagueId } = useParams<{ leagueId: string }>();
  const { user } = useAuthContext();
  const { data, isLoading, error } = useStandings(leagueId!);
  const { isLive, lastSyncedAt } = useStatSync(leagueId);
  const { lastUpdated, memberDeltas } = useLiveScoring(leagueId);

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
  const displayTime = lastUpdated ?? lastSyncedAt ?? null;

  return (
    <Container size="lg" py="xl">
      <style>{pulseKeyframes}</style>
      <Stack gap="xl">
        <Group justify="space-between" align="flex-start">
          <div>
            <Title order={2}>Standings</Title>
            <Text c="dimmed">
              {league?.name} · Round {league?.current_round ?? 0}
            </Text>
          </div>
          <Stack gap={4} align="flex-end">
            {isLive && (
              <Badge
                color="green"
                variant="dot"
                size="lg"
                styles={{
                  root: {
                    animation: 'scorePulse 2s ease-in-out infinite',
                  },
                }}
              >
                LIVE
              </Badge>
            )}
            {displayTime && (
              <Text size="xs" c="dimmed">
                Updated {formatTimeAgo(displayTime)}
              </Text>
            )}
          </Stack>
        </Group>

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
                      style={{
                        textAlign: 'right',
                        fontVariantNumeric: 'tabular-nums',
                        position: 'relative',
                        animation: memberDeltas[member.id]
                          ? 'scorePulse 200ms ease-in-out'
                          : undefined,
                      }}
                    >
                      <Box component="span" fw={memberDeltas[member.id] ? 700 : undefined}>
                        {member.total_points ?? 0}
                      </Box>
                      {memberDeltas[member.id] && (
                        <Text
                          component="span"
                          size="xs"
                          c="green"
                          fw={700}
                          ml={4}
                          style={{
                            animation: 'deltaFade 2s ease-out forwards',
                          }}
                        >
                          {memberDeltas[member.id].delta > 0
                            ? `+${memberDeltas[member.id].delta}`
                            : memberDeltas[member.id].delta}
                        </Text>
                      )}
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
