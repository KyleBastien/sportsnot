import { useState, useEffect } from 'react';
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
  List,
} from '@mantine/core';
import { useQuery } from '@tanstack/react-query';
import { supabase } from '@sportsnot/supabase';
import { useAuthContext } from '../../context/AuthContext';

export function DraftLobbyPage() {
  const { leagueId } = useParams<{ leagueId: string }>();
  const { user } = useAuthContext();
  const navigate = useNavigate();
  const [starting, setStarting] = useState(false);

  const { data: league, isLoading } = useQuery({
    queryKey: ['draft-lobby', leagueId],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('leagues')
        .select(
          '*, league_members(id, user_id, team_name, users(display_name))'
        )
        .eq('id', leagueId!)
        .single();

      if (error) throw error;
      return data;
    },
    enabled: !!leagueId,
    refetchInterval: 5000,
  });

  // Check for active draft and redirect
  const { data: activeDraft } = useQuery({
    queryKey: ['active-draft-check', leagueId],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('drafts')
        .select('id, status')
        .eq('league_id', leagueId!)
        .eq('status', 'active')
        .maybeSingle();

      if (error) throw error;
      return data;
    },
    enabled: !!leagueId,
    refetchInterval: 3000,
  });

  useEffect(() => {
    if (activeDraft?.status === 'active') {
      navigate(`/draft/${leagueId}`);
    }
  }, [activeDraft, leagueId, navigate]);

  const isCommissioner = league?.commissioner_id === user?.id;
  const members = league?.league_members ?? [];
  const nextRound = (league?.current_round ?? 0) + 1;

  const handleStartDraft = async () => {
    if (!league || members.length < 2) return;
    setStarting(true);

    const memberUserIds = members.map((m: any) => m.user_id);
    const shuffled = [...memberUserIds].sort(() => Math.random() - 0.5);

    const { error } = await supabase.from('drafts').insert({
      league_id: leagueId,
      round: nextRound,
      status: 'active',
      current_pick: 1,
      draft_order: shuffled,
      started_at: new Date().toISOString(),
    });

    if (!error) {
      await supabase
        .from('leagues')
        .update({ status: 'drafting', current_round: nextRound })
        .eq('id', leagueId!);

      navigate(`/draft/${leagueId}`);
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

  // Calculate total picks per member: 5F + 3D + 1G + 1IR_F + 1IR_D = 11
  const totalPicks = members.length * 11;

  return (
    <Container size="md" py="xl">
      <Stack gap="xl">
        <Stack gap="xs">
          <Title order={2}>Draft Lobby</Title>
          <Text c="dimmed">
            {league.name} — Round {nextRound}
          </Text>
        </Stack>

        <Card shadow="sm" padding="lg" radius="md" withBorder>
          <Stack gap="md">
            <Title order={4}>Draft Info</Title>
            <Group gap="xl">
              <div>
                <Text size="sm" c="dimmed">
                  Format
                </Text>
                <Text fw={500}>Snake Draft</Text>
              </div>
              <div>
                <Text size="sm" c="dimmed">
                  Participants
                </Text>
                <Text fw={500}>{members.length}</Text>
              </div>
              <div>
                <Text size="sm" c="dimmed">
                  Total Picks
                </Text>
                <Text fw={500}>{totalPicks}</Text>
              </div>
              <div>
                <Text size="sm" c="dimmed">
                  Roster
                </Text>
                <Text fw={500}>5F, 3D, 1G, 1IR_F, 1IR_D</Text>
              </div>
            </Group>
          </Stack>
        </Card>

        <Card shadow="sm" padding="lg" radius="md" withBorder>
          <Stack gap="md">
            <Title order={4}>Participants</Title>
            <List spacing="sm">
              {members.map((m: any) => (
                <List.Item key={m.id}>
                  <Group gap="sm">
                    <Text fw={500}>
                      {(m.users as any)?.display_name ?? 'Unknown'}
                    </Text>
                    <Text c="dimmed" size="sm">
                      ({m.team_name})
                    </Text>
                    {m.user_id === league.commissioner_id && (
                      <Badge size="xs" variant="light">
                        Commissioner
                      </Badge>
                    )}
                    {m.user_id === user?.id && (
                      <Badge size="xs" color="green" variant="light">
                        You
                      </Badge>
                    )}
                  </Group>
                </List.Item>
              ))}
            </List>
          </Stack>
        </Card>

        {members.length < 2 && (
          <Alert color="yellow" title="Need More Players">
            At least 2 players are needed to start the draft. Share the invite
            code to add more members.
          </Alert>
        )}

        {isCommissioner ? (
          <Button
            size="lg"
            color="green"
            onClick={handleStartDraft}
            loading={starting}
            disabled={members.length < 2}
            fullWidth
          >
            Start Round {nextRound} Draft
          </Button>
        ) : (
          <Alert color="blue" title="Waiting for Commissioner">
            The commissioner will start the draft when everyone is ready.
          </Alert>
        )}
      </Stack>
    </Container>
  );
}
