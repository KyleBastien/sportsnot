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
  Table,
  CopyButton,
  ActionIcon,
  Tooltip,
  Loader,
  Center,
  Alert,
} from '@mantine/core';
import { useQuery } from '@tanstack/react-query';
import { supabase } from '@sportsnot/supabase';
import { useAuthContext } from '../../context/AuthContext';
import { LiveGamesWidget } from '../../components/LiveGamesWidget';

function useLeague(leagueId: string) {
  return useQuery({
    queryKey: ['league', leagueId],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('leagues')
        .select(
          `
          *,
          league_members(
            id, user_id, team_name, total_points,
            users(display_name, avatar_url)
          )
        `
        )
        .eq('id', leagueId)
        .single();

      if (error) throw error;
      return data;
    },
  });
}

const STATUS_COLORS: Record<string, string> = {
  setup: 'blue',
  drafting: 'orange',
  active: 'green',
  completed: 'gray',
};

export function LeagueDashboardPage() {
  const { leagueId } = useParams<{ leagueId: string }>();
  const navigate = useNavigate();
  const { user } = useAuthContext();
  const { data: league, isLoading, error } = useLeague(leagueId!);

  if (isLoading) {
    return (
      <Center h="50vh">
        <Loader size="lg" />
      </Center>
    );
  }

  if (error || !league) {
    return (
      <Container size="md" py="xl">
        <Alert color="red" title="Error">
          League not found or you don't have access.
        </Alert>
      </Container>
    );
  }

  const isCommissioner = league.commissioner_id === user?.id;
  const members = league.league_members ?? [];
  const sortedMembers = [...members].sort(
    (a: any, b: any) => (b.total_points ?? 0) - (a.total_points ?? 0)
  );

  return (
    <Container size="lg" py="xl">
      <Stack gap="xl">
        {/* Header */}
        <Group justify="space-between" align="flex-start">
          <div>
            <Group gap="sm">
              <Title order={2}>{league.name}</Title>
              <Badge color={STATUS_COLORS[league.status]} size="lg">
                {league.status}
              </Badge>
            </Group>
            <Text c="dimmed">
              Round {league.current_round} · {members.length} /{' '}
              {league.max_participants} members
            </Text>
          </div>
          <Group>
            {isCommissioner && (
              <Button
                variant="subtle"
                onClick={() => navigate(`/leagues/${leagueId}/settings`)}
              >
                Settings
              </Button>
            )}
            {league.status === 'setup' && isCommissioner && (
              <Button
                onClick={() => navigate(`/draft/${leagueId}/lobby`)}
                disabled={members.length < 2}
              >
                Start Draft
              </Button>
            )}
            {league.status === 'drafting' && (
              <Button
                color="orange"
                onClick={() => navigate(`/draft/${leagueId}`)}
              >
                Go to Draft
              </Button>
            )}
            {league.status === 'active' && (
              <>
                <Button
                  variant="outline"
                  onClick={() => navigate(`/roster/${leagueId}`)}
                >
                  My Roster
                </Button>
                <Button
                  variant="outline"
                  onClick={() => navigate(`/standings/${leagueId}`)}
                >
                  Standings
                </Button>
                {isCommissioner && (
                  <Button
                    color="green"
                    onClick={() => navigate(`/draft/${leagueId}/transition`)}
                  >
                    Next Round
                  </Button>
                )}
              </>
            )}
          </Group>
        </Group>

        {/* Invite Code */}
        <Card shadow="sm" padding="md" radius="md" withBorder>
          <Group justify="space-between">
            <div>
              <Text size="sm" c="dimmed">
                Invite Code
              </Text>
              <Text
                size="xl"
                fw={700}
                style={{ letterSpacing: 3, fontFamily: 'monospace' }}
              >
                {league.invite_code}
              </Text>
            </div>
            <CopyButton value={league.invite_code}>
              {({ copied, copy }) => (
                <Tooltip label={copied ? 'Copied!' : 'Copy invite code'}>
                  <ActionIcon
                    color={copied ? 'teal' : 'gray'}
                    variant="subtle"
                    onClick={copy}
                    size="lg"
                  >
                    {copied ? '✓' : '📋'}
                  </ActionIcon>
                </Tooltip>
              )}
            </CopyButton>
          </Group>
        </Card>

        {/* Live Games */}
        <LiveGamesWidget leagueId={leagueId} />

        {/* Members / Standings */}
        <Card shadow="sm" padding="md" radius="md" withBorder>
          <Title order={4} mb="md">
            Standings
          </Title>
          <Table striped highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Rank</Table.Th>
                <Table.Th>Team</Table.Th>
                <Table.Th>Manager</Table.Th>
                <Table.Th style={{ textAlign: 'right' }}>Points</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {sortedMembers.map((member: any, index: number) => (
                <Table.Tr
                  key={member.id}
                  style={{
                    fontWeight:
                      member.user_id === user?.id ? 700 : undefined,
                  }}
                >
                  <Table.Td>{index + 1}</Table.Td>
                  <Table.Td>{member.team_name}</Table.Td>
                  <Table.Td>
                    {member.users?.display_name ?? 'Unknown'}
                  </Table.Td>
                  <Table.Td style={{ textAlign: 'right' }}>
                    {member.total_points ?? 0}
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Card>
      </Stack>
    </Container>
  );
}
