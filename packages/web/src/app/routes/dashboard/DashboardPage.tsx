import { useNavigate } from 'react-router-dom';
import {
  Container,
  Title,
  Text,
  Stack,
  Button,
  Group,
  SimpleGrid,
  Card,
  Badge,
  Loader,
  Center,
  Alert,
  Skeleton,
} from '@mantine/core';
import { useAuthContext } from '../../context/AuthContext';
import { useMyLeagues, useLiveGames } from './dashboardPageQueries';

interface TeamStatRow {
  team_id: number;
  team_name: string;
  team_abbreviation: string;
  wins: number;
  shutouts: number;
  is_eliminated: boolean;
  playoff_round: number;
}
const STATUS_COLORS: Record<string, string> = {
  setup: 'blue',
  drafting: 'orange',
  active: 'green',
  completed: 'gray',
};

export function DashboardPage() {
  const navigate = useNavigate();
  const { user } = useAuthContext();
  const { data: leagues, isLoading } = useMyLeagues();
  const { data: liveGames } = useLiveGames();

  return (
    <Container size="lg" py="xl">
      <Stack gap="xl">
        <Group justify="space-between" align="center">
          <div>
            <Title order={2}>Dashboard</Title>
            <Text c="dimmed">
              Welcome back,{' '}
              {user?.user_metadata?.['display_name'] ?? user?.email}
            </Text>
          </div>
          {isLoading ? (
            <Group data-testid="dashboard-header-skeleton">
              <Skeleton height={36} width={130} radius="sm" />
              <Skeleton height={36} width={110} radius="sm" />
            </Group>
          ) : (
            <Group>
              <Button onClick={() => navigate('/leagues/create')}>
                Create League
              </Button>
              <Button
                variant="outline"
                onClick={() => navigate('/leagues/join')}
              >
                Join League
              </Button>
            </Group>
          )}
        </Group>

        <Title order={3}>My Leagues</Title>

        {isLoading ? (
          <Center py="xl">
            <Loader />
          </Center>
        ) : !leagues?.length ? (
          <Card shadow="sm" padding="xl" radius="md" withBorder>
            <Stack align="center" gap="md">
              <Text size="lg" c="dimmed">
                You haven't joined any leagues yet
              </Text>
              <Group>
                <Button onClick={() => navigate('/leagues/create')}>
                  Create a League
                </Button>
                <Button
                  variant="outline"
                  onClick={() => navigate('/leagues/join')}
                >
                  Join with Invite Code
                </Button>
              </Group>
            </Stack>
          </Card>
        ) : (
          <SimpleGrid cols={{ base: 1, sm: 2, md: 3 }}>
            {leagues.map((league) => (
              <Card
                key={league.id}
                shadow="sm"
                padding="lg"
                radius="md"
                withBorder
                style={{ cursor: 'pointer' }}
                onClick={() => navigate(`/leagues/${league.id}`)}
              >
                <Group justify="space-between" mb="xs">
                  <Title order={4}>{league.name}</Title>
                  <Badge color={STATUS_COLORS[league.status]}>
                    {league.status}
                  </Badge>
                </Group>
                <Text size="sm" c="dimmed">
                  Round {league.current_round} · {league.memberCount} members
                </Text>
              </Card>
            ))}
          </SimpleGrid>
        )}

        {liveGames && liveGames.length > 0 && (
          <>
            <Title order={3}>Live Games</Title>
            <Alert color="green" title="Games In Progress">
              There are currently {liveGames.length} teams competing in the
              playoffs.
            </Alert>
            <SimpleGrid cols={{ base: 1, sm: 2, md: 3 }}>
              {liveGames.map((team: TeamStatRow) => (
                <Card
                  key={team.team_id}
                  shadow="sm"
                  padding="md"
                  radius="md"
                  withBorder
                >
                  <Group justify="space-between">
                    <Text fw={600}>{team.team_name}</Text>
                    <Badge color="green" variant="light">
                      {team.team_abbreviation}
                    </Badge>
                  </Group>
                  <Text size="sm" c="dimmed">
                    {team.wins} wins · {team.shutouts} shutouts
                  </Text>
                </Card>
              ))}
            </SimpleGrid>
          </>
        )}
      </Stack>
    </Container>
  );
}
