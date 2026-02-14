import { useParams } from 'react-router-dom';
import {
  Container,
  Title,
  Text,
  Stack,
  Card,
  Badge,
  Loader,
  Center,
  Alert,
  SegmentedControl,
  Table,
  Group,
} from '@mantine/core';
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { supabase } from '@sportsnot/supabase';
import { useAuthContext } from '../../context/AuthContext';

export function RosterHistoryPage() {
  const { leagueId } = useParams<{ leagueId: string }>();
  const { user } = useAuthContext();
  const [selectedRound, setSelectedRound] = useState('1');

  const { data: league, isLoading: leagueLoading } = useQuery({
    queryKey: ['league-history', leagueId],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('leagues')
        .select('*, league_members(id, user_id, team_name)')
        .eq('id', leagueId!)
        .single();

      if (error) throw error;
      return data;
    },
    enabled: !!leagueId,
  });

  const myMember = (league?.league_members ?? []).find(
    (m: any) => m.user_id === user?.id
  );

  const { data: rosters, isLoading: rostersLoading } = useQuery({
    queryKey: ['roster-history', myMember?.id, selectedRound],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('rosters')
        .select('*')
        .eq('league_member_id', myMember!.id)
        .eq('round', parseInt(selectedRound, 10))
        .order('position');

      if (error) throw error;
      return data ?? [];
    },
    enabled: !!myMember,
  });

  const currentRound = league?.current_round ?? 1;
  const roundOptions = Array.from({ length: currentRound }, (_, i) => ({
    label: `Round ${i + 1}`,
    value: String(i + 1),
  }));

  const isLoading = leagueLoading || rostersLoading;

  if (isLoading) {
    return (
      <Center h="50vh">
        <Loader size="lg" />
      </Center>
    );
  }

  if (!league) {
    return (
      <Container size="md" py="xl">
        <Alert color="red">League not found</Alert>
      </Container>
    );
  }

  const positionOrder = ['F', 'D', 'G', 'IR_F', 'IR_D'];
  const sortedRosters = [...(rosters ?? [])].sort(
    (a, b) =>
      positionOrder.indexOf(a.position) - positionOrder.indexOf(b.position)
  );

  const totalPoints = sortedRosters
    .filter((r) => r.is_active)
    .reduce((sum, r) => sum + (r.points_earned ?? 0), 0);

  return (
    <Container size="md" py="xl">
      <Stack gap="xl">
        <Title order={2}>Roster History</Title>

        {currentRound > 1 && (
          <SegmentedControl
            value={selectedRound}
            onChange={setSelectedRound}
            data={roundOptions}
          />
        )}

        <Card shadow="sm" padding="lg" radius="md" withBorder>
          <Stack gap="md">
            <Group justify="space-between">
              <Title order={4}>
                Round {selectedRound} Roster — {myMember?.team_name}
              </Title>
              <Badge size="lg" variant="filled">
                {totalPoints} pts
              </Badge>
            </Group>

            {sortedRosters.length === 0 ? (
              <Text c="dimmed">No roster data for this round</Text>
            ) : (
              <Table>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>Position</Table.Th>
                    <Table.Th>Player/Team ID</Table.Th>
                    <Table.Th>Status</Table.Th>
                    <Table.Th>Points</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {sortedRosters.map((slot) => (
                    <Table.Tr
                      key={slot.id}
                      style={{
                        opacity: slot.is_active ? 1 : 0.5,
                      }}
                    >
                      <Table.Td>
                        <Badge
                          variant="light"
                          color={
                            slot.position.startsWith('IR')
                              ? 'red'
                              : slot.position === 'G'
                                ? 'grape'
                                : slot.position === 'D'
                                  ? 'blue'
                                  : 'green'
                          }
                        >
                          {slot.position}
                        </Badge>
                      </Table.Td>
                      <Table.Td>
                        {slot.player_id
                          ? `Player #${slot.player_id}`
                          : slot.team_id
                            ? `Team #${slot.team_id}`
                            : 'Empty'}
                      </Table.Td>
                      <Table.Td>
                        {slot.activated_from_ir ? (
                          <Badge color="orange" size="sm">
                            IR Activated
                          </Badge>
                        ) : slot.is_active ? (
                          <Badge color="green" size="sm">
                            Active
                          </Badge>
                        ) : (
                          <Badge color="red" size="sm">
                            Inactive
                          </Badge>
                        )}
                      </Table.Td>
                      <Table.Td fw={700}>{slot.points_earned ?? 0}</Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            )}
          </Stack>
        </Card>
      </Stack>
    </Container>
  );
}
