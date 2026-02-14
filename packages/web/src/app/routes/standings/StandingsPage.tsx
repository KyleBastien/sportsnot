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
  Group,
  Box,
  Button,
} from '@mantine/core';
import { useQuery } from '@tanstack/react-query';
import { supabase, useStatSync, useLiveScoring } from '@sportsnot/supabase';
import { useAuthContext } from '../../context/AuthContext';
import { ResponsiveTable, type ResponsiveTableColumn } from '@sportsnot/ui';
import { downloadCsv } from '@sportsnot/utils';
import { type ReactNode, useMemo, useCallback } from 'react';

function useStandings(leagueId: string) {
  return useQuery({
    queryKey: ['standings', leagueId],
    queryFn: async () => {
      const { data: league } = await supabase
        .from('leagues')
        .select('name, current_round')
        .eq('id', leagueId)
        .single();

      const { data: members, error } = await supabase
        .from('league_members')
        .select('id, user_id, team_name, total_points, users(display_name)')
        .eq('league_id', leagueId)
        .order('total_points', { ascending: false });

      if (error) throw error;

      return {
        league,
        members: members ?? [],
      };
    },
  });
}

function formatTimeAgo(date: Date): string {
  const seconds = Math.floor((Date.now() - date.getTime()) / 1000);
  if (seconds < 60) return 'just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ago`;
}

const pulseKeyframes = `
@keyframes scorePulse {
  0% { background-color: transparent; }
  50% { background-color: var(--mantine-color-green-1); }
  100% { background-color: transparent; }
}
@keyframes deltaFade {
  0% { opacity: 1; transform: translateY(0); }
  100% { opacity: 0; transform: translateY(-12px); }
}
`;

export function StandingsPage() {
  const { leagueId } = useParams<{ leagueId: string }>();
  const { user } = useAuthContext();
  const { data, isLoading, error } = useStandings(leagueId!);
  const { isLive, lastSyncedAt } = useStatSync(leagueId);
  const { lastUpdated, memberDeltas } = useLiveScoring(leagueId);

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

  const { league, members } = data;
  const displayTime = lastUpdated ?? lastSyncedAt ?? null;

  const handleExportCsv = () => {
    const headers = ['Rank', 'Team', 'Manager', 'Points'];
    const rows = members.map((member: any, index: number) => [
      index + 1,
      member.team_name ?? '',
      member.users?.display_name ?? 'Unknown',
      member.total_points ?? 0,
    ]);
    const date = new Date().toISOString().slice(0, 10);
    const safeName = (league?.name ?? 'league').replace(/[^a-zA-Z0-9]/g, '-');
    downloadCsv(headers, rows, `sportsnot-standings-${safeName}-${date}.csv`);
  };

  const standingsColumns: ResponsiveTableColumn[] = [
    { key: 'rank', label: 'Rank' },
    { key: 'team', label: 'Team' },
    { key: 'manager', label: 'Manager' },
    { key: 'points', label: 'Points', sortable: true },
  ];

  const standingsData = useMemo(
    () =>
      members.map((member: any, index: number) => ({
        _id: member.id,
        _userId: member.user_id,
        rank: index + 1,
        team: member.team_name ?? '',
        manager: member.users?.display_name ?? 'Unknown',
        points: member.total_points ?? 0,
      })),
    [members]
  );

  const renderCell = useCallback(
    (key: string, value: unknown, row: Record<string, unknown>): ReactNode => {
      const isMe = row._userId === user?.id;
      const memberId = row._id as string;

      if (key === 'rank') {
        const rank = value as number;
        if (rank === 1) return <Badge color="gold" variant="filled">1st</Badge>;
        if (rank === 2) return <Badge color="gray" variant="filled">2nd</Badge>;
        if (rank === 3) return <Badge color="orange" variant="filled">3rd</Badge>;
        return <>{rank}</>;
      }

      if (key === 'manager') {
        return (
          <Text size="sm" truncate="end" style={{ maxWidth: 160 }}>
            {String(value)}
            {isMe && (
              <Badge size="xs" ml="xs" variant="light">
                You
              </Badge>
            )}
          </Text>
        );
      }

      if (key === 'points') {
        return (
          <Box
            style={{
              textAlign: 'right',
              fontVariantNumeric: 'tabular-nums',
              position: 'relative',
              animation: memberDeltas[memberId]
                ? 'scorePulse 200ms ease-in-out'
                : undefined,
            }}
          >
            <Box component="span" fw={memberDeltas[memberId] ? 700 : undefined}>
              {value as number}
            </Box>
            {memberDeltas[memberId] && (
              <Text
                component="span"
                size="xs"
                c="green"
                fw={700}
                ml={4}
                style={{
                  animation: 'deltaFade 2s ease-out forwards',
                }}
              >
                {memberDeltas[memberId].delta > 0
                  ? `+${memberDeltas[memberId].delta}`
                  : memberDeltas[memberId].delta}
              </Text>
            )}
          </Box>
        );
      }

      return <>{value != null ? String(value) : '—'}</>;
    },
    [user?.id, memberDeltas]
  );

  const rowStyle = useCallback(
    (row: Record<string, unknown>) => {
      const isMe = row._userId === user?.id;
      return isMe
        ? {
            fontWeight: 700,
            backgroundColor: 'var(--mantine-color-blue-0)',
          }
        : undefined;
    },
    [user?.id]
  );

  return (
    <Container size="lg" py="xl">
      <style>{pulseKeyframes}</style>
      <Stack gap="xl">
        <Group justify="space-between" align="flex-start">
          <div>
            <Title order={2}>Standings</Title>
            <Text c="dimmed">
              {league?.name} · Round {league?.current_round ?? 0}
            </Text>
          </div>
          <Group gap="sm" align="flex-start">
            <Button variant="outline" size="sm" onClick={handleExportCsv}>
              Export CSV
            </Button>
            <Stack gap={4} align="flex-end">
            {isLive && (
              <Badge
                color="green"
                variant="dot"
                size="lg"
                styles={{
                  root: {
                    animation: 'scorePulse 2s ease-in-out infinite',
                  },
                }}
              >
                LIVE
              </Badge>
            )}
            {displayTime && (
              <Text size="xs" c="dimmed">
                Updated {formatTimeAgo(displayTime)}
              </Text>
            )}
          </Stack>
          </Group>
        </Group>

        <Card shadow="sm" padding="md" radius="md" withBorder>
          <ResponsiveTable
            columns={standingsColumns}
            data={standingsData}
            sortable
            renderCell={renderCell}
            rowStyle={rowStyle}
          />
        </Card>
      </Stack>
    </Container>
  );
}
