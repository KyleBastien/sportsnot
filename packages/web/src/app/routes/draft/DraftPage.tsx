import { useState, useEffect, useMemo } from 'react';
import { useParams } from 'react-router-dom';
import {
  Container,
  Title,
  Text,
  Stack,
  Group,
  Card,
  Badge,
  Button,
  TextInput,
  SegmentedControl,
  Loader,
  Center,
  Alert,
  Modal,
  Table,
  ScrollArea,
} from '@mantine/core';
import { useQuery } from '@tanstack/react-query';
import { supabase, usePlayoffPlayers, usePlayoffTeams } from '@sportsnot/supabase';
import { useAuthContext } from '../../context/AuthContext';
import type { Position } from '@sportsnot/types';

interface DraftablePlayer {
  id: number;
  fullName: string;
  firstName: string;
  lastName: string;
  position: string;
  team: string;
  teamId: number;
  headshot?: string;
}

function useDraft(leagueId: string) {
  return useQuery({
    queryKey: ['draft', leagueId],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('drafts')
        .select('*, draft_picks(*, league_members(team_name, user_id))')
        .eq('league_id', leagueId)
        .order('round', { ascending: false })
        .limit(1)
        .single();

      if (error) throw error;
      return data;
    },
    refetchInterval: 3000, // Poll every 3s for real-time feel
  });
}

function useLeagueMembers(leagueId: string) {
  return useQuery({
    queryKey: ['league-members', leagueId],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('league_members')
        .select('id, user_id, team_name, total_points, users(display_name)')
        .eq('league_id', leagueId);

      if (error) throw error;
      return data ?? [];
    },
  });
}

interface AvailablePlayerBoardProps {
  playerStats: any[];
  teamStats: any[];
  draftedPlayerIds: Set<number>;
  draftedTeamIds: Set<number>;
  positionFilter: string;
  searchQuery: string;
  isMyTurn: boolean;
  onSelectPlayer: (player: DraftablePlayer) => void;
}

