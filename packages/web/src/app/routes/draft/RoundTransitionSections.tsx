import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  Stack,
  Table,
  Text,
  Title,
} from '@mantine/core';
import { DataRow, MobileCardList } from '@sportsnot/ui';

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

export function RoundTransitionSummary({
  leagueName,
  currentRound,
  nextRound,
}: {
  leagueName: string;
  currentRound: number;
  nextRound: number;
}) {
  return (
    <>
      <Stack gap="xs">
        <Title order={2}>Round {currentRound} Complete!</Title>
        <Text c="dimmed">{leagueName}</Text>
      </Stack>

      <Alert color="navy" title="Full Re-Draft">
        All players return to the pool. A new draft will be conducted for Round{' '}
        {nextRound}.
        {nextRound === 3 &&
          ' This draft covers both Conference Finals and Stanley Cup Final — your Round 3 picks carry into Round 4.'}{' '}
        Draft order is based on current standings — worst to best, snake
        pattern.
      </Alert>
    </>
  );
}

export function RoundTransitionStandings({
  currentRound,
  sortedMembers,
  currentUserId,
  isMobile,
}: {
  currentRound: number;
  sortedMembers: TransitionMemberRow[];
  currentUserId: string | undefined;
  isMobile: boolean;
}) {
  const rankedMembers = [...sortedMembers].reverse();

  return (
    <Card shadow="sm" padding="lg" radius="md" withBorder>
      <Stack gap="md">
        <Title order={4}>Round {currentRound} Final Standings</Title>
        {isMobile ? (
          <MobileCardList>
            {rankedMembers.map((member, index) => (
              <RoundTransitionMobileCard
                key={member.id}
                member={member}
                index={index}
                totalMembers={sortedMembers.length}
                currentUserId={currentUserId}
              />
            ))}
          </MobileCardList>
        ) : (
          <Table.ScrollContainer minWidth={600}>
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
                {rankedMembers.map((member, index) => (
                  <RoundTransitionTableRow
                    key={member.id}
                    member={member}
                    index={index}
                    totalMembers={sortedMembers.length}
                    currentUserId={currentUserId}
                  />
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        )}
      </Stack>
    </Card>
  );
}

export function RoundTransitionHistory({
  completedDrafts,
}: {
  completedDrafts: CompletedDraftRow[];
}) {
  if (completedDrafts.length === 0) {
    return null;
  }

  return (
    <Card shadow="sm" padding="lg" radius="md" withBorder>
      <Stack gap="md">
        <Title order={4}>Draft History</Title>
        {completedDrafts.map((draft) => (
          <Group key={draft.id} justify="space-between">
            <Text>Round {draft.round}</Text>
            <Badge color="green" variant="light">
              Completed
            </Badge>
          </Group>
        ))}
      </Stack>
    </Card>
  );
}

export function RoundTransitionAction({
  isCommissioner,
  nextRound,
  starting,
  onStartReDraft,
}: {
  isCommissioner: boolean;
  nextRound: number;
  starting: boolean;
  onStartReDraft: () => void;
}) {
  if (!isCommissioner) {
    return (
      <Alert color="navy" title="Waiting for Commissioner">
        The commissioner will start the re-draft for Round {nextRound} when
        ready.
      </Alert>
    );
  }

  return (
    <Button
      size="lg"
      color="green"
      onClick={onStartReDraft}
      loading={starting}
      fullWidth
    >
      Start Round {nextRound} Re-Draft
    </Button>
  );
}

function RoundTransitionMobileCard({
  member,
  index,
  totalMembers,
  currentUserId,
}: {
  member: TransitionMemberRow;
  index: number;
  totalMembers: number;
  currentUserId: string | undefined;
}) {
  return (
    <Card padding="sm" radius="sm" withBorder>
      <Group justify="space-between" mb={4}>
        <Group gap="xs">
          <Badge
            variant="light"
            color={index === 0 ? 'yellow' : 'gray'}
            size="sm"
          >
            #{index + 1}
          </Badge>
          <Text fw={500} size="sm">
            {member.team_name}
          </Text>
        </Group>
        <Badge variant="outline" size="sm">
          Pick #{totalMembers - index}
        </Badge>
      </Group>
      <DataRow
        label="Player"
        value={
          <Group gap={4}>
            <Text size="sm" fw={500}>
              {member.users?.display_name ?? 'Unknown'}
            </Text>
            {member.user_id === currentUserId && (
              <Badge size="xs" color="green" variant="light">
                You
              </Badge>
            )}
          </Group>
        }
      />
      <DataRow
        label="Points"
        value={
          <Text size="sm" fw={700}>
            {member.total_points ?? 0}
          </Text>
        }
      />
    </Card>
  );
}

function RoundTransitionTableRow({
  member,
  index,
  totalMembers,
  currentUserId,
}: {
  member: TransitionMemberRow;
  index: number;
  totalMembers: number;
  currentUserId: string | undefined;
}) {
  return (
    <Table.Tr>
      <Table.Td>
        <Badge variant="light" color={index === 0 ? 'yellow' : 'gray'}>
          #{index + 1}
        </Badge>
      </Table.Td>
      <Table.Td>{member.team_name}</Table.Td>
      <Table.Td>
        {member.users?.display_name ?? 'Unknown'}
        {member.user_id === currentUserId && (
          <Badge size="xs" ml="xs" color="green" variant="light">
            You
          </Badge>
        )}
      </Table.Td>
      <Table.Td fw={700}>{member.total_points ?? 0}</Table.Td>
      <Table.Td>
        <Badge variant="outline">#{totalMembers - index}</Badge>
      </Table.Td>
    </Table.Tr>
  );
}
