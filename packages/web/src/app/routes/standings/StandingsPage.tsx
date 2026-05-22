import { Link, useParams, useSearchParams } from 'react-router-dom';
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
  Button,
  Group,
  Anchor,
  SegmentedControl,
} from '@mantine/core';
import { useQuery } from '@tanstack/react-query';
import { supabase } from '@sportsnot/supabase';
import { useAuthContext } from '../../context/AuthContext';
import { useMockStandings } from '../../../mock/hooks/useMockStandings';
import { useRoundComplete } from '../../hooks/useRoundComplete';
import { useWinnerConfetti } from '../../hooks/useWinnerConfetti';
import { useIsMobile, MobileCardList, DataRow } from '@sportsnot/ui';
import {
  buildRoundSearch,
  clampRoundSelection,
  getAvailableRounds,
  getRoundPoints,
} from '../../utils/roundUtils';
import {
  buildStandingsMembers,
  getVisibleRoundNumbers,
} from './standingsUtils';
import type { ComponentProps } from 'react';

const IS_MOCK = import.meta.env.VITE_MOCK_MODE === 'true';

interface StandingsMemberRow {
  id: string;
  user_id: string;
  team_name: string;
  total_points: number;
  player_points?: number | null;
  goalie_points?: number | null;
  round_points?: Record<string, number> | null;
  users?: { display_name?: string } | null;
}

interface DisplayStandingsMemberRow extends StandingsMemberRow {
  selected_total_points: number;
}

function useStandings(leagueId: string) {
  const mockResult = useMockStandings(leagueId);

  const queryResult = useQuery({
    queryKey: ['standings', leagueId],
    queryFn: async () => {
      const { data: league } = await supabase
        .from('leagues')
        .select('name, current_round')
        .eq('id', leagueId)
        .single();

      const { data: members, error } = await supabase
        .from('league_members')
        .select(
          'id, user_id, team_name, total_points, player_points, goalie_points, round_points, users(display_name)'
        )
        .eq('league_id', leagueId)
        .order('total_points', { ascending: false });

      if (error) throw error;

      return {
        league,
        members: members ?? [],
      };
    },
    enabled: !IS_MOCK,
  });

  return IS_MOCK ? mockResult : queryResult;
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

function buildStandingsSubtitle(
  leagueName: string | undefined,
  selectedRound: number,
  currentRound: number
) {
  if (selectedRound === currentRound) {
    return `${leagueName} · Current standings (R${currentRound})`;
  }

  return `${leagueName} · Viewing snapshot R${selectedRound} · Current R${currentRound}`;
}

function hasBreakdownData(members: StandingsMemberRow[]) {
  return members.some(
    (member) => member.player_points != null || member.goalie_points != null
  );
}

function collectRoundNumbers(members: StandingsMemberRow[]) {
  return [
    ...new Set(
      members.flatMap((member) =>
        member.round_points ? Object.keys(member.round_points).map(Number) : []
      )
    ),
  ].sort((a, b) => a - b);
}

function buildNextSearchParams(
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

function StandingsRoundSelector({
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

function StandingsHeader({
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

export function StandingsPage() {
  const { leagueId } = useParams<{ leagueId: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const { user } = useAuthContext();
  const { data, isLoading, error } = useStandings(leagueId!);

  const currentRound = Math.max(data?.league?.current_round ?? 1, 1);
  const selectedRound = clampRoundSelection(
    searchParams.get('round'),
    currentRound
  );
  const { seasonComplete } = useRoundComplete(currentRound);

  const typedMembers = (data?.members ?? []) as StandingsMemberRow[];
  const winnerId = seasonComplete ? typedMembers[0]?.user_id : undefined;
  const displayedMembers = buildStandingsMembers(
    typedMembers,
    selectedRound,
    currentRound
  );
  const rosterRoundSearch = buildRoundSearch(selectedRound, currentRound);

  useWinnerConfetti({
    seasonComplete,
    isWinner: !!winnerId && winnerId === user?.id,
    leagueId,
  });

  const isMobile = useIsMobile();
  const isCurrentUser = (memberUserId: string) => memberUserId === user?.id;

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

  const { league } = data;
  const hasBreakdown = hasBreakdownData(typedMembers);
  const showBreakdown = hasBreakdown && selectedRound === currentRound;
  const visibleRoundNumbers = getVisibleRoundNumbers(
    collectRoundNumbers(typedMembers),
    selectedRound
  );
  const showSeasonWinner = seasonComplete && selectedRound === currentRound;
  const handleRoundChange = (value: string) => {
    const nextRound = clampRoundSelection(value, currentRound);
    setSearchParams(
      buildNextSearchParams(searchParams, nextRound, currentRound),
      { replace: true }
    );
  };

  return (
    <Container size="lg" py="xl">
      <Stack gap="xl">
        <StandingsHeader
          currentRound={currentRound}
          displayedMembers={displayedMembers}
          leagueName={league?.name}
          selectedRound={selectedRound}
        />
        <StandingsRoundSelector
          currentRound={currentRound}
          selectedRound={selectedRound}
          onRoundChange={handleRoundChange}
        />

        <Card shadow="sm" padding="md" radius="md" withBorder>
          {isMobile ? (
            <MobileStandingsCards
              displayedMembers={displayedMembers}
              isCurrentUser={isCurrentUser}
              rosterBasePath={`/roster/${leagueId}`}
              rosterRoundSearch={rosterRoundSearch}
              showBreakdown={showBreakdown}
              showSeasonWinner={showSeasonWinner}
              userId={user?.id}
              visibleRoundNumbers={visibleRoundNumbers}
            />
          ) : (
            <DesktopStandingsTable
              displayedMembers={displayedMembers}
              isCurrentUser={isCurrentUser}
              rosterBasePath={`/roster/${leagueId}`}
              rosterRoundSearch={rosterRoundSearch}
              showBreakdown={showBreakdown}
              showSeasonWinner={showSeasonWinner}
              userId={user?.id}
              visibleRoundNumbers={visibleRoundNumbers}
            />
          )}
        </Card>
      </Stack>
    </Container>
  );
}