function AvailablePlayerBoard({
  playerStats,
  teamStats,
  draftedPlayerIds,
  draftedTeamIds,
  positionFilter,
  searchQuery,
  isMyTurn,
  onSelectPlayer,
}: AvailablePlayerBoardProps) {
  const query = searchQuery.toLowerCase();

  // Build skater rows from player_stats_cache
  const skaterRows = playerStats
    .filter((p) => !draftedPlayerIds.has(p.player_id))
    .filter((p) => !p.is_injured)
    .map((p) => ({
      id: p.player_id,
      fullName: p.player_name ?? `Player #${p.player_id}`,
      firstName: '',
      lastName: '',
      position: p.position ?? 'F',
      team: p.team_abbreviation ?? 'NHL',
      teamId: 0,
      goals: p.goals ?? 0,
      assists: p.assists ?? 0,
      points: (p.goals ?? 0) + (p.assists ?? 0),
      gamesPlayed: p.games_played ?? 0,
    }));

  // Build team/goalie rows from team_stats_cache
  const teamRows = teamStats
    .filter((t) => !draftedTeamIds.has(t.team_id))
    .filter((t) => !t.is_eliminated)
    .map((t) => ({
      id: t.team_id,
      fullName: t.team_name ?? `Team #${t.team_id}`,
      firstName: '',
      lastName: '',
      position: 'G' as const,
      team: t.team_abbreviation ?? `Team #${t.team_id}`,
      teamId: t.team_id,
      wins: t.wins ?? 0,
      shutouts: t.shutouts ?? 0,
    }));

  const filteredSkaters = skaterRows.filter((p) => {
    if (positionFilter !== 'ALL' && positionFilter !== 'F' && positionFilter !== 'D') return false;
    if (positionFilter === 'F' && p.position !== 'F') return false;
    if (positionFilter === 'D' && p.position !== 'D') return false;
    if (query && !p.fullName.toLowerCase().includes(query)) return false;
    return true;
  });

  const filteredTeams = teamRows.filter((t) => {
    if (positionFilter !== 'ALL' && positionFilter !== 'G') return false;
    if (query && !t.fullName.toLowerCase().includes(query)) return false;
    return true;
  });

  const showSkaters = positionFilter !== 'G';
  const showTeams = positionFilter === 'ALL' || positionFilter === 'G';

  return (
    <Stack gap="md">
      {showSkaters && (
        <>
          <Text fw={600} size="sm">Skaters ({filteredSkaters.length} available)</Text>
          <ScrollArea h={300}>
            <Table striped highlightOnHover>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Player</Table.Th>
                  <Table.Th>Pos</Table.Th>
                  <Table.Th style={{ textAlign: 'right' }}>G</Table.Th>
                  <Table.Th style={{ textAlign: 'right' }}>A</Table.Th>
                  <Table.Th style={{ textAlign: 'right' }}>Pts</Table.Th>
                  <Table.Th style={{ textAlign: 'right' }}>GP</Table.Th>
                  {isMyTurn && <Table.Th />}
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {filteredSkaters.map((p) => (
                  <Table.Tr key={p.id}>
                    <Table.Td>{p.fullName}</Table.Td>
                    <Table.Td>
                      <Badge size="xs" variant="light">{p.position}</Badge>
                    </Table.Td>
                    <Table.Td style={{ textAlign: 'right' }}>{p.goals}</Table.Td>
                    <Table.Td style={{ textAlign: 'right' }}>{p.assists}</Table.Td>
                    <Table.Td style={{ textAlign: 'right', fontWeight: 600 }}>{p.points}</Table.Td>
                    <Table.Td style={{ textAlign: 'right' }}>{p.gamesPlayed}</Table.Td>
                    {isMyTurn && (
                      <Table.Td>
                        <Button
                          size="xs"
                          variant="light"
                          onClick={() =>
                            onSelectPlayer({
                              id: p.id,
                              fullName: p.fullName,
                              firstName: p.firstName,
                              lastName: p.lastName,
                              position: p.position,
                              team: p.team,
                              teamId: p.teamId,
                            })
                          }
                        >
                          Draft
                        </Button>
                      </Table.Td>
                    )}
                  </Table.Tr>
                ))}
                {filteredSkaters.length === 0 && (
                  <Table.Tr>
                    <Table.Td colSpan={isMyTurn ? 7 : 6}>
                      <Text c="dimmed" ta="center" size="sm">No available skaters match your filters</Text>
                    </Table.Td>
                  </Table.Tr>
                )}
              </Table.Tbody>
            </Table>
          </ScrollArea>
        </>
      )}

      {showTeams && (
        <>
          <Text fw={600} size="sm">Teams / Goaltending ({filteredTeams.length} available)</Text>
          <Table striped highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Team</Table.Th>
                <Table.Th style={{ textAlign: 'right' }}>Wins</Table.Th>
                <Table.Th style={{ textAlign: 'right' }}>Shutouts</Table.Th>
                {isMyTurn && <Table.Th />}
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {filteredTeams.map((t) => (
                <Table.Tr key={t.teamId}>
                  <Table.Td>{t.fullName}</Table.Td>
                  <Table.Td style={{ textAlign: 'right' }}>{t.wins}</Table.Td>
                  <Table.Td style={{ textAlign: 'right' }}>{t.shutouts}</Table.Td>
                  {isMyTurn && (
                    <Table.Td>
                      <Button
                        size="xs"
                        variant="light"
                        onClick={() =>
                          onSelectPlayer({
                            id: t.teamId,
                            fullName: t.fullName,
                            firstName: '',
                            lastName: '',
                            position: 'G',
                            team: t.team,
                            teamId: t.teamId,
                          })
                        }
                      >
                        Draft
                      </Button>
                    </Table.Td>
                  )}
                </Table.Tr>
              ))}
              {filteredTeams.length === 0 && (
                <Table.Tr>
                  <Table.Td colSpan={isMyTurn ? 4 : 3}>
                    <Text c="dimmed" ta="center" size="sm">No available teams match your filters</Text>
                  </Table.Td>
                </Table.Tr>
              )}
            </Table.Tbody>
          </Table>
        </>
      )}
    </Stack>
  );
}

