import {
  Alert,
  Badge,
  Button,
  Card,
  Container,
  Group,
  Stack,
  Table,
  Text,
  Title,
} from '@mantine/core';
import { MobileCardList, DataRow } from '@sportsnot/ui';
import type {
  CompletedDraftRow,
  TransitionMemberRow,
} from './useRoundTransitionState';

interface RoundTransitionContentProps {
  completedDrafts: CompletedDraftRow[];
  currentRound: number;
  isCommissioner: boolean;
  isMobile: boolean;
  league: {
    name: string;
  };
  nextRound: number;
  sortedMembers: TransitionMemberRow[];
  starting: boolean;
  userId: string | undefined;
  onBackToLeague: () => void;
  onStartReDraft: () => void;
}

function getRankColor(index: number): string {
  return index === 0 ? 'yellow' : 'gray';
}

function renderUserBadge(memberUserId: string, userId: string | undefined) {
  if (memberUserId !== userId) {
    return null;
  }

  return (
    <Badge size="xs" color="green" variant="light">
      You
    </Badge>
  );
}

function RoundCompletionAlert({ nextRound }: { nextRound: number }) {
  return (
    <Alert color="navy" title="Full Re-Draft">
      All players return to the pool. A new draft will be conducted for Round{' '}
      {nextRound}.
      {nextRound === 3 &&
        ' This draft covers both Conference Finals and Stanley Cup Final — your Round 3 picks carry into Round 4.'}{' '}
      Draft order is based on current standings — worst to best, snake pattern.
    </Alert>
  );
}

function RoundStandingsMobile({
  members,
  userId,
}: {
  members: TransitionMemberRow[];
  userId: string | undefined;
}) {
  return (
    <MobileCardList>
      {members.map((member, index) => (
        <Card key={member.id} padding="sm" radius="sm" withBorder>
          <Group justify="space-between" mb={4}>
            <Group gap="xs">
              <Badge variant="light" color={getRankColor(index)} size="sm">
                #{index + 1}
              </Badge>
              <Text fw={500} size="sm">
                {member.team_name}
              </Text>
            </Group>
            <Badge variant="outline" size="sm">
              Pick #{members.length - index}
            </Badge>
          </Group>
          <DataRow
            label="Player"
            value={
              <Group gap={4}>
                <Text size="sm" fw={500}>
                  {member.users?.display_name ?? 'Unknown'}
                </Text>
                {renderUserBadge(member.user_id, userId)}
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
      ))}
    </MobileCardList>
  );
}

function RoundStandingsDesktop({
  members,
  userId,
}: {
  members: TransitionMemberRow[];
  userId: string | undefined;
}) {
  return (
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
          {members.map((member, index) => (
            <Table.Tr key={member.id}>
              <Table.Td>
                <Badge variant="light" color={getRankColor(index)}>
                  #{index + 1}
                </Badge>
              </Table.Td>
              <Table.Td>{member.team_name}</Table.Td>
              <Table.Td>
                {member.users?.display_name ?? 'Unknown'}
                {member.user_id === userId && (
                  <Badge size="xs" ml="xs" color="green" variant="light">
                    You
                  </Badge>
                )}
              </Table.Td>
              <Table.Td fw={700}>{member.total_points ?? 0}</Table.Td>
              <Table.Td>
                <Badge variant="outline">#{members.length - index}</Badge>
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Table.ScrollContainer>
  );
}

function RoundStandingsCard({
  currentRound,
  isMobile,
  members,
  userId,
}: {
  currentRound: number;
  isMobile: boolean;
  members: TransitionMemberRow[];
  userId: string | undefined;
}) {
  return (
    <Card shadow="sm" padding="lg" radius="md" withBorder>
      <Stack gap="md">
        <Title order={4}>Round {currentRound} Final Standings</Title>
        {isMobile ? (
          <RoundStandingsMobile members={members} userId={userId} />
        ) : (
          <RoundStandingsDesktop members={members} userId={userId} />
        )}
      </Stack>
    </Card>
  );
}

function DraftHistoryCard({
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

function RoundTransitionAction({
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
  if (isCommissioner) {
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

  return (
    <Alert color="navy" title="Waiting for Commissioner">
      The commissioner will start the re-draft for Round {nextRound} when ready.
    </Alert>
  );
}

export function RoundTransitionContent({
  completedDrafts,
  currentRound,
  isCommissioner,
  isMobile,
  league,
  nextRound,
  sortedMembers,
  starting,
  userId,
  onBackToLeague,
  onStartReDraft,
}: RoundTransitionContentProps) {
  const rankedMembers = [...sortedMembers].reverse();

  return (
    <Container size="md" py="xl">
      <Stack gap="xl">
        <Stack gap="xs">
          <Title order={2}>Round {currentRound} Complete!</Title>
          <Text c="dimmed">{league.name}</Text>
        </Stack>

        <RoundCompletionAlert nextRound={nextRound} />
        <RoundStandingsCard
          currentRound={currentRound}
          isMobile={isMobile}
          members={rankedMembers}
          userId={userId}
        />
        <DraftHistoryCard completedDrafts={completedDrafts} />
        <RoundTransitionAction
          isCommissioner={isCommissioner}
          nextRound={nextRound}
          starting={starting}
          onStartReDraft={onStartReDraft}
        />
        <Button variant="subtle" onClick={onBackToLeague}>
          Back to League
        </Button>
      </Stack>
    </Container>
  );
}
