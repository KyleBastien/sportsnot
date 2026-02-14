import { useParams } from 'react-router-dom';
import {
  ActionIcon,
  Container,
  Title,
  Text,
  Stack,
  Group,
  Card,
  Badge,
  Button,
  Table,
  Loader,
  Center,
  Alert,
  Modal,
  Tooltip,
} from '@mantine/core';
import { useState, useMemo } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { supabase, usePlayoffPlayers, usePlayoffTeams } from '@sportsnot/supabase';
import { useAuthContext } from '../../context/AuthContext';
import { useCompareContext, type ComparePlayer } from '../../context/CompareContext';
import { SCORING } from '@sportsnot/types';

function useMyRoster(leagueId: string) {
  const { user } = useAuthContext();

  return useQuery({
    queryKey: ['roster', leagueId, user?.id],
    queryFn: async () => {
      // Get the member for this league
      const { data: member } = await supabase
        .from('league_members')
        .select('id')
        .eq('league_id', leagueId)
        .eq('user_id', user!.id)
        .single();

      if (!member) throw new Error('Not a member of this league');

      // Get the league to know current round
      const { data: league } = await supabase
        .from('leagues')
        .select('current_round')
        .eq('id', leagueId)
        .single();

      if (!league) throw new Error('League not found');

      // Get roster for current round
      const { data: roster, error } = await supabase
        .from('rosters')
        .select('*')
        .eq('league_member_id', member.id)
        .eq('round', league.current_round);

      if (error) throw error;

      return {
        memberId: member.id,
        round: league.current_round,
        slots: roster ?? [],
      };
    },
    enabled: !!user,
  });
}

const POSITION_LABELS: Record<string, string> = {
  F: 'Forward',
  D: 'Defenseman',
  G: 'Goalie',
  IR_F: 'IR Forward',
  IR_D: 'IR Defenseman',
};

const POSITION_ORDER = ['F', 'D', 'G', 'IR_F', 'IR_D'];

