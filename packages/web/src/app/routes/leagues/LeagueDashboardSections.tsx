import { Link } from 'react-router-dom';
import {
  ActionIcon,
  Anchor,
  Badge,
  Button,
  Card,
  CopyButton,
  Group,
  Table,
  Text,
  Title,
  Tooltip,
} from '@mantine/core';
import type { WidgetSnapshot } from '@sportsnot/widget-api';
import { FeatureOnWidgetButton } from '../../components/FeatureOnWidgetButton';
import { LeagueGameCardsSection } from './LeagueGameCardsSection';
import { LeagueMemberRow } from './leagueDashboardTypes';

export function LeagueDashboardHeader({
  league,
  statusColor,
  membersCount,
  isCommissioner,
  currentUserTeamName,
  seasonComplete,
  roundComplete,
  roundStatusLoading,
  onOpenSettings,
  onStartDraft,
  onGoToDraft,
  onOpenRoster,
  onOpenStandings,
  onStartNextDraft,
}: {
  league: {
    id: string;
    name: string;
    status: string;
    current_round: number;
    max_participants: number;
    share_code?: string | null;
  };
  statusColor: string | undefined;
  membersCount: number;
  isCommissioner: boolean;
  currentUserTeamName: string | null;
  seasonComplete: boolean;
  roundComplete: boolean;
  roundStatusLoading: boolean;
  onOpenSettings: () => void;
  onStartDraft: () => void;
  onGoToDraft: () => void;
  onOpenRoster: () => void;
  onOpenStandings: () => void;
  onStartNextDraft: () => void;
}) {
  return (
    <Group justify="space-between" align="flex-start">
      <div>
        <Group gap="sm">
          <Title order={2}>{league.name}</Title>
          <Badge color={statusColor} size="lg">
            {league.status}
          </Badge>
        </Group>
        <Text c="dimmed">
          Round {league.current_round} · {membersCount} /{' '}
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
        <LeagueDashboardStatusActions
          league={league}
          isCommissioner={isCommissioner}
          seasonComplete={seasonComplete}
          roundComplete={roundComplete}
          roundStatusLoading={roundStatusLoading}
          onStartDraft={onStartDraft}
          onGoToDraft={onGoToDraft}
          onOpenRoster={onOpenRoster}
          onOpenStandings={onOpenStandings}
          onStartNextDraft={onStartNextDraft}
        />
      </Group>
    </Group>
  );
}

export function LeagueInviteCodeCard({ inviteCode }: { inviteCode: string }) {
  return (
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
            {inviteCode}
          </Text>
        </div>
        <CopyButton value={inviteCode}>
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
  );
}

export function LeagueStandingsCard({
  leagueId,
  sortedMembers,
  currentUserId,
  isMobile,
  seasonComplete,
}: {
  leagueId: string;
  sortedMembers: LeagueMemberRow[];
  currentUserId: string | undefined;
  isMobile: boolean;
  seasonComplete: boolean;
}) {
  return (
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
            <LeagueStandingsRow
              key={member.id}
              leagueId={leagueId}
              member={member}
              index={index}
              currentUserId={currentUserId}
              isMobile={isMobile}
              seasonComplete={seasonComplete}
            />
          ))}
        </Table.Tbody>
      </Table>
    </Card>
  );
}

export function LeagueActiveGamesSection({
  leagueStatus,
  widgetSnapshot,
  widgetSnapshotLoading,
  leagueGameCardsError,
}: {
  leagueStatus: string;
  widgetSnapshot: WidgetSnapshot | null | undefined;
  widgetSnapshotLoading: boolean;
  leagueGameCardsError: Error | null;
}) {
  if (leagueStatus !== 'active') {
    return null;
  }

  return (
    <LeagueGameCardsSection
      snapshot={widgetSnapshot}
      isLoading={widgetSnapshotLoading}
      error={leagueGameCardsError}
    />
  );
}

function LeagueDashboardStatusActions({
  league,
  isCommissioner,
  seasonComplete,
  roundComplete,
  roundStatusLoading,
  onStartDraft,
  onGoToDraft,
  onOpenRoster,
  onOpenStandings,
  onStartNextDraft,
}: {
  league: { status: string; current_round: number };
  isCommissioner: boolean;
  seasonComplete: boolean;
  roundComplete: boolean;
  roundStatusLoading: boolean;
  onStartDraft: () => void;
  onGoToDraft: () => void;
  onOpenRoster: () => void;
  onOpenStandings: () => void;
  onStartNextDraft: () => void;
}) {
  if (league.status === 'setup' && isCommissioner) {
    return <Button onClick={onStartDraft}>Start Draft</Button>;
  }

  if (league.status === 'drafting') {
    return (
      <Button color="orange" onClick={onGoToDraft}>
        Go to Draft
      </Button>
    );
  }

  if (league.status !== 'active') {
    return null;
  }

  return (
    <>
      <Button variant="outline" onClick={onOpenRoster}>
        My Roster
      </Button>
      <Button variant="outline" onClick={onOpenStandings}>
        Standings
      </Button>
      {isCommissioner && !seasonComplete && league.current_round < 3 && (
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
  );
}

function LeagueStandingsRow({
  leagueId,
  member,
  index,
  currentUserId,
  isMobile,
  seasonComplete,
}: {
  leagueId: string;
  member: LeagueMemberRow;
  index: number;
  currentUserId: string | undefined;
  isMobile: boolean;
  seasonComplete: boolean;
}) {
  const isCurrentUser = member.user_id === currentUserId;

  return (
    <Table.Tr style={{ fontWeight: isCurrentUser ? 700 : undefined }}>
      <Table.Td>{index + 1}</Table.Td>
      <Table.Td>
        <Anchor
          component={Link}
          to={`/roster/${leagueId}/${member.id}`}
          fw={isCurrentUser ? 700 : undefined}
        >
          {member.team_name}
          {seasonComplete && index === 0 && ' 🏆'}
        </Anchor>
      </Table.Td>
      {!isMobile && (
        <Table.Td>{member.users?.display_name ?? 'Unknown'}</Table.Td>
      )}
      <Table.Td style={{ textAlign: 'right' }}>
        {member.total_points ?? 0}
      </Table.Td>
    </Table.Tr>
  );
}
