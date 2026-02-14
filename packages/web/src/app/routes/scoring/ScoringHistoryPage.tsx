import { useState, useMemo } from 'react';
import { useParams } from 'react-router-dom';
import {
  Container,
  Title,
  Text,
  Alert,
  Stack,
  Group,
  Select,
  Switch,
  Pagination,
  Loader,
  Center,
  TextInput,
  Badge,
} from '@mantine/core';
import { ResponsiveTable } from '@sportsnot/ui';
import {
  useScoringEvents,
  useLeague,
  type ScoringEventsFilters,
} from '@sportsnot/supabase';
import { useAuthContext } from '../../context/AuthContext';

const EVENT_TYPE_ICONS: Record<string, string> = {
  goal: '🏒',
  assist: '🅰️',
  win: '🏆',
  shutout: '🧤',
};

const EVENT_TYPE_LABELS: Record<string, string> = {
  goal: 'Goal',
  assist: 'Assist',
  win: 'Win',
  shutout: 'Shutout',
};

const COLUMNS = [
  { key: 'eventIcon', label: 'Type' },
  { key: 'description', label: 'Event' },
  { key: 'points', label: 'Points', sortable: true },
  { key: 'memberName', label: 'Team' },
  { key: 'gameDate', label: 'Date', sortable: true },
  { key: 'time', label: 'Time' },
];

const PAGE_SIZE = 20;

function formatDate(dateStr: string): string {
  const d = new Date(dateStr);
  return d.toLocaleDateString('en-US', {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

function formatTime(dateStr: string): string {
  const d = new Date(dateStr);
  return d.toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
  });
}

export function ScoringHistoryPage() {
  const { leagueId } = useParams<{ leagueId: string }>();
  const { user } = useAuthContext();

  const [page, setPage] = useState(0);
  const [eventTypeFilter, setEventTypeFilter] = useState<string | null>(null);
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [showMyEvents, setShowMyEvents] = useState(false);

  const { data: league } = useLeague(leagueId);

  const currentMemberId = useMemo(() => {
    if (!league || !user) return undefined;
    const member = league.league_members?.find(
      (m: { user_id: string }) => m.user_id === user.id
    );
    return member?.id as string | undefined;
  }, [league, user]);

  const filters: ScoringEventsFilters = useMemo(() => {
    const f: ScoringEventsFilters = {};
    if (eventTypeFilter) {
      f.eventType = eventTypeFilter as ScoringEventsFilters['eventType'];
    }
    if (dateFrom) f.dateFrom = dateFrom;
    if (dateTo) f.dateTo = dateTo;
    if (showMyEvents && currentMemberId) f.memberId = currentMemberId;
    return f;
  }, [eventTypeFilter, dateFrom, dateTo, showMyEvents, currentMemberId]);

  const { data: result, isLoading, isError } = useScoringEvents(leagueId, filters, page);

  const memberMap = useMemo(() => {
    const map: Record<string, string> = {};
    if (league?.league_members) {
      for (const m of league.league_members) {
        map[m.id] = m.team_name || m.users?.display_name || 'Unknown';
      }
    }
    return map;
  }, [league]);

  // Group events by game date
  const groupedRows = useMemo(() => {
    if (!result?.data) return [];

    const groups: { date: string; rows: Record<string, unknown>[] }[] = [];
    let currentDate = '';

    for (const event of result.data) {
      const eventDate = event.game_date
        ? formatDate(event.game_date)
        : 'Unknown Date';
      if (eventDate !== currentDate) {
        currentDate = eventDate;
        groups.push({ date: eventDate, rows: [] });
      }
      groups[groups.length - 1].rows.push({
        eventIcon: `${EVENT_TYPE_ICONS[event.event_type] || '📋'} ${EVENT_TYPE_LABELS[event.event_type] || event.event_type}`,
        description: event.description || '—',
        points: event.points,
        memberName: memberMap[event.member_id] || '—',
        gameDate: event.game_date || '—',
        time: event.created_at ? formatTime(event.created_at) : '—',
        _eventType: event.event_type,
      });
    }
    return groups;
  }, [result, memberMap]);

  const totalPages = Math.ceil((result?.count ?? 0) / PAGE_SIZE);

  if (!leagueId) {
    return (
      <Container size="md" py="xl">
        <Alert color="red" title="Error">
          No league selected.
        </Alert>
      </Container>
    );
  }

  return (
    <Container size="lg" py="xl">
      <Stack gap="lg">
        <Title order={2}>Scoring History</Title>
        <Text c="dimmed">View how points were earned over time.</Text>

        {/* Filters */}
        <Group gap="sm" wrap="wrap">
          <Select
            placeholder="All event types"
            clearable
            value={eventTypeFilter}
            onChange={(val) => {
              setEventTypeFilter(val);
              setPage(0);
            }}
            data={[
              { value: 'goal', label: '🏒 Goal' },
              { value: 'assist', label: '🅰️ Assist' },
              { value: 'win', label: '🏆 Win' },
              { value: 'shutout', label: '🧤 Shutout' },
            ]}
            w={180}
          />
          <TextInput
            type="date"
            placeholder="From date"
            value={dateFrom}
            onChange={(e) => {
              setDateFrom(e.currentTarget.value);
              setPage(0);
            }}
            w={160}
            label="From"
          />
          <TextInput
            type="date"
            placeholder="To date"
            value={dateTo}
            onChange={(e) => {
              setDateTo(e.currentTarget.value);
              setPage(0);
            }}
            w={160}
            label="To"
          />
          <Switch
            label="Show only my events"
            checked={showMyEvents}
            onChange={(e) => {
              setShowMyEvents(e.currentTarget.checked);
              setPage(0);
            }}
            disabled={!currentMemberId}
            mt="lg"
          />
        </Group>

        {/* Content */}
        {isLoading && (
          <Center py="xl">
            <Loader />
          </Center>
        )}

        {isError && (
          <Alert color="red" title="Error">
            Failed to load scoring events.
          </Alert>
        )}

        {!isLoading && !isError && result && result.data.length === 0 && (
          <Center py="xl">
            <Text c="dimmed">No scoring events found.</Text>
          </Center>
        )}

        {!isLoading && !isError && groupedRows.length > 0 && (
          <Stack gap="md">
            {groupedRows.map((group) => (
              <Stack key={group.date} gap="xs">
                <Badge variant="light" color="gray" size="lg" radius="sm">
                  {group.date}
                </Badge>
                <ResponsiveTable
                  columns={COLUMNS}
                  data={group.rows}
                  renderCell={(key, value, row) => {
                    if (key === 'points') {
                      return (
                        <Badge
                          color={
                            (row['_eventType'] as string) === 'shutout'
                              ? 'grape'
                              : (row['_eventType'] as string) === 'win'
                                ? 'teal'
                                : 'blue'
                          }
                          variant="light"
                        >
                          +{String(value)}
                        </Badge>
                      );
                    }
                    return value != null ? String(value) : '—';
                  }}
                />
              </Stack>
            ))}
          </Stack>
        )}

        {/* Pagination */}
        {totalPages > 1 && (
          <Center>
            <Pagination
              total={totalPages}
              value={page + 1}
              onChange={(p) => setPage(p - 1)}
            />
          </Center>
        )}
      </Stack>
    </Container>
  );
}