export function DraftPage() {
  const { leagueId } = useParams<{ leagueId: string }>();
  const { user } = useAuthContext();
  const { data: draft, isLoading: draftLoading } = useDraft(leagueId!);
  const { data: members } = useLeagueMembers(leagueId!);
  const [positionFilter, setPositionFilter] = useState('ALL');
  const [searchQuery, setSearchQuery] = useState('');
  const [confirmPlayer, setConfirmPlayer] = useState<DraftablePlayer | null>(null);
  const [confirmPosition, setConfirmPosition] = useState<Position>('F');
  const [submitting, setSubmitting] = useState(false);

  // Fetch cached NHL data
  const currentSeason = '20242025'; // TODO: derive from NHL API
  const currentRound = draft?.round ?? 1;
  const { data: playerStats } = usePlayoffPlayers(currentSeason, currentRound);
  const { data: teamStats } = usePlayoffTeams(currentSeason, currentRound);

  // Derived state — compute before early returns to keep hook order stable
  const draftOrder: string[] = (draft?.draft_order as string[]) ?? [];
  const picks = draft?.draft_picks ?? [];

  const currentPickIndex = draft ? draft.current_pick - 1 : 0;
  const currentPickerUserId = draftOrder[currentPickIndex];
  const isMyTurn = currentPickerUserId === user?.id;
  const myMember = members?.find((m: any) => m.user_id === user?.id);
  const currentPicker = members?.find(
    (m: any) => m.user_id === currentPickerUserId
  );

  // Track which players/teams have already been drafted
  const draftedPlayerIds = useMemo(
    () => new Set<number>(picks.filter((p: any) => p.player_id).map((p: any) => p.player_id as number)),
    [picks]
  );
  const draftedTeamIds = useMemo(
    () => new Set<number>(picks.filter((p: any) => p.team_id).map((p: any) => p.team_id as number)),
    [picks]
  );

  // Subscribe to real-time draft changes
  useEffect(() => {
    if (!leagueId) return;

    const channel = supabase
      .channel(`draft-${leagueId}`)
      .on(
        'postgres_changes',
        { event: '*', schema: 'public', table: 'draft_picks' },
        () => {
          // Refetch handled by react-query refetchInterval
        }
      )
      .on(
        'postgres_changes',
        { event: '*', schema: 'public', table: 'drafts' },
        () => {
          // Refetch handled by react-query refetchInterval
        }
      )
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, [leagueId]);

  if (draftLoading) {
    return (
      <Center h="50vh">
        <Loader size="lg" />
      </Center>
    );
  }

  if (!draft) {
    return (
      <Container size="md" py="xl">
        <Alert color="blue" title="No Active Draft">
          No draft has been started for this league yet.
        </Alert>
      </Container>
    );
  }

  const handleConfirmPick = async () => {
    if (!confirmPlayer || !myMember || !draft) return;

    setSubmitting(true);

    const isGoalie = confirmPosition === 'G';

    const { error } = await supabase.from('draft_picks').insert({
      draft_id: draft.id,
      league_member_id: myMember.id,
      pick_number: draft.current_pick,
      player_id: isGoalie ? null : confirmPlayer.id,
      team_id: isGoalie ? confirmPlayer.teamId : null,
      position: confirmPosition,
    });

    if (!error) {
      // Also create the corresponding roster entry
      await supabase.from('rosters').insert({
        league_member_id: myMember.id,
        round: draft.round,
        player_id: isGoalie ? null : confirmPlayer.id,
        team_id: isGoalie ? confirmPlayer.teamId : null,
        position: confirmPosition,
      });

      const totalExpectedPicks = draftOrder.length; // snake order already expanded
      const nextPick = draft.current_pick + 1;

      if (nextPick > totalExpectedPicks) {
        // Draft is complete — mark draft as completed and league as active
        await supabase
          .from('drafts')
          .update({
            status: 'completed',
            current_pick: nextPick,
            completed_at: new Date().toISOString(),
          })
          .eq('id', draft.id);

        await supabase
          .from('leagues')
          .update({ status: 'active' })
          .eq('id', draft.league_id);
      } else {
        // Advance the pick
        await supabase
          .from('drafts')
          .update({ current_pick: nextPick })
          .eq('id', draft.id);
      }
    }

    setSubmitting(false);
    setConfirmPlayer(null);
  };

  return (
    <Container size="xl" py="xl">
      <Stack gap="xl">
        {/* Draft Header */}
        <Group justify="space-between">
          <div>
            <Title order={2}>Draft Room</Title>
            <Text c="dimmed">Round {draft.round}</Text>
          </div>
          <Card padding="md" radius="md" withBorder>
            <Stack gap={4} align="center">
              <Text size="sm" c="dimmed">
                Pick #{draft.current_pick}
              </Text>
              <Text fw={700} size="lg">
                {currentPicker
                  ? (currentPicker as any).team_name
                  : 'Unknown'}
              </Text>
              {isMyTurn && (
                <Badge color="green" size="lg">
                  Your Turn!
                </Badge>
              )}
            </Stack>
          </Card>
        </Group>

        {/* Filters */}
        <Group>
          <SegmentedControl
            value={positionFilter}
            onChange={setPositionFilter}
            data={[
              { label: 'All', value: 'ALL' },
              { label: 'Forwards', value: 'F' },
              { label: 'Defense', value: 'D' },
              { label: 'Goalies', value: 'G' },
            ]}
          />
          <TextInput
            placeholder="Search players..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.currentTarget.value)}
            style={{ flex: 1 }}
          />
        </Group>

        {/* Draft History */}
        <Card shadow="sm" padding="md" radius="md" withBorder>
          <Title order={4} mb="sm">
            Draft History
          </Title>
          {picks.length === 0 ? (
            <Text c="dimmed" size="sm">
              No picks yet
            </Text>
          ) : (
            <Stack gap="xs">
              {[...picks]
                .sort(
                  (a: any, b: any) =>
                    (b.pick_number ?? 0) - (a.pick_number ?? 0)
                )
                .slice(0, 10)
                .map((pick: any) => (
                  <Group key={pick.id} justify="space-between">
                    <Text size="sm">
                      #{pick.pick_number} -{' '}
                      {pick.league_members?.team_name ?? 'Unknown'}
                    </Text>
                    <Badge variant="light" size="sm">
                      {pick.position}
                    </Badge>
                  </Group>
                ))}
            </Stack>
          )}
        </Card>

        {/* Available Players */}
        <Card shadow="sm" padding="md" radius="md" withBorder>
          <Title order={4} mb="sm">
            Available Players
          </Title>
          {!playerStats?.length && !teamStats?.length ? (
            <Stack gap="sm">
              <Text size="sm" c="dimmed">
                No player data available yet. Ensure the NHL stats sync edge
                function has been run to populate playoff player data.
              </Text>
              {isMyTurn ? (
                <Alert color="green" title="It's your turn!">
                  Once player data is synced, you'll see a selectable list here.
                </Alert>
              ) : (
                <Alert color="blue">
                  Waiting for{' '}
                  {currentPicker
                    ? (currentPicker as any).team_name
                    : 'the next drafter'}{' '}
                  to make their pick...
                </Alert>
              )}
            </Stack>
          ) : (
            <AvailablePlayerBoard
              playerStats={playerStats ?? []}
              teamStats={teamStats ?? []}
              draftedPlayerIds={draftedPlayerIds}
              draftedTeamIds={draftedTeamIds}
              positionFilter={positionFilter}
              searchQuery={searchQuery}
              isMyTurn={isMyTurn}
              onSelectPlayer={(player) => {
                setConfirmPlayer(player);
                setConfirmPosition(
                  player.position === 'G'
                    ? 'G'
                    : player.position === 'D'
                      ? 'D'
                      : 'F'
                );
              }}
            />
          )}
        </Card>

        {/* Confirm Pick Modal */}
        <Modal
          opened={!!confirmPlayer}
          onClose={() => setConfirmPlayer(null)}
          title="Confirm Draft Pick"
        >
          {confirmPlayer && (
            <Stack gap="md">
              <Text>
                Draft <strong>{confirmPlayer.fullName}</strong> (
                {confirmPlayer.team})?
              </Text>
              <SegmentedControl
                value={confirmPosition}
                onChange={(val) => setConfirmPosition(val as Position)}
                data={
                  confirmPlayer.position === 'G'
                    ? [{ label: 'Goalie', value: 'G' }]
                    : confirmPlayer.position === 'D'
                      ? [
                          { label: 'Defense', value: 'D' },
                          { label: 'IR Defense', value: 'IR_D' },
                        ]
                      : [
                          { label: 'Forward', value: 'F' },
                          { label: 'IR Forward', value: 'IR_F' },
                        ]
                }
              />
              <Group justify="flex-end">
                <Button
                  variant="subtle"
                  onClick={() => setConfirmPlayer(null)}
                >
                  Cancel
                </Button>
                <Button onClick={handleConfirmPick} loading={submitting}>
                  Confirm Pick
                </Button>
              </Group>
            </Stack>
          )}
        </Modal>
      </Stack>
    </Container>
  );
}
