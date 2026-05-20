import { useMemo, useState, type CSSProperties } from 'react';
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
import {
  supabase,
  useLeague as useSupabaseLeague,
  usePlayoffTeams as useSupabasePlayoffTeams,
} from '@sportsnot/supabase';
import { CURRENT_SEASON } from '@sportsnot/types';
import { useIsMobile, MobileCardList, DataRow } from '@sportsnot/ui';
import { useMockScoringHistory } from '../../../mock/hooks/useMockScoringHistory';
import { useMockLeague } from '../../../mock/hooks/useMockLeagues';
import { useMockPlayoffTeams } from '../../../mock/hooks/useMockNhlApi';

const IS_MOCK = import.meta.env.VITE_MOCK_MODE === 'true';
const DIMMED_TEXT_COLOR = 'var(--mantine-color-dimmed)';

interface ScoringEvent {
  id: string;
  player_name: string;
  team_abbreviation: string;
  event_type: 'goal' | 'assist' | 'win' | 'shutout';
  points: number;
  game_date: string;
  league_member_team: string;
}

interface LeagueRoundRow {
  current_round?: number;
}

interface PlayoffTeamRow {
  team_abbreviation?: string | null;
  is_eliminated?: boolean | null;
}

interface ScoringFiltersState {
  player: string;
  team: string | null;
  date: string;
}

interface ScoringFiltersProps {
  filters: ScoringFiltersState;
  teams: string[];
  onPlayerChange: (value: string) => void;
  onTeamChange: (value: string | null) => void;
  onDateChange: (value: string) => void;
}

interface ScoringEventsViewProps {
  events: ScoringEvent[];
  eliminatedTeamAbbrs: Set<string>;
}

function useScoringHistory(leagueId: string) {
  const mockResult = useMockScoringHistory(leagueId);

  const queryResult = useQuery({
    queryKey: ['scoring-history', leagueId],
    queryFn: async () => {
      if (!leagueId) {
        return [];
      }

      const { data, error } = await supabase
        .from('scoring_events')
        .select('*')
        .eq('league_id', leagueId)
        .order('game_date', { ascending: false });

      if (error) throw error;
      return (data ?? []) as ScoringEvent[];
    },
    enabled: !IS_MOCK && !!leagueId,
  });

  return IS_MOCK ? mockResult : queryResult;
}

function useLeagueRound(leagueId: string): number {
  const mockLeague = useMockLeague(leagueId);
  const supabaseLeague = useSupabaseLeague(leagueId);
  const leagueData = (IS_MOCK ? mockLeague.data : supabaseLeague.data) as
    | LeagueRoundRow
    | null
    | undefined;

  return leagueData?.current_round ?? 1;
}

function usePlayoffTeamsForScoring(round: number): PlayoffTeamRow[] {
  const mockTeams = useMockPlayoffTeams(CURRENT_SEASON, round);
  const supabaseTeams = useSupabasePlayoffTeams(CURRENT_SEASON, round);
  return (IS_MOCK ? mockTeams.data : supabaseTeams.data) ?? [];
}

function useEliminatedTeamAbbrs(leagueId: string): Set<string> {
  const currentRound = useLeagueRound(leagueId);
  const round1Teams = usePlayoffTeamsForScoring(1);
  const currentRoundTeams = usePlayoffTeamsForScoring(currentRound);
  const nextRoundTeams = usePlayoffTeamsForScoring(currentRound + 1);

  return useMemo(
    () =>
      buildEliminatedTeamAbbrs({
        currentRound,
        round1Teams,
        currentRoundTeams,
        nextRoundTeams,
      }),
    [currentRound, currentRoundTeams, nextRoundTeams, round1Teams]
  );
}

function buildEliminatedTeamAbbrs(params: {
  currentRound: number;
  round1Teams: ReadonlyArray<PlayoffTeamRow>;
  currentRoundTeams: ReadonlyArray<PlayoffTeamRow>;
  nextRoundTeams: ReadonlyArray<PlayoffTeamRow>;
}): Set<string> {
  const aliveTeams = selectAliveTeams(params);
  const aliveAbbrs = collectAliveTeamAbbrs(aliveTeams);

  return collectEliminatedTeamAbbrs(params.round1Teams, aliveAbbrs);
}

