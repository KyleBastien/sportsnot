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
  Table,
  Loader,
  Center,
  Alert,
  Modal,
  Radio,
} from '@mantine/core';
import { useState, useMemo } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  supabase,
  useLeague,
  usePlayoffPlayers,
  usePlayoffTeams,
} from '@sportsnot/supabase';
import { useAuthContext } from '../../context/AuthContext';
import { SCORING } from '@sportsnot/types';
import {
  buildPlayerNameMap,
  buildTeamNameMap,
  resolvePickName,
} from '@sportsnot/utils';
import {
  useMockRoster,
  useMockActivateIR,
} from '../../../mock/hooks/useMockRoster';
import { useMockLeague } from '../../../mock/hooks/useMockLeagues';
import {
  useMockPlayoffPlayers,
  useMockPlayoffTeams,
} from '../../../mock/hooks/useMockNhlApi';
import { groupHasActions } from './rosterUtils';

const IS_MOCK = import.meta.env.VITE_MOCK_MODE === 'true';

interface RosterSlotRow {
  id: string;
  league_member_id: string;
  round: number;
  player_id: number | null;
  team_id: number | null;
  position: string;
  is_active: boolean;
  points_earned: number;
  activated_from_ir: boolean;
  is_eliminated?: boolean;
}

function useMyRoster(leagueId: string) {
  const mockResult = useMockRoster(leagueId);
  const { user } = useAuthContext();

  const queryResult = useQuery({
    queryKey: ['roster', leagueId, user?.id],
    queryFn: async () => {
      // Get the member for this league
      const { data: member } = await supabase
        .from('league_members')
        .select('id, total_points')
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
        // Live mode: is_eliminated defaults to false (TODO: derive from team_stats_cache)
        slots: (roster ?? []).map((s: RosterSlotRow) => ({
          ...s,
          is_eliminated: s.is_eliminated ?? false,
        })),
        totalPoints: member.total_points ?? 0,
      };
    },
    enabled: !IS_MOCK && !!user,
  });

  return IS_MOCK ? mockResult : queryResult;
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

  // Fetch league's allow_ir_slots setting
  const mockLeagueResult = useMockLeague(leagueId);
  const realLeagueResult = useLeague(leagueId);
  const leagueData = IS_MOCK ? mockLeagueResult.data : realLeagueResult.data;
  const allowIrSlots = (leagueData?.allow_ir_slots ?? true) as boolean;

  const positionOrder = allowIrSlots
    ? POSITION_ORDER
    : POSITION_ORDER.filter((p) => p !== 'IR_F' && p !== 'IR_D');

  const [irModal, setIrModal] = useState<{
    irSlotId: string;
    candidates: RosterSlotRow[];
  } | null>(null);
  const [selectedInjuredSlotId, setSelectedInjuredSlotId] = useState<
    string | null
  >(null);
  const [activating, setActivating] = useState(false);
  const mockActivateIR = useMockActivateIR();

  // Fetch player/team stats for name resolution
  const currentSeason = '20242025';
  const currentRound = data?.round ?? 1;
  // For Round 4, use Round 3 stats so eliminated players' names are still resolved
  const nameResolutionRound = currentRound >= 4 ? 3 : currentRound;
  const mockPlayerResult = useMockPlayoffPlayers(
    currentSeason,
    nameResolutionRound
  );
  const supabasePlayerResult = usePlayoffPlayers(
    currentSeason,
    nameResolutionRound
  );
  const { data: playerStats } = IS_MOCK
    ? mockPlayerResult
    : supabasePlayerResult;
  const mockTeamResult = useMockPlayoffTeams(
    currentSeason,
    nameResolutionRound
  );
  const supabaseTeamResult = usePlayoffTeams(
    currentSeason,
    nameResolutionRound
  );
  const { data: teamStats } = IS_MOCK ? mockTeamResult : supabaseTeamResult;

  const playerNameMap = useMemo(
    () => buildPlayerNameMap(playerStats ?? []),
    [playerStats]
  );
  const teamNameMap = useMemo(
    () => buildTeamNameMap(teamStats ?? []),
    [teamStats]
  );

  const injuredPlayerIds = useMemo(() => {
    const ids = new Set<number>();
    for (const p of playerStats ?? []) {
      if (p.is_injured) {
        ids.add(p.player_id);
      }
    }
    return ids;
  }, [playerStats]);

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

  // Show empty state when no roster exists for this round (e.g. before re-draft)
  if (slots.length === 0) {
    return (
      <Container size="md" py="xl">
        <Stack gap="lg" align="center">
          <Title order={2}>My Roster</Title>
          <Text c="dimmed">Round {round}</Text>
          <Alert color="navy" title="No Roster Yet">
            Your roster for Round {round} has not been set yet. Waiting for the
            draft to begin.
          </Alert>
        </Stack>
      </Container>
    );
  }

  // Group slots by position
  const groupedSlots = positionOrder.map((pos) => ({
    position: pos,
    label: POSITION_LABELS[pos],
    players: slots.filter((s: RosterSlotRow) => s.position === pos),
  }));

  const roundPoints = slots
    .filter((s: RosterSlotRow) => s.is_active)
    .reduce((sum: number, s: RosterSlotRow) => sum + (s.points_earned ?? 0), 0);

  const totalPoints = data.totalPoints ?? 0;

  const handleActivateIR = async () => {
    if (!irModal || !selectedInjuredSlotId) return;
    setActivating(true);

    if (IS_MOCK && mockActivateIR) {
      mockActivateIR.mutate({
        leagueMemberId: data.memberId,
        slotId: irModal.irSlotId,
      });
      setActivating(false);
      setIrModal(null);
      setSelectedInjuredSlotId(null);
      return;
    }

    const { error: activateError } = await supabase.rpc('activate_ir_player', {
      p_league_member_id: data.memberId,
      p_round: round,
      p_injured_roster_id: selectedInjuredSlotId,
      p_ir_roster_id: irModal.irSlotId,
    });

    if (!activateError) {
      queryClient.invalidateQueries({ queryKey: ['roster', leagueId] });
    }

    setActivating(false);
    setIrModal(null);
    setSelectedInjuredSlotId(null);
  };

  return (
    <Container size="lg" py="xl">
      <Stack gap="xl">
        <Group justify="space-between">
          <div>
            <Title order={2}>My Roster</Title>
            <Text c="dimmed">Round {round}</Text>
          </div>
          <Group gap="md">
            <Card padding="md" radius="md" withBorder>
              <Stack gap={0} align="center">
                <Text size="sm" c="dimmed">
                  Round {round} Points
                </Text>
                <Text fw={700} size="xl">
                  {roundPoints}
                </Text>
              </Stack>
            </Card>
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
        </Group>

        <Text size="sm" c="dimmed">
          Scoring: Goal = {SCORING.goal}pt · Assist = {SCORING.assist}pt · Win ={' '}
          {SCORING.win}pts · Shutout = {SCORING.shutout}pts
        </Text>

        {groupedSlots.map((group) => {
          const hasAnyActions = groupHasActions(
            group.position,
            group.players,
            slots,
            injuredPlayerIds
          );

          return (
            <Card
              key={group.position}
              shadow="sm"
              padding="md"
              radius="md"
              withBorder
            >
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
                      <Table.Th>Player/Team</Table.Th>
                      <Table.Th>Status</Table.Th>
                      <Table.Th style={{ textAlign: 'right' }}>Points</Table.Th>
                      {hasAnyActions && <Table.Th>Actions</Table.Th>}
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {group.players.map((slot: RosterSlotRow) => {
                      const isIrSlot =
                        slot.position === 'IR_F' || slot.position === 'IR_D';
                      const matchingPosition =
                        slot.position === 'IR_F' ? 'F' : 'D';
                      // Find active, injured players at the matching position
                      const injuredCandidates = slots.filter(
                        (s: RosterSlotRow) =>
                          s.position === matchingPosition &&
                          s.is_active &&
                          s.id !== slot.id &&
                          s.player_id !== null &&
                          injuredPlayerIds.has(s.player_id)
                      );

                      return (
                        <Table.Tr key={slot.id}>
                          <Table.Td>
                            <span
                              style={
                                slot.is_eliminated
                                  ? { textDecoration: 'line-through' }
                                  : undefined
                              }
                            >
                              {resolvePickName(
                                slot.player_id,
                                slot.team_id,
                                playerNameMap,
                                teamNameMap
                              )}
                            </span>
                          </Table.Td>
                          <Table.Td>
                            {slot.is_eliminated ? (
                              <Badge color="red" size="sm">
                                Eliminated
                              </Badge>
                            ) : slot.is_active ? (
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
                          {hasAnyActions && (
                            <Table.Td>
                              {isIrSlot &&
                                !slot.activated_from_ir &&
                                injuredCandidates.length > 0 && (
                                  <Button
                                    size="xs"
                                    variant="outline"
                                    color="orange"
                                    onClick={() => {
                                      setIrModal({
                                        irSlotId: slot.id,
                                        candidates: injuredCandidates,
                                      });
                                      setSelectedInjuredSlotId(
                                        injuredCandidates[0].id
                                      );
                                    }}
                                  >
                                    Activate IR
                                  </Button>
                                )}
                            </Table.Td>
                          )}
                        </Table.Tr>
                      );
                    })}
                  </Table.Tbody>
                </Table>
              )}
            </Card>
          );
        })}

        {/* IR Activation Modal */}
        <Modal
          opened={!!irModal}
          onClose={() => {
            setIrModal(null);
            setSelectedInjuredSlotId(null);
          }}
          title="Activate IR Player"
        >
          {irModal && (
            <Stack gap="md">
              <Alert color="orange">
                Activating an IR player will remove all points from the injured
                player and retroactively grant the IR player&apos;s points for
                this round.
              </Alert>
              <Text fw={500} size="sm">
                Select the injured player to replace:
              </Text>
              <Radio.Group
                value={selectedInjuredSlotId ?? ''}
                onChange={setSelectedInjuredSlotId}
              >
                <Stack gap="xs">
                  {irModal.candidates.map((candidate) => (
                    <Radio
                      key={candidate.id}
                      value={candidate.id}
                      label={resolvePickName(
                        candidate.player_id,
                        candidate.team_id,
                        playerNameMap,
                        teamNameMap
                      )}
                    />
                  ))}
                </Stack>
              </Radio.Group>
              <Group justify="flex-end">
                <Button
                  variant="subtle"
                  onClick={() => {
                    setIrModal(null);
                    setSelectedInjuredSlotId(null);
                  }}
                >
                  Cancel
                </Button>
                <Button
                  color="orange"
                  onClick={handleActivateIR}
                  loading={activating}
                  disabled={!selectedInjuredSlotId}
                >
                  Activate IR Player
                </Button>
              </Group>
            </Stack>
          )}
        </Modal>
      </Stack>
    </Container>
  );
}
