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
  members: Array<StandingsMemberRow & { selected_total_points: number }>,
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

  // Check if breakdown data exists
  const hasBreakdown = typedMembers.some(
    (m) => m.player_points != null || m.goalie_points != null
  );
  const showBreakdown = hasBreakdown && selectedRound === currentRound;

  // Check if round-by-round data exists
  const hasRoundPoints = typedMembers.some(
    (m) => m.round_points && Object.keys(m.round_points).length > 0
  );

  // Collect all round numbers across all members
  const roundNumbers = hasRoundPoints
    ? [
        ...new Set(
          typedMembers.flatMap((m) =>
            m.round_points ? Object.keys(m.round_points).map(Number) : []
          )
        ),
      ].sort((a, b) => a - b)
    : [];
  const visibleRoundNumbers = getVisibleRoundNumbers(
    roundNumbers,
    selectedRound
  );
  const showSeasonWinner = seasonComplete && selectedRound === currentRound;
  const handleRoundChange = (value: string) => {
    const nextRound = clampRoundSelection(value, currentRound);
    const nextSearchParams = new URLSearchParams(searchParams);

    if (nextRound === currentRound) {
      nextSearchParams.delete('round');
    } else {
      nextSearchParams.set('round', String(nextRound));
    }

    setSearchParams(nextSearchParams, { replace: true });
  };

  return (
    <Container size="lg" py="xl">
      <Stack gap="xl">
        <Group justify="space-between" align="flex-end">
          <div>
            <Title order={2}>Standings</Title>
            <Text c="dimmed">
              {selectedRound === currentRound
                ? `${league?.name} · Round ${currentRound}`
                : `${league?.name} · Viewing Round ${selectedRound} snapshot · Current Round ${currentRound}`}
            </Text>
          </div>
          <Button
            variant="light"
            onClick={() =>
              downloadCSV(
                displayedMembers,
                league?.name,
                selectedRound,
                currentRound
              )
            }
          >
            Export CSV
          </Button>
        </Group>

        {currentRound > 1 && (
          <SegmentedControl
            fullWidth
            value={String(selectedRound)}
            onChange={handleRoundChange}
            data={getAvailableRounds(currentRound).map((round) => ({
              label: `Round ${round}`,
              value: String(round),
            }))}
          />
        )}

        <Card shadow="sm" padding="md" radius="md" withBorder>
          {isMobile ? (
            <MobileCardList emptyMessage="No standings data">
              {displayedMembers.map((member, index) => {
                const isMe = member.user_id === user?.id;
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
                        {index === 0 ? (
                          <Badge color="gold" variant="filled" size="sm">
                            1st
                          </Badge>
                        ) : index === 1 ? (
                          <Badge color="gray" variant="filled" size="sm">
                            2nd
                          </Badge>
                        ) : index === 2 ? (
                          <Badge color="orange" variant="filled" size="sm">
                            3rd
                          </Badge>
                        ) : (
                          <Badge variant="light" size="sm">
                            {index + 1}
                          </Badge>
                        )}
                        <Anchor
                          component={Link}
                          to={`/roster/${leagueId}/${member.id}${rosterRoundSearch}`}
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
                          {isMe && (
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
                        {visibleRoundNumbers.map((r) => (
                          <Badge key={r} size="sm" variant="outline">
                            R{r}: {getRoundPoints(member.round_points, r)}
                          </Badge>
                        ))}
                      </Group>
                    )}
                  </Card>
                );
              })}
            </MobileCardList>
          ) : (
            <Table.ScrollContainer minWidth={600}>
              <Table striped highlightOnHover>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th style={{ width: 60 }}>Rank</Table.Th>
                    <Table.Th>Team</Table.Th>
                    <Table.Th>Manager</Table.Th>
                    {showBreakdown && (
                      <>
                        <Table.Th style={{ textAlign: 'right' }}>
                          Player Pts
                        </Table.Th>
                        <Table.Th style={{ textAlign: 'right' }}>
                          Goalie Pts
                        </Table.Th>
                      </>
                    )}
                    {visibleRoundNumbers.map((r) => (
                      <Table.Th key={r} style={{ textAlign: 'right' }}>
                        R{r}
                      </Table.Th>
                    ))}
                    <Table.Th style={{ textAlign: 'right' }}>Points</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {displayedMembers.map((member, index) => {
                    const isMe = member.user_id === user?.id;
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
                          {index === 0 ? (
                            <Badge color="gold" variant="filled">
                              1st
                            </Badge>
                          ) : index === 1 ? (
                            <Badge color="gray" variant="filled">
                              2nd
                            </Badge>
                          ) : index === 2 ? (
                            <Badge color="orange" variant="filled">
                              3rd
                            </Badge>
                          ) : (
                            index + 1
                          )}
                        </Table.Td>
                        <Table.Td>
                          <Anchor
                            component={Link}
                            to={`/roster/${leagueId}/${member.id}${rosterRoundSearch}`}
                            fw={isMe ? 700 : undefined}
                          >
                            {member.team_name}
                            {showSeasonWinner && index === 0 && ' 🏆'}
                          </Anchor>
                        </Table.Td>
                        <Table.Td>
                          {member.users?.display_name ?? 'Unknown'}
                          {isMe && (
                            <Badge size="xs" ml="xs" variant="light">
                              You
                            </Badge>
                          )}
                        </Table.Td>
                        {showBreakdown && (
                          <>
                            <Table.Td
                              style={{
                                textAlign: 'right',
                                fontVariantNumeric: 'tabular-nums',
                              }}
                            >
                              {member.player_points ?? 0}
                            </Table.Td>
                            <Table.Td
                              style={{
                                textAlign: 'right',
                                fontVariantNumeric: 'tabular-nums',
                              }}
                            >
                              {member.goalie_points ?? 0}
                            </Table.Td>
                          </>
                        )}
                        {visibleRoundNumbers.map((r) => (
                          <Table.Td
                            key={r}
                            style={{
                              textAlign: 'right',
                              fontVariantNumeric: 'tabular-nums',
                            }}
                          >
                            {getRoundPoints(member.round_points, r)}
                          </Table.Td>
                        ))}
                        <Table.Td
                          style={{
                            textAlign: 'right',
                            fontVariantNumeric: 'tabular-nums',
                          }}
                        >
                          {member.selected_total_points}
                        </Table.Td>
                      </Table.Tr>
                    );
                  })}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>
          )}
        </Card>
      </Stack>
    </Container>
  );
}