function selectAliveTeams(params: {
  currentRound: number;
  currentRoundTeams: ReadonlyArray<PlayoffTeamRow>;
  nextRoundTeams: ReadonlyArray<PlayoffTeamRow>;
}): ReadonlyArray<PlayoffTeamRow> {
  if (params.currentRound < 4 && params.nextRoundTeams.length > 0) {
    return params.nextRoundTeams;
  }

  return params.currentRoundTeams;
}

function collectAliveTeamAbbrs(
  teams: ReadonlyArray<PlayoffTeamRow>
): Set<string> {
  const aliveAbbrs = new Set<string>();

  for (const team of teams) {
    if (team.team_abbreviation && !team.is_eliminated) {
      aliveAbbrs.add(team.team_abbreviation);
    }
  }

  return aliveAbbrs;
}

function collectEliminatedTeamAbbrs(
  teams: ReadonlyArray<PlayoffTeamRow>,
  aliveAbbrs: Set<string>
): Set<string> {
  const eliminatedAbbrs = new Set<string>();

  for (const team of teams) {
    if (team.team_abbreviation && !aliveAbbrs.has(team.team_abbreviation)) {
      eliminatedAbbrs.add(team.team_abbreviation);
    }
  }

  return eliminatedAbbrs;
}

function buildTeamOptions(events: ReadonlyArray<ScoringEvent>): string[] {
  return [...new Set(events.map((event) => event.team_abbreviation))].sort();
}

function filterEvents(
  events: ReadonlyArray<ScoringEvent>,
  filters: ScoringFiltersState
): ScoringEvent[] {
  return events.filter(
    (event) =>
      matchesPlayerFilter(event, filters.player) &&
      matchesTeamFilter(event, filters.team) &&
      matchesDateFilter(event, filters.date)
  );
}

function matchesPlayerFilter(
  event: ScoringEvent,
  playerFilter: string
): boolean {
  if (!playerFilter) {
    return true;
  }

  return event.player_name.toLowerCase().includes(playerFilter.toLowerCase());
}

function matchesTeamFilter(
  event: ScoringEvent,
  teamFilter: string | null
): boolean {
  return !teamFilter || event.team_abbreviation === teamFilter;
}

function matchesDateFilter(event: ScoringEvent, dateFilter: string): boolean {
  return !dateFilter || event.game_date.startsWith(dateFilter);
}

function isEliminatedEvent(
  event: ScoringEvent,
  eliminatedTeamAbbrs: Set<string>
): boolean {
  return eliminatedTeamAbbrs.has(event.team_abbreviation);
}

function getPlayerNameCellStyle(
  isEliminated: boolean
): CSSProperties | undefined {
  if (!isEliminated) {
    return undefined;
  }

  return {
    textDecoration: 'line-through',
    color: DIMMED_TEXT_COLOR,
  };
}

function ScoringFilters(props: ScoringFiltersProps) {
  const { filters, teams, onPlayerChange, onTeamChange, onDateChange } = props;

  return (
    <Group>
      <TextInput
        placeholder="Filter by player"
        value={filters.player}
        onChange={(event) => onPlayerChange(event.currentTarget.value)}
        aria-label="Filter by player"
      />
      <Select
        placeholder="Filter by team"
        data={teams}
        value={filters.team}
        onChange={onTeamChange}
        clearable
        aria-label="Filter by team"
      />
      <TextInput
        placeholder="Filter by date (YYYY-MM-DD)"
        value={filters.date}
        onChange={(event) => onDateChange(event.currentTarget.value)}
        aria-label="Filter by date"
      />
    </Group>
  );
}

function EventPlayerName(props: {
  event: ScoringEvent;
  eliminatedTeamAbbrs: Set<string>;
}) {
  const isEliminated = isEliminatedEvent(
    props.event,
    props.eliminatedTeamAbbrs
  );

  return (
    <Text
      fw={500}
      size="sm"
      td={isEliminated ? 'line-through' : undefined}
      c={isEliminated ? 'dimmed' : undefined}
    >
      {props.event.player_name}
    </Text>
  );
}

