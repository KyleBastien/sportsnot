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
} from '@mantine/core';
import { useAuthContext } from '../../context/AuthContext';
import { useQuery } from '@tanstack/react-query';
import { supabase } from '@sportsnot/supabase';

interface LeagueWithMembership {
  id: string;
  name: string;
  status: string;
  current_round: number;
  max_participants: number;
  commissioner_id: string;
  invite_code: string;
  league_members: Array<{ team_name: string; total_points: number; user_id: string }>;
  memberCount: number;
}

function useLiveGames() {
  return useQuery({
    queryKey: ['live-games'],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('team_stats_cache')
        .select('team_id, team_name, team_abbreviation, wins, shutouts, is_eliminated')
        .eq('is_eliminated', false)
        .order('wins', { ascending: false });

      if (error) throw error;
      return data ?? [];
    },
  });
}

function useMyLeagues() {
  const { user } = useAuthContext();

  return useQuery({
    queryKey: ['my-leagues', user?.id],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('leagues')
        .select(
          `
          *,
          league_members!inner(team_name, total_points, user_id)
        `
        )
        .eq('league_members.user_id', user!.id);

      if (error) throw error;

      return (data ?? []).map((league: any) => ({
        ...league,
        memberCount: league.league_members?.length ?? 0,
      })) as LeagueWithMembership[];
    },
    enabled: !!user,
  });
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
              Welcome back, {user?.user_metadata?.['display_name'] ?? user?.email}
            </Text>
          </div>
          <Group>
            <Button onClick={() => navigate('/leagues/create')}>
              Create League
            </Button>
            <Button variant="outline" onClick={() => navigate('/leagues/join')}>
              Join League
            </Button>
          </Group>
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
              {liveGames.map((team: any) => (
                <Card key={team.team_id} shadow="sm" padding="md" radius="md" withBorder>
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
