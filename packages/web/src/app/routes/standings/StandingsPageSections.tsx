import type { ComponentProps } from 'react';
import { Link } from 'react-router-dom';
import {
  Anchor,
  Badge,
  Button,
  Card,
  Group,
  SegmentedControl,
  Table,
  Text,
  Title,
} from '@mantine/core';
import { DataRow, MobileCardList } from '@sportsnot/ui';
import { getAvailableRounds, getRoundPoints } from '../../utils/roundUtils';
import type { DisplayStandingsMember } from './standingsUtils';

export interface StandingsMemberRow {
  id: string;
  user_id: string;
  team_name: string;
  total_points: number;
  player_points?: number | null;
  goalie_points?: number | null;
  round_points?: Record<string, number> | null;
  users?: { display_name?: string } | null;
}

export type DisplayStandingsMemberRow =
  DisplayStandingsMember<StandingsMemberRow>;

function buildStandingsSubtitle(
  leagueName: string | undefined,
  selectedRound: number,
  currentRound: number
) {
  if (selectedRound === currentRound) {
    return `${leagueName} · Current standings through round ${currentRound}`;
  }

  return `${leagueName} · Snapshot through round ${selectedRound} · League now in round ${currentRound}`;
}

function downloadCSV(
  members: DisplayStandingsMemberRow[],
  leagueName: string | undefined,
  selectedRound: number,
  currentRound: number
) {
  const header = 'Rank,Team,Manager,Points\n';
  const rows = members
    .map(
      (m, i: number) =>
        `${i + 1},"${m.team_name}","${m.users?.display_name ?? 'Unknown'}",${m.selected_total_points}`
    )
    .join('\n');

  const blob = new Blob([header + rows], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  const suffix =
    selectedRound === currentRound ? '' : `_through_round_${selectedRound}`;
  a.download = `${
    leagueName?.replace(/[^a-z0-9]/gi, '_') ?? 'standings'
  }${suffix}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

export function hasBreakdownData(members: StandingsMemberRow[]) {
  return members.some(
    (member) => member.player_points != null || member.goalie_points != null
  );
}

export function collectRoundNumbers(members: StandingsMemberRow[]) {
  return [
    ...new Set(
      members.flatMap((member) =>
        member.round_points ? Object.keys(member.round_points).map(Number) : []
      )
    ),
  ].sort((a, b) => a - b);
}

export function buildNextSearchParams(
  searchParams: URLSearchParams,
  nextRound: number,
  currentRound: number
) {
  const nextSearchParams = new URLSearchParams(searchParams);

  if (nextRound === currentRound) {
    nextSearchParams.delete('round');
  } else {
    nextSearchParams.set('round', String(nextRound));
  }

  return nextSearchParams;
}

export function StandingsRoundSelector({
  currentRound,
  selectedRound,
  onRoundChange,
}: {
  currentRound: number;
  selectedRound: number;
  onRoundChange: (value: string) => void;
}) {
  if (currentRound <= 1) {
    return null;
  }

  return (
    <SegmentedControl
      fullWidth
      value={String(selectedRound)}
      onChange={onRoundChange}
      data={getAvailableRounds(currentRound).map((round) => ({
        label: `Round ${round}`,
        value: String(round),
      }))}
    />
  );
}

export function StandingsHeader({
  currentRound,
  displayedMembers,
  leagueName,
  selectedRound,
}: {
  currentRound: number;
  displayedMembers: DisplayStandingsMemberRow[];
  leagueName: string | undefined;
  selectedRound: number;
}) {
  return (
    <Group justify="space-between" align="flex-end">
      <div>
        <Title order={2}>Standings</Title>
        <Text c="dimmed">
          {buildStandingsSubtitle(leagueName, selectedRound, currentRound)}
        </Text>
      </div>
      <Button
        variant="light"
        onClick={() =>
          downloadCSV(displayedMembers, leagueName, selectedRound, currentRound)
        }
      >
        Export CSV
      </Button>
    </Group>
  );
}

function MobileStandingsCards({
  displayedMembers,
  isCurrentUser,
  rosterBasePath,
  rosterRoundSearch,
  showBreakdown,
  showSeasonWinner,
  userId,
  visibleRoundNumbers,
}: {
  displayedMembers: DisplayStandingsMemberRow[];
  isCurrentUser: (userId: string) => boolean;
  rosterBasePath: string;
  rosterRoundSearch: string;
  showBreakdown: boolean;
  showSeasonWinner: boolean;
  userId: string | undefined;
  visibleRoundNumbers: number[];
}) {
  return (
    <MobileCardList emptyMessage="No standings data">
      {displayedMembers.map((member, index) => {
        const isMe = isCurrentUser(member.user_id);
        return (
          <Card
            key={member.id}
            padding="sm"
            radius="sm"
            withBorder
            style={{
              fontWeight: isMe ? 700 : undefined,
              backgroundColor: isMe
                ? 'var(--mantine-color-blue-light)'
                : undefined,
            }}
          >
            <Group justify="space-between" mb={4}>
              <Group gap="xs">
                <RankBadge rank={index} />
                <Anchor
                  component={Link}
                  to={`${rosterBasePath}/${member.id}${rosterRoundSearch}`}
                  fw={isMe ? 700 : undefined}
                >
                  {member.team_name}
                  {showSeasonWinner && index === 0 && ' 🏆'}
                </Anchor>
              </Group>
              <Badge size="lg" variant="filled" color="blue">
                {member.selected_total_points}
              </Badge>
            </Group>
            <DataRow
              label="Manager"
              value={
                <Group gap={4}>
                  <Text size="sm" fw={500}>
                    {member.users?.display_name ?? 'Unknown'}
                  </Text>
                  {member.user_id === userId && (
                    <Badge size="xs" variant="light">
                      You
                    </Badge>
                  )}
                </Group>
              }
            />
            {showBreakdown && (
              <Group gap="xs" mt={4}>
                <Badge size="sm" variant="light">
                  Player: {member.player_points ?? 0}
                </Badge>
                <Badge size="sm" variant="light">
                  Goalie: {member.goalie_points ?? 0}
                </Badge>
              </Group>
            )}
            {visibleRoundNumbers.length > 0 && (
              <Group gap="xs" mt={4}>
                {visibleRoundNumbers.map((round) => (
                  <Badge key={round} size="sm" variant="outline">
                    R{round}: {getRoundPoints(member.round_points, round)}
                  </Badge>
                ))}
              </Group>
            )}
          </Card>
        );
      })}
    </MobileCardList>
  );
}

function DesktopStandingsTable({
  displayedMembers,
  isCurrentUser,
  rosterBasePath,
  rosterRoundSearch,
  showBreakdown,
  showSeasonWinner,
  userId,
  visibleRoundNumbers,
}: {
  displayedMembers: DisplayStandingsMemberRow[];
  isCurrentUser: (userId: string) => boolean;
  rosterBasePath: string;
  rosterRoundSearch: string;
  showBreakdown: boolean;
  showSeasonWinner: boolean;
  userId: string | undefined;
  visibleRoundNumbers: number[];
}) {
  return (
    <Table.ScrollContainer minWidth={600}>
      <Table striped highlightOnHover>
        <Table.Thead>
          <Table.Tr>
            <Table.Th style={{ width: 60 }}>Rank</Table.Th>
            <Table.Th>Team</Table.Th>
            <Table.Th>Manager</Table.Th>
            {showBreakdown && (
              <>
                <Table.Th style={{ textAlign: 'right' }}>Player Pts</Table.Th>
                <Table.Th style={{ textAlign: 'right' }}>Goalie Pts</Table.Th>
              </>
            )}
            {visibleRoundNumbers.map((round) => (
              <Table.Th key={round} style={{ textAlign: 'right' }}>
                R{round}
              </Table.Th>
            ))}
            <Table.Th style={{ textAlign: 'right' }}>Points</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {displayedMembers.map((member, index) => {
            const isMe = isCurrentUser(member.user_id);
            return (
              <Table.Tr
                key={member.id}
                style={{
                  fontWeight: isMe ? 700 : undefined,
                  backgroundColor: isMe
                    ? 'var(--mantine-color-blue-light)'
                    : undefined,
                }}
              >
                <Table.Td>
                  <RankBadge rank={index} />
                </Table.Td>
                <Table.Td>
                  <Anchor
                    component={Link}
                    to={`${rosterBasePath}/${member.id}${rosterRoundSearch}`}
                    fw={isMe ? 700 : undefined}
                  >
                    {member.team_name}
                    {showSeasonWinner && index === 0 && ' 🏆'}
                  </Anchor>
                </Table.Td>
                <Table.Td>
                  {member.users?.display_name ?? 'Unknown'}
                  {member.user_id === userId && (
                    <Badge size="xs" ml="xs" variant="light">
                      You
                    </Badge>
                  )}
                </Table.Td>
                {showBreakdown && (
                  <>
                    <NumericStandingsCell value={member.player_points ?? 0} />
                    <NumericStandingsCell value={member.goalie_points ?? 0} />
                  </>
                )}
                {visibleRoundNumbers.map((round) => (
                  <NumericStandingsCell
                    key={round}
                    value={getRoundPoints(member.round_points, round)}
                  />
                ))}
                <NumericStandingsCell value={member.selected_total_points} />
              </Table.Tr>
            );
          })}
        </Table.Tbody>
      </Table>
    </Table.ScrollContainer>
  );
}

function RankBadge({ rank }: { rank: number }) {
  if (rank === 0) {
    return (
      <Badge color="gold" variant="filled">
        1st
      </Badge>
    );
  }

  if (rank === 1) {
    return (
      <Badge color="gray" variant="filled">
        2nd
      </Badge>
    );
  }

  if (rank === 2) {
    return (
      <Badge color="orange" variant="filled">
        3rd
      </Badge>
    );
  }

  return rank + 1;
}

function NumericStandingsCell({
  value,
  ...props
}: { value: number } & Omit<ComponentProps<typeof Table.Td>, 'children'>) {
  return (
    <Table.Td
      {...props}
      style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}
    >
      {value}
    </Table.Td>
  );
}

export function StandingsContent({
  displayedMembers,
  isCurrentUser,
  isMobile,
  leagueId,
  rosterRoundSearch,
  showBreakdown,
  showSeasonWinner,
  userId,
  visibleRoundNumbers,
}: {
  displayedMembers: DisplayStandingsMemberRow[];
  isCurrentUser: (userId: string) => boolean;
  isMobile: boolean;
  leagueId: string;
  rosterRoundSearch: string;
  showBreakdown: boolean;
  showSeasonWinner: boolean;
  userId: string | undefined;
  visibleRoundNumbers: number[];
}) {
  const rosterBasePath = `/roster/${leagueId}`;

  return (
    <Card shadow="sm" padding="md" radius="md" withBorder>
      {isMobile ? (
        <MobileStandingsCards
          displayedMembers={displayedMembers}
          isCurrentUser={isCurrentUser}
          rosterBasePath={rosterBasePath}
          rosterRoundSearch={rosterRoundSearch}
          showBreakdown={showBreakdown}
          showSeasonWinner={showSeasonWinner}
          userId={userId}
          visibleRoundNumbers={visibleRoundNumbers}
        />
      ) : (
        <DesktopStandingsTable
          displayedMembers={displayedMembers}
          isCurrentUser={isCurrentUser}
          rosterBasePath={rosterBasePath}
          rosterRoundSearch={rosterRoundSearch}
          showBreakdown={showBreakdown}
          showSeasonWinner={showSeasonWinner}
          userId={userId}
          visibleRoundNumbers={visibleRoundNumbers}
        />
      )}
    </Card>
  );
}
