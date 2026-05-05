import { Link } from 'react-router-dom';
import {
  ActionIcon,
  Anchor,
  Badge,
  Button,
  Card,
  Container,
  CopyButton,
  Group,
  Stack,
  Table,
  Text,
  Title,
  Tooltip,
} from '@mantine/core';
import { FeatureOnWidgetButton } from '../../components/FeatureOnWidgetButton';
import { LeagueGameCardsSection } from './LeagueGameCardsSection';
import { LeagueMemberRow } from './leagueDashboardTypes';

interface LeagueDashboardPageViewProps {
  league: {
    id: string;
    name: string;
    status: string;
    current_round: number;
    max_participants: number;
    invite_code: string;
    share_code?: string | null;
  };
  statusColor: string | undefined;
  members: LeagueMemberRow[];
  sortedMembers: LeagueMemberRow[];
  currentUserId: string | undefined;
  currentUserTeamName: string | null;
  isCommissioner: boolean;
  isMobile: boolean;
  seasonComplete: boolean;
  roundComplete: boolean;
  roundStatusLoading: boolean;
  widgetSnapshot: unknown;
  widgetSnapshotLoading: boolean;
  leagueGameCardsError: Error | null;
  onOpenSettings: () => void;
  onStartDraft: () => void;
  onGoToDraft: () => void;
  onOpenRoster: () => void;
  onOpenStandings: () => void;
  onStartNextDraft: () => void;
}

export function LeagueDashboardPageView({
  league,
  statusColor,
  members,
  sortedMembers,
  currentUserId,
  currentUserTeamName,
  isCommissioner,
  isMobile,
  seasonComplete,
  roundComplete,
  roundStatusLoading,
  widgetSnapshot,
  widgetSnapshotLoading,
  leagueGameCardsError,
  onOpenSettings,
  onStartDraft,
  onGoToDraft,
  onOpenRoster,
  onOpenStandings,
  onStartNextDraft,
}: LeagueDashboardPageViewProps) {
  return (
    <Container size="lg" py="xl">
      <Stack gap="xl">
        <Group justify="space-between" align="flex-start">
          <div>
            <Group gap="sm">
              <Title order={2}>{league.name}</Title>
              <Badge color={statusColor} size="lg">
                {league.status}
              </Badge>
            </Group>
            <Text c="dimmed">
              Round {league.current_round} · {members.length} /{' '}
              {league.max_participants} members
            </Text>
          </div>
          <Group>
            {isCommissioner && (
              <Button variant="subtle" onClick={onOpenSettings}>
                Settings
              </Button>
            )}
            <FeatureOnWidgetButton
              leagueId={league.id}
              leagueName={league.name}
              shareCode={league.share_code ?? null}
              myTeamName={currentUserTeamName}
            />
            {league.status === 'setup' && isCommissioner && (
              <Button onClick={onStartDraft} disabled={members.length < 2}>
                Start Draft
              </Button>
            )}
            {league.status === 'drafting' && (
              <Button color="orange" onClick={onGoToDraft}>
                Go to Draft
              </Button>
            )}
            {league.status === 'active' && (
              <>
                <Button variant="outline" onClick={onOpenRoster}>
                  My Roster
                </Button>
                <Button variant="outline" onClick={onOpenStandings}>
                  Standings
                </Button>
                {isCommissioner &&
                  !seasonComplete &&
                  league.current_round < 3 && (
                    <Tooltip
                      label="All series in the current round must be complete"
                      disabled={roundComplete}
                    >
                      <Button
                        color="green"
                        onClick={onStartNextDraft}
                        disabled={!roundComplete || roundStatusLoading}
                        loading={roundStatusLoading}
                      >
                        Start Next Draft
                      </Button>
                    </Tooltip>
                  )}
              </>
            )}
          </Group>
        </Group>

        <Card shadow="sm" padding="md" radius="md" withBorder>
          <Group justify="space-between">
            <div>
              <Text size="sm" c="dimmed">
                Invite Code
              </Text>
              <Text
                size="xl"
                fw={700}
                style={{ letterSpacing: 3, fontFamily: 'monospace' }}
              >
                {league.invite_code}
              </Text>
            </div>
            <CopyButton value={league.invite_code}>
              {({ copied, copy }) => (
                <Tooltip label={copied ? 'Copied!' : 'Copy invite code'}>
                  <ActionIcon
                    color={copied ? 'teal' : 'gray'}
                    variant="subtle"
                    onClick={copy}
                    size="lg"
                  >
                    {copied ? '✓' : '📋'}
                  </ActionIcon>
                </Tooltip>
              )}
            </CopyButton>
          </Group>
        </Card>

        <Card shadow="sm" padding="md" radius="md" withBorder>
          <Title order={4} mb="md">
            Standings
          </Title>
          <Table striped highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Rank</Table.Th>
                <Table.Th>Team</Table.Th>
                {!isMobile && <Table.Th>Manager</Table.Th>}
                <Table.Th style={{ textAlign: 'right' }}>Points</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {sortedMembers.map((member, index) => (
                <Table.Tr
                  key={member.id}
                  style={{
                    fontWeight:
                      member.user_id === currentUserId ? 700 : undefined,
                  }}
                >
                  <Table.Td>{index + 1}</Table.Td>
                  <Table.Td>
                    <Anchor
                      component={Link}
                      to={`/roster/${league.id}/${member.id}`}
                      fw={member.user_id === currentUserId ? 700 : undefined}
                    >
                      {member.team_name}
                      {seasonComplete && index === 0 && ' 🏆'}
                    </Anchor>
                  </Table.Td>
                  {!isMobile && (
                    <Table.Td>
                      {member.users?.display_name ?? 'Unknown'}
                    </Table.Td>
                  )}
                  <Table.Td style={{ textAlign: 'right' }}>
                    {member.total_points ?? 0}
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Card>

        {league.status === 'active' && (
          <LeagueGameCardsSection
            snapshot={widgetSnapshot}
            isLoading={widgetSnapshotLoading}
            error={leagueGameCardsError}
          />
        )}
      </Stack>
    </Container>
  );
}
