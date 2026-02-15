import { useState } from 'react';
import { useParams } from 'react-router-dom';
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
  Group,
  Select,
  TextInput,
} from '@mantine/core';
import { useQuery } from '@tanstack/react-query';
import { supabase } from '@sportsnot/supabase';
import { useMockScoringHistory } from '../../../mock/hooks/useMockScoringHistory';

const IS_MOCK = import.meta.env.VITE_MOCK_MODE === 'true';

interface ScoringEvent {
  id: string;
  player_name: string;
  team_abbreviation: string;
  event_type: 'goal' | 'assist' | 'win' | 'shutout';
  points: number;
  game_date: string;
  league_member_team: string;
}

/* eslint-disable react-hooks/rules-of-hooks */
function useScoringHistory(leagueId: string) {
  if (IS_MOCK) return useMockScoringHistory(leagueId);

  return useQuery({
    queryKey: ['scoring-history', leagueId],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('scoring_events')
        .select('*')
        .eq('league_id', leagueId)
        .order('game_date', { ascending: false });

      if (error) throw error;
      return (data ?? []) as ScoringEvent[];
    },
  });
}
/* eslint-enable react-hooks/rules-of-hooks */

const EVENT_COLORS: Record<string, string> = {
  goal: 'red',
  assist: 'blue',
  win: 'green',
  shutout: 'yellow',
};

export function ScoringHistoryPage() {
  const { leagueId } = useParams<{ leagueId: string }>();
  const { data: events, isLoading, error } = useScoringHistory(leagueId!);
  const [playerFilter, setPlayerFilter] = useState('');
  const [teamFilter, setTeamFilter] = useState<string | null>(null);
  const [dateFilter, setDateFilter] = useState('');

  if (isLoading) {
    return (
      <Center h="50vh">
        <Loader size="lg" />
      </Center>
    );
  }

  if (error) {
    return (
      <Container size="md" py="xl">
        <Alert color="red" title="Error">
          Could not load scoring history.
        </Alert>
      </Container>
    );
  }

  const allEvents = events ?? [];

  // Extract unique teams for filter dropdown
  const teams = [...new Set(allEvents.map((e) => e.team_abbreviation))].sort();

  // Apply filters
  const filtered = allEvents.filter((e) => {
    if (playerFilter && !e.player_name.toLowerCase().includes(playerFilter.toLowerCase())) {
      return false;
    }
    if (teamFilter && e.team_abbreviation !== teamFilter) {
      return false;
    }
    if (dateFilter && !e.game_date.startsWith(dateFilter)) {
      return false;
    }
    return true;
  });

  return (
    <Container size="lg" py="xl">
      <Stack gap="xl">
        <div>
          <Title order={2}>Scoring History</Title>
          <Text c="dimmed">{allEvents.length} scoring events</Text>
        </div>

        <Group>
          <TextInput
            placeholder="Filter by player"
            value={playerFilter}
            onChange={(e) => setPlayerFilter(e.currentTarget.value)}
            aria-label="Filter by player"
          />
          <Select
            placeholder="Filter by team"
            data={teams}
            value={teamFilter}
            onChange={setTeamFilter}
            clearable
            aria-label="Filter by team"
          />
          <TextInput
            placeholder="Filter by date (YYYY-MM-DD)"
            value={dateFilter}
            onChange={(e) => setDateFilter(e.currentTarget.value)}
            aria-label="Filter by date"
          />
        </Group>

        <Card shadow="sm" padding="md" radius="md" withBorder>
          <Table striped highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Player</Table.Th>
                <Table.Th>Team</Table.Th>
                <Table.Th>Event</Table.Th>
                <Table.Th style={{ textAlign: 'right' }}>Points</Table.Th>
                <Table.Th>Date</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {filtered.length === 0 ? (
                <Table.Tr>
                  <Table.Td colSpan={5}>
                    <Text ta="center" c="dimmed" py="md">
                      No scoring events found
                    </Text>
                  </Table.Td>
                </Table.Tr>
              ) : (
                filtered.map((event, index) => (
                  <Table.Tr key={event.id ?? index}>
                    <Table.Td>{event.player_name}</Table.Td>
                    <Table.Td>
                      <Badge variant="light" color="gray">
                        {event.team_abbreviation}
                      </Badge>
                    </Table.Td>
                    <Table.Td>
                      <Badge color={EVENT_COLORS[event.event_type] ?? 'gray'}>
                        {event.event_type}
                      </Badge>
                    </Table.Td>
                    <Table.Td style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>
                      +{event.points}
                    </Table.Td>
                    <Table.Td>{event.game_date}</Table.Td>
                  </Table.Tr>
                ))
              )}
            </Table.Tbody>
          </Table>
        </Card>
      </Stack>
    </Container>
  );
}
