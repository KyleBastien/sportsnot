import { useState } from 'react';
import { Navigate, useParams, useNavigate } from 'react-router-dom';
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
import { supabase } from '@sportsnot/supabase';
import { getRosterComposition } from '@sportsnot/types';
import { useAuthContext } from '../../context/AuthContext';
import { useMockStartDraft } from '../../../mock/hooks/useMockDraft';
import { buildDraftOrder } from '../../utils/draftOrderUtils';
import { useLeagueForLobby, useActiveDraftCheck } from './draftLobbyQueries';

const IS_MOCK = import.meta.env.VITE_MOCK_MODE === 'true';

interface LobbyMember {
  id: string;
  user_id: string;
  team_name: string;
  users?: { display_name?: string } | null;
}

export function DraftLobbyPage() {
  const { leagueId } = useParams<{ leagueId: string }>();
  const { user } = useAuthContext();
  const navigate = useNavigate();
  const [starting, setStarting] = useState(false);

  const { data: league, isLoading: leagueLoading } = useLeagueForLobby(
    leagueId!
  );
  const { data: activeDraft, isLoading: activeDraftLoading } =
    useActiveDraftCheck(leagueId!);
  const mockStartDraft = useMockStartDraft();

  const isCommissioner = league?.commissioner_id === user?.id;
  const members = league?.league_members ?? [];
  const nextRound = (league?.current_round ?? 0) + 1;
  const allowIrSlots = (league?.allow_ir_slots ?? true) as boolean;
  const rosterComp = getRosterComposition(allowIrSlots);
  const picksPerMember =
    rosterComp.forwards +
    rosterComp.defensemen +
    rosterComp.goalies +
    rosterComp.irForwards +
    rosterComp.irDefensemen;

  const handleStartDraft = async () => {
    if (!league || members.length < 2) return;
    setStarting(true);

    if (IS_MOCK && mockStartDraft) {
      mockStartDraft.mutate({
        leagueId: leagueId!,
        round: nextRound,
      });
      navigate(`/draft/${leagueId}`);
      setStarting(false);
      return;
    }

    const draftOrder = buildDraftOrder(members, allowIrSlots, nextRound);

    const { error } = await supabase.from('drafts').insert({
      league_id: leagueId,
      round: nextRound,
      status: 'active',
      current_pick: 1,
      draft_order: draftOrder,
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

  if (leagueLoading || activeDraftLoading) {
    return (
      <Center h="50vh">
        <Loader size="lg" />
      </Center>
    );
  }

  if (activeDraft?.status === 'active') {
    return <Navigate to={`/draft/${leagueId}`} replace />;
  }

  if (!league) {
    return (
      <Container size="md" py="xl">
        <Alert color="red">League not found</Alert>
      </Container>
    );
  }

  const totalPicks = members.length * picksPerMember;

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
                <Text fw={500}>
                  {rosterComp.forwards}F, {rosterComp.defensemen}D,{' '}
                  {rosterComp.goalies}G
                  {allowIrSlots
                    ? `, ${rosterComp.irForwards}IR_F, ${rosterComp.irDefensemen}IR_D`
                    : ''}
                </Text>
              </div>
            </Group>
          </Stack>
        </Card>

        <Card shadow="sm" padding="lg" radius="md" withBorder>
          <Stack gap="md">
            <Title order={4}>Participants</Title>
            <List spacing="sm">
              {members.map((m: LobbyMember) => (
                <List.Item key={m.id}>
                  <Group gap="sm">
                    <Text fw={500}>{m.users?.display_name ?? 'Unknown'}</Text>
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
          <Alert color="navy" title="Waiting for Commissioner">
            The commissioner will start the draft when everyone is ready.
          </Alert>
        )}
      </Stack>
    </Container>
  );
}