function MobileScoringEvents(props: ScoringEventsViewProps) {
  return (
    <MobileCardList emptyMessage="No scoring events found">
      {props.events.map((event, index) => (
        <Card key={event.id ?? index} padding="sm" radius="sm" withBorder>
          <Group justify="space-between" mb={4}>
            <EventPlayerName
              event={event}
              eliminatedTeamAbbrs={props.eliminatedTeamAbbrs}
            />
            <Badge color={EVENT_COLORS[event.event_type] ?? 'gray'} size="sm">
              {event.event_type}
            </Badge>
          </Group>
          <DataRow
            label="Team"
            value={
              <Badge variant="light" color="gray" size="sm">
                {event.team_abbreviation}
              </Badge>
            }
          />
          <DataRow
            label="Points"
            value={
              <Text
                size="sm"
                fw={500}
                style={{ fontVariantNumeric: 'tabular-nums' }}
              >
                +{event.points}
              </Text>
            }
          />
          <DataRow label="Date" value={event.game_date} />
        </Card>
      ))}
    </MobileCardList>
  );
}

function DesktopScoringEvents(props: ScoringEventsViewProps) {
  return (
    <Table.ScrollContainer minWidth={600}>
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
          {props.events.length === 0 ? (
            <Table.Tr>
              <Table.Td colSpan={5}>
                <Text ta="center" c="dimmed" py="md">
                  No scoring events found
                </Text>
              </Table.Td>
            </Table.Tr>
          ) : (
            props.events.map((event, index) => (
              <Table.Tr key={event.id ?? index}>
                <Table.Td
                  style={getPlayerNameCellStyle(
                    isEliminatedEvent(event, props.eliminatedTeamAbbrs)
                  )}
                >
                  {event.player_name}
                </Table.Td>
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
                <Table.Td
                  style={{
                    textAlign: 'right',
                    fontVariantNumeric: 'tabular-nums',
                  }}
                >
                  +{event.points}
                </Table.Td>
                <Table.Td>{event.game_date}</Table.Td>
              </Table.Tr>
            ))
          )}
        </Table.Tbody>
      </Table>
    </Table.ScrollContainer>
  );
}

const EVENT_COLORS: Record<string, string> = {
  goal: 'red',
  assist: 'blue',
  win: 'green',
  shutout: 'yellow',
};

export function ScoringHistoryPage() {
  const { leagueId } = useParams<{ leagueId: string }>();
  const resolvedLeagueId = leagueId ?? '';
  const {
    data: events,
    isLoading,
    error,
  } = useScoringHistory(resolvedLeagueId);
  const eliminatedTeamAbbrs = useEliminatedTeamAbbrs(resolvedLeagueId);
  const [playerFilter, setPlayerFilter] = useState('');
  const [teamFilter, setTeamFilter] = useState<string | null>(null);
  const [dateFilter, setDateFilter] = useState('');
  const isMobile = useIsMobile();
  const allEvents = useMemo(() => events ?? [], [events]);
  const filters = useMemo(
    () => ({ player: playerFilter, team: teamFilter, date: dateFilter }),
    [playerFilter, teamFilter, dateFilter]
  );
  const teams = useMemo(() => buildTeamOptions(allEvents), [allEvents]);
  const filteredEvents = useMemo(
    () => filterEvents(allEvents, filters),
    [allEvents, filters]
  );

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

  return (
    <Container size="lg" py="xl">
      <Stack gap="xl">
        <div>
          <Title order={2}>Scoring History</Title>
          <Text c="dimmed">{allEvents.length} scoring events</Text>
        </div>

        <ScoringFilters
          filters={filters}
          teams={teams}
          onPlayerChange={setPlayerFilter}
          onTeamChange={setTeamFilter}
          onDateChange={setDateFilter}
        />

        <Card shadow="sm" padding="md" radius="md" withBorder>
          {isMobile ? (
            <MobileScoringEvents
              events={filteredEvents}
              eliminatedTeamAbbrs={eliminatedTeamAbbrs}
            />
          ) : (
            <DesktopScoringEvents
              events={filteredEvents}
              eliminatedTeamAbbrs={eliminatedTeamAbbrs}
            />
          )}
        </Card>
      </Stack>
    </Container>
  );
}