export function RosterPage() {
  const { leagueId } = useParams<{ leagueId: string }>();
  const { data, isLoading, error } = useMyRoster(leagueId!);
  const queryClient = useQueryClient();
  const { players: comparePlayers, isFull: isCompareFull, addPlayer, removePlayer } = useCompareContext();
  const [irModal, setIrModal] = useState<{
    injuredSlotId: string;
    irSlotId: string;
  } | null>(null);
  const [activating, setActivating] = useState(false);

  // Fetch cached NHL data for player/team name lookups
  const currentSeason = '20242025'; // TODO: derive from NHL API
  const currentRound = data?.round ?? 1;
  const { data: playerStats } = usePlayoffPlayers(currentSeason, currentRound);
  const { data: teamStats } = usePlayoffTeams(currentSeason, currentRound);

  const playerLookup = useMemo(() => {
    const map = new Map<number, any>();
    playerStats?.forEach((p: any) => map.set(p.player_id, p));
    return map;
  }, [playerStats]);

  const teamLookup = useMemo(() => {
    const map = new Map<number, any>();
    teamStats?.forEach((t: any) => map.set(t.team_id, t));
    return map;
  }, [teamStats]);

  const comparePlayerIds = useMemo(
    () => new Set(comparePlayers.map((p) => p.playerId)),
    [comparePlayers]
  );

  const handleCompareToggle = (player: ComparePlayer) => {
    if (comparePlayers.some((p) => p.playerId === player.playerId)) {
      removePlayer(player.playerId);
    } else {
      addPlayer(player);
    }
  };

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
          Could not load your roster.
        </Alert>
      </Container>
    );
  }

  const { slots, round } = data;

  // Group slots by position
  const groupedSlots = POSITION_ORDER.map((pos) => ({
    position: pos,
    label: POSITION_LABELS[pos],
    players: slots.filter((s: any) => s.position === pos),
  }));

  const totalPoints = slots
    .filter((s: any) => s.is_active)
    .reduce((sum: number, s: any) => sum + (s.points_earned ?? 0), 0);

  const handleActivateIR = async () => {
    if (!irModal) return;
    setActivating(true);

    const { error: activateError } = await supabase.rpc('activate_ir_player', {
      p_league_member_id: data.memberId,
      p_round: round,
      p_injured_roster_id: irModal.injuredSlotId,
      p_ir_roster_id: irModal.irSlotId,
    });

    if (!activateError) {
      queryClient.invalidateQueries({ queryKey: ['roster', leagueId] });
    }

    setActivating(false);
    setIrModal(null);
  };

  return (
    <Container size="lg" py="xl">
      <Stack gap="xl">
        <Group justify="space-between">
          <div>
            <Title order={2}>My Roster</Title>
            <Text c="dimmed">Round {round}</Text>
          </div>
          <Card padding="md" radius="md" withBorder>
            <Stack gap={0} align="center">
              <Text size="sm" c="dimmed">
                Total Points
              </Text>
              <Text fw={700} size="xl">
                {totalPoints}
              </Text>
            </Stack>
          </Card>
        </Group>

        <Text size="sm" c="dimmed">
          Scoring: Goal = {SCORING.goal}pt · Assist = {SCORING.assist}pt · Win ={' '}
          {SCORING.win}pts · Shutout = {SCORING.shutout}pts
        </Text>

        {groupedSlots.map((group) => (
          <Card key={group.position} shadow="sm" padding="md" radius="md" withBorder>
            <Group justify="space-between" mb="sm">
              <Title order={4}>{group.label}</Title>
              <Badge variant="light">
                {group.players.length} player
                {group.players.length !== 1 ? 's' : ''}
              </Badge>
            </Group>

            {group.players.length === 0 ? (
              <Text c="dimmed" size="sm">
                No player drafted in this slot
              </Text>
            ) : (
              <Table>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th />
                    <Table.Th>Player/Team</Table.Th>
                    <Table.Th>Status</Table.Th>
                    <Table.Th style={{ textAlign: 'right' }}>Points</Table.Th>
                    <Table.Th>Actions</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {group.players.map((slot: any) => {
                    const isIrSlot =
                      slot.position === 'IR_F' || slot.position === 'IR_D';
                    const matchingPosition =
                      slot.position === 'IR_F' ? 'F' : 'D';
                    // Find an active injured player at the matching position
                    const injuredCandidates = slots.filter(
                      (s: any) =>
                        s.position === matchingPosition &&
                        s.is_active &&
                        s.id !== slot.id
                    );

                    // Resolve player/team info from stats cache
                    const playerInfo = slot.player_id ? playerLookup.get(slot.player_id) : null;
                    const teamInfo = slot.team_id ? teamLookup.get(slot.team_id) : null;
                    const displayName = playerInfo?.player_name ?? (teamInfo?.team_name ?? (slot.player_id ? `Player #${slot.player_id}` : `Team #${slot.team_id}`));
                    const compareId = slot.player_id ?? slot.team_id;
                    const inCompare = comparePlayerIds.has(compareId);

                    const buildComparePlayer = (): ComparePlayer => {
                      if (playerInfo) {
                        return {
                          playerId: slot.player_id,
                          name: playerInfo.player_name ?? `Player #${slot.player_id}`,
                          teamAbbrev: playerInfo.team_abbreviation ?? '',
                          position: playerInfo.position ?? slot.position,
                          stats: {
                            goals: playerInfo.goals ?? 0,
                            assists: playerInfo.assists ?? 0,
                            points: (playerInfo.goals ?? 0) + (playerInfo.assists ?? 0),
                            gamesPlayed: playerInfo.games_played ?? 0,
                            fantasyPoints: slot.points_earned ?? 0,
                          },
                        };
                      }
                      return {
                        playerId: slot.team_id,
                        name: teamInfo?.team_name ?? `Team #${slot.team_id}`,
                        teamAbbrev: teamInfo?.team_abbreviation ?? '',
                        position: 'G',
                        stats: {
                          wins: teamInfo?.wins ?? 0,
                          shutouts: teamInfo?.shutouts ?? 0,
                          fantasyPoints: slot.points_earned ?? 0,
                        },
                      };
                    };

                    return (
                      <Table.Tr key={slot.id}>
                        <Table.Td>
                          <Tooltip label={inCompare ? 'Remove from compare' : isCompareFull ? 'Compare full' : 'Add to compare'}>
                            <ActionIcon
                              size="sm"
                              variant={inCompare ? 'filled' : 'subtle'}
                              color={inCompare ? 'blue' : 'gray'}
                              disabled={!inCompare && isCompareFull}
                              onClick={() => handleCompareToggle(buildComparePlayer())}
                            >
                              {inCompare ? '✓' : '⚖'}
                            </ActionIcon>
                          </Tooltip>
                        </Table.Td>
                        <Table.Td>
                          {displayName}
                        </Table.Td>
                        <Table.Td>
                          {slot.is_active ? (
                            <Badge color="green" size="sm">
                              Active
                            </Badge>
                          ) : (
                            <Badge color="gray" size="sm">
                              Inactive
                            </Badge>
                          )}
                          {slot.activated_from_ir && (
                            <Badge color="orange" size="sm" ml="xs">
                              From IR
                            </Badge>
                          )}
                        </Table.Td>
                        <Table.Td style={{ textAlign: 'right' }}>
                          {slot.points_earned ?? 0}
                        </Table.Td>
                        <Table.Td>
                          {isIrSlot &&
                            !slot.activated_from_ir &&
                            injuredCandidates.length > 0 && (
                              <Button
                                size="xs"
                                variant="outline"
                                color="orange"
                                onClick={() =>
                                  setIrModal({
                                    injuredSlotId: injuredCandidates[0].id,
                                    irSlotId: slot.id,
                                  })
                                }
                              >
                                Activate IR
                              </Button>
                            )}
                        </Table.Td>
                      </Table.Tr>
                    );
                  })}
                </Table.Tbody>
              </Table>
            )}
          </Card>
        ))}

        {/* IR Activation Modal */}
        <Modal
          opened={!!irModal}
          onClose={() => setIrModal(null)}
          title="Activate IR Player"
        >
          <Stack gap="md">
            <Alert color="orange">
              Activating an IR player will remove all points from the injured
              player and retroactively grant the IR player's points for this
              round.
            </Alert>
            <Group justify="flex-end">
              <Button variant="subtle" onClick={() => setIrModal(null)}>
                Cancel
              </Button>
              <Button
                color="orange"
                onClick={handleActivateIR}
                loading={activating}
              >
                Activate IR Player
              </Button>
            </Group>
          </Stack>
        </Modal>
      </Stack>
    </Container>
  );
}
