import {
  Alert,
  Badge,
  Button,
  Card,
  Container,
  Group,
  List,
  Stack,
  Text,
  Title,
} from '@mantine/core';

interface LobbyMember {
  id: string;
  user_id: string;
  team_name: string;
  users?: { display_name?: string } | null;
}

interface DraftLobbyPageViewProps {
  leagueName: string;
  nextRound: number;
  members: LobbyMember[];
  rosterSummary: string;
  totalPicks: number;
  commissionerId: string | undefined;
  currentUserId: string | undefined;
  isCommissioner: boolean;
  starting: boolean;
  onStartDraft: () => void;
}

export function DraftLobbyPageView({
  leagueName,
  nextRound,
  members,
  rosterSummary,
  totalPicks,
  commissionerId,
  currentUserId,
  isCommissioner,
  starting,
  onStartDraft,
}: DraftLobbyPageViewProps) {
  return (
    <Container size="md" py="xl">
      <Stack gap="xl">
        <Stack gap="xs">
          <Title order={2}>Draft Lobby</Title>
          <Text c="dimmed">
            {leagueName} — Round {nextRound}
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
                <Text fw={500}>{rosterSummary}</Text>
              </div>
            </Group>
          </Stack>
        </Card>

        <Card shadow="sm" padding="lg" radius="md" withBorder>
          <Stack gap="md">
            <Title order={4}>Participants</Title>
            <List spacing="sm">
              {members.map((member) => (
                <List.Item key={member.id}>
                  <Group gap="sm">
                    <Text fw={500}>
                      {member.users?.display_name ?? 'Unknown'}
                    </Text>
                    <Text c="dimmed" size="sm">
                      ({member.team_name})
                    </Text>
                    {member.user_id === commissionerId && (
                      <Badge size="xs" variant="light">
                        Commissioner
                      </Badge>
                    )}
                    {member.user_id === currentUserId && (
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
            onClick={onStartDraft}
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
