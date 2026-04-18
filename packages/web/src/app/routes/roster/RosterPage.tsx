import { useParams, useNavigate } from 'react-router-dom';
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
  Select,
} from '@mantine/core';
import { useState, useMemo } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  supabase,
  useLeague,
  usePlayoffPlayers,
  usePlayoffTeams,
  useRegularSeasonPlayers,
} from '@sportsnot/supabase';
import { useAuthContext } from '../../context/AuthContext';
import { SCORING, CURRENT_SEASON } from '@sportsnot/types';
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
  useMockRegularSeasonPlayers,
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

function useMemberRoster(leagueId: string, leagueMemberId?: string) {
  const mockResult = useMockRoster(leagueId, leagueMemberId);
  const { user } = useAuthContext();

  const queryResult = useQuery({
    queryKey: ['roster', leagueId, leagueMemberId ?? user?.id],
    queryFn: async () => {
      let memberId = leagueMemberId;
      let memberTotalPoints = 0;

      if (memberId) {
        const { data: member } = await supabase
          .from('league_members')
          .select('id, total_points')
          .eq('id', memberId)
          .single();

        if (!member) throw new Error('Member not found');
        memberTotalPoints = member.total_points ?? 0;
      } else {
        const { data: member } = await supabase
          .from('league_members')
          .select('id, total_points')
          .eq('league_id', leagueId)
          .eq('user_id', user!.id)
          .single();

        if (!member) throw new Error('Not a member of this league');
        memberId = member.id;
        memberTotalPoints = member.total_points ?? 0;
      }

      const { data: league } = await supabase
        .from('leagues')
        .select('current_round')
        .eq('id', leagueId)
        .single();

      if (!league) throw new Error('League not found');

      const { data: roster, error } = await supabase
        .from('rosters')
        .select('*')
        .eq('league_member_id', memberId)
        .eq('round', league.current_round);

      if (error) throw error;

      return {
        memberId: memberId as string,
        round: league.current_round,
        slots: (roster ?? []).map((s: RosterSlotRow) => ({
          ...s,
          is_eliminated: s.is_eliminated ?? false,
        })),
        totalPoints: memberTotalPoints,
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
  const { leagueId, leagueMemberId } = useParams<{
    leagueId: string;
    leagueMemberId?: string;
  }>();
  const navigate = useNavigate();
  const { user } = useAuthContext();
  const { data, isLoading, error } = useMemberRoster(leagueId!, leagueMemberId);
  const queryClient = useQueryClient();

  // Fetch league data (members list + settings)
  const mockLeagueResult = useMockLeague(leagueId);
  const realLeagueResult = useLeague(leagueId);
  const leagueData = IS_MOCK ? mockLeagueResult.data : realLeagueResult.data;
  const allowIrSlots = (leagueData?.allow_ir_slots ?? true) as boolean;

  interface LeagueMemberRow {
    id: string;
    user_id: string;
    team_name: string;
    users?: { display_name?: string } | null;
  }

  const leagueMembers = (leagueData?.league_members ?? []) as LeagueMemberRow[];

  // Determine the current user's member ID in this league
  const myMemberId = leagueMembers.find((m) => m.user_id === user?.id)?.id;

  const isOwnRoster = !leagueMemberId || leagueMemberId === myMemberId;

  // Resolve the viewed member's team name for the title
  const viewedMember = leagueMemberId
    ? leagueMembers.find((m) => m.id === leagueMemberId)
    : undefined;
  const rosterTitle = isOwnRoster
    ? 'My Roster'
    : `${viewedMember?.team_name ?? 'Roster'}`;

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
  const currentSeason = CURRENT_SEASON;
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

  // Fetch regular season stats for name resolution fallback in Round 1
  const isRound1 = currentRound === 1;
  const mockRegSeasonResult = useMockRegularSeasonPlayers(
    currentSeason,
    isRound1
  );
  const supabaseRegSeasonResult = useRegularSeasonPlayers(
    currentSeason,
    isRound1
  );
  const { data: regSeasonStats } = IS_MOCK
    ? mockRegSeasonResult
    : supabaseRegSeasonResult;

  // Merge regular season names so roster resolves picks even before playoff data exists
  const playerNameMap = useMemo(() => {
    const map = buildPlayerNameMap(regSeasonStats ?? []);
    for (const [id, name] of buildPlayerNameMap(playerStats ?? [])) {
      map.set(id, name);
    }
    return map;
  }, [playerStats, regSeasonStats]);
  const teamNameMap = useMemo(
    () => buildTeamNameMap(teamStats ?? []),
    [teamStats]
  );

  const playerTeamAbbreviationMap = useMemo(() => {
    const map = new Map<number, string>();
    for (const p of regSeasonStats ?? []) {
      if (p.team_abbreviation) map.set(p.player_id, p.team_abbreviation);
    }
    for (const p of playerStats ?? []) {
      if (p.team_abbreviation) map.set(p.player_id, p.team_abbreviation);
    }
    return map;
  }, [playerStats, regSeasonStats]);

  const teamAbbreviationMap = useMemo(() => {
    const map = new Map<number, string>();
    for (const t of teamStats ?? []) {
      if (t.team_abbreviation) map.set(t.team_id, t.team_abbreviation);
    }
    return map;
  }, [teamStats]);

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
          Could not load roster.
        </Alert>
      </Container>
    );
  }

  const { slots, round } = data;

  // Build member selector options
  const memberOptions = leagueMembers.map((m) => ({
    value: m.id,
    label:
      m.user_id === user?.id
        ? `${m.team_name} (You)`
        : `${m.team_name} — ${m.users?.display_name ?? 'Unknown'}`,
  }));

  const selectedMemberId = leagueMemberId ?? myMemberId ?? '';

  // Show empty state when no roster exists for this round (e.g. before re-draft)
  if (slots.length === 0) {
    return (
      <Container size="md" py="xl">
        <Stack gap="lg" align="center">
          <Title order={2}>{rosterTitle}</Title>
          <Text c="dimmed">Round {round}</Text>
          {memberOptions.length > 1 && (
            <Select
              data={memberOptions}
              value={selectedMemberId}
              onChange={(value) => {
                if (!value || value === myMemberId) {
                  navigate(`/roster/${leagueId}`);
                } else {
                  navigate(`/roster/${leagueId}/${value}`);
                }
              }}
              w={300}
              allowDeselect={false}
            />
          )}
          <Alert color="navy" title="No Roster Yet">
            {isOwnRoster
              ? `Your roster for Round ${round} has not been set yet. Waiting for the draft to begin.`
              : `This team's roster for Round ${round} has not been set yet.`}
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
        {memberOptions.length > 1 && (
          <Select
            label="View roster"
            data={memberOptions}
            value={selectedMemberId}
            onChange={(value) => {
              if (!value || value === myMemberId) {
                navigate(`/roster/${leagueId}`);
              } else {
                navigate(`/roster/${leagueId}/${value}`);
              }
            }}
            w={300}
            allowDeselect={false}
          />
        )}
        <Group justify="space-between">
          <div>
            <Title order={2}>{rosterTitle}</Title>
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
          const hasAnyActions =
            isOwnRoster &&
            groupHasActions(
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
                <Table.ScrollContainer minWidth={640}>
                  <Table>
                    <Table.Thead>
                      <Table.Tr>
                        <Table.Th>Player/Team</Table.Th>
                        <Table.Th>NHL Team</Table.Th>
                        <Table.Th>Status</Table.Th>
                        <Table.Th style={{ textAlign: 'right' }}>
                          Points
                        </Table.Th>
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
                              {slot.player_id != null
                                ? (playerTeamAbbreviationMap.get(slot.player_id) ?? '—')
                                : slot.team_id != null
                                  ? (teamAbbreviationMap.get(slot.team_id) ??
                                    '—')
                                  : '—'}
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
                </Table.ScrollContainer>
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
