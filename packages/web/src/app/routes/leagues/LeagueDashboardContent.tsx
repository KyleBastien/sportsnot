import { Link } from 'react-router-dom';
import {
  Anchor,
  ActionIcon,
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
import type { WidgetSnapshot } from '@sportsnot/widget-api';
import { FeatureOnWidgetButton } from '../../components/FeatureOnWidgetButton';
import { LeagueGameCardsSection } from './LeagueGameCardsSection';

const STATUS_COLORS: Record<string, string> = {
  setup: 'blue',
  drafting: 'orange',
  active: 'green',
  completed: 'gray',
};

export interface LeagueMemberRow {
  id: string;
  user_id: string;
  team_name: string;
  total_points: number;
  round_points?: Record<string, number> | null;
  users?: { display_name?: string; avatar_url?: string } | null;
}

interface LeagueDashboardContentProps {
  currentRound: number;
  isCommissioner: boolean;
  isMobile: boolean;
  league: {
    id: string;
    invite_code: string;
    max_participants: number;
    name: string;
    share_code?: string | null;
    status: string;
  };
  leagueGameCardsError: Error | null;
  leagueId: string | undefined;
  members: LeagueMemberRow[];
  roundComplete: boolean;
  roundStatusLoading: boolean;
  seasonComplete: boolean;
  userId: string | undefined;
  widgetSnapshot: WidgetSnapshot | null | undefined;
  widgetSnapshotLoading: boolean;
  onOpenDraft: () => void;
  onOpenLobby: () => void;
  onOpenRoster: () => void;
  onOpenSettings: () => void;
  onOpenStandings: () => void;
  onStartNextDraft: () => void;
  onOpenTransition: () => void;
}

interface LeagueHeaderSectionProps {
  currentRound: number;
  isCommissioner: boolean;
  league: LeagueDashboardContentProps['league'];
  members: LeagueMemberRow[];
  roundComplete: boolean;
  roundStatusLoading: boolean;
  seasonComplete: boolean;
  userId: string | undefined;
  onOpenDraft: () => void;
  onOpenLobby: () => void;
  onOpenRoster: () => void;
  onOpenSettings: () => void;
  onOpenStandings: () => void;
  onStartNextDraft: () => void;
  onOpenTransition: () => void;
}

interface LeagueStatusActionProps {
  isCommissioner: boolean;
  leagueStatus: string;
  membersCount: number;
  onOpenDraft: () => void;
  onOpenLobby: () => void;
}

interface LeagueActiveActionsProps {
  currentRound: number;
  isCommissioner: boolean;
  leagueStatus: string;
  roundComplete: boolean;
  roundStatusLoading: boolean;
  seasonComplete: boolean;
  onOpenRoster: () => void;
  onOpenStandings: () => void;
  onStartNextDraft: () => void;
  onOpenTransition: () => void;
}

interface LeagueInviteCodeCardProps {
  inviteCode: string;
}

interface LeagueStandingsCardProps {
  currentRound: number;
  isMobile: boolean;
  leagueId: string | undefined;
  members: LeagueMemberRow[];
  seasonComplete: boolean;
  userId: string | undefined;
}

const MAX_PLAYOFF_ROUND = 4;

export function getVisibleStandingsRounds(
  currentRound: number,
  isMobile: boolean
): number[] {
  const cappedRound = Math.min(Math.max(currentRound, 0), MAX_PLAYOFF_ROUND);

  if (cappedRound <= 1) {
    return [];
  }

  if (isMobile) {
    return [cappedRound];
  }

  return Array.from({ length: cappedRound }, (_, index) => index + 1);
}

function getRoundPoints(
  roundPoints: Record<string, number> | null | undefined,
  round: number
): number {
  return roundPoints?.[round] ?? 0;
}

function getMyTeamName(
  members: LeagueMemberRow[],
  userId: string | undefined
): string | null {
  return members.find((member) => member.user_id === userId)?.team_name ?? null;
}

function LeagueStatusAction({
  isCommissioner,
  leagueStatus,
  membersCount,
  onOpenDraft,
  onOpenLobby,
}: LeagueStatusActionProps) {
  if (leagueStatus === 'setup' && isCommissioner) {
    return (
      <Button onClick={onOpenLobby} disabled={membersCount < 2}>
        Start Draft
      </Button>
    );
  }

  if (leagueStatus === 'drafting') {
    return (
      <Button color="orange" onClick={onOpenDraft}>
        Go to Draft
      </Button>
    );
  }

  return null;
}

const ROUND_COMPLETE_TOOLTIP =
  'All series in the current round must be complete';

interface RoundCompleteGateButtonProps {
  label: string;
  onClick: () => void;
  roundComplete: boolean;
  roundStatusLoading: boolean;
}

function RoundCompleteGateButton({
  label,
  onClick,
  roundComplete,
  roundStatusLoading,
}: RoundCompleteGateButtonProps) {
  return (
    <Tooltip label={ROUND_COMPLETE_TOOLTIP} disabled={roundComplete}>
      <Button
        color="green"
        onClick={onClick}
        disabled={!roundComplete || roundStatusLoading}
        loading={roundStatusLoading}
      >
        {label}
      </Button>
    </Tooltip>
  );
}

function LeagueActiveActions({
  currentRound,
  isCommissioner,
  leagueStatus,
  roundComplete,
  roundStatusLoading,
  seasonComplete,
  onOpenRoster,
  onOpenStandings,
  onStartNextDraft,
  onOpenTransition,
}: LeagueActiveActionsProps) {
  if (leagueStatus !== 'active') {
    return null;
  }

  const showStartNextDraft =
    isCommissioner && !seasonComplete && currentRound < 3;

  const showAdvanceToFinals =
    isCommissioner && !seasonComplete && currentRound === 3 && roundComplete;

  return (
    <>
      <Button variant="outline" onClick={onOpenRoster}>
        My Roster
      </Button>
      <Button variant="outline" onClick={onOpenStandings}>
        Standings
      </Button>
      {showStartNextDraft && (
        <RoundCompleteGateButton
          label="Start Next Draft"
          onClick={onStartNextDraft}
          roundComplete={roundComplete}
          roundStatusLoading={roundStatusLoading}
        />
      )}
      {showAdvanceToFinals && (
        <RoundCompleteGateButton
          label="Advance to Finals"
          onClick={onOpenTransition}
          roundComplete={roundComplete}
          roundStatusLoading={roundStatusLoading}
        />
      )}
    </>
  );
}

function LeagueHeaderSection({
  currentRound,
  isCommissioner,
  league,
  members,
  roundComplete,
  roundStatusLoading,
  seasonComplete,
  userId,
  onOpenDraft,
  onOpenLobby,
  onOpenRoster,
  onOpenSettings,
  onOpenStandings,
  onStartNextDraft,
  onOpenTransition,
}: LeagueHeaderSectionProps) {
  return (
    <Group justify="space-between" align="flex-start">
      <div>
        <Group gap="sm">
          <Title order={2}>{league.name}</Title>
          <Badge color={STATUS_COLORS[league.status]} size="lg">
            {league.status}
          </Badge>
        </Group>
        <Text c="dimmed">
          Round {currentRound} · {members.length} / {league.max_participants}{' '}
          members
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
          myTeamName={getMyTeamName(members, userId)}
        />
        <LeagueStatusAction
          isCommissioner={isCommissioner}
          leagueStatus={league.status}
          membersCount={members.length}
          onOpenDraft={onOpenDraft}
          onOpenLobby={onOpenLobby}
        />
        <LeagueActiveActions
          currentRound={currentRound}
          isCommissioner={isCommissioner}
          leagueStatus={league.status}
          roundComplete={roundComplete}
          roundStatusLoading={roundStatusLoading}
          seasonComplete={seasonComplete}
          onOpenRoster={onOpenRoster}
          onOpenStandings={onOpenStandings}
          onStartNextDraft={onStartNextDraft}
          onOpenTransition={onOpenTransition}
        />
      </Group>
    </Group>
  );
}

function LeagueInviteCodeCard({ inviteCode }: LeagueInviteCodeCardProps) {
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
  currentRound,
  isMobile,
  leagueId,
  members,
  seasonComplete,
  userId,
}: LeagueStandingsCardProps) {
  const sortedMembers = [...members].sort(
    (a: LeagueMemberRow, b: LeagueMemberRow) =>
      (b.total_points ?? 0) - (a.total_points ?? 0)
  );
  const visibleRounds = getVisibleStandingsRounds(currentRound, isMobile);
  const tableMinWidth = isMobile ? 0 : 680;

  return (
    <Card shadow="sm" padding="md" radius="md" withBorder>
      <Title order={4} mb="md">
        Standings
      </Title>
      <Table.ScrollContainer minWidth={tableMinWidth}>
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Rank</Table.Th>
              <Table.Th>Team</Table.Th>
              {!isMobile && <Table.Th>Manager</Table.Th>}
              {visibleRounds.map((round) => (
                <Table.Th key={round} style={{ textAlign: 'right' }}>
                  Round {round}
                </Table.Th>
              ))}
              <Table.Th style={{ textAlign: 'right' }}>Total Points</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {sortedMembers.map((member: LeagueMemberRow, index: number) => (
              <Table.Tr
                key={member.id}
                style={{
                  fontWeight: member.user_id === userId ? 700 : undefined,
                }}
              >
                <Table.Td>{index + 1}</Table.Td>
                <Table.Td>
                  <Anchor
                    component={Link}
                    to={`/roster/${leagueId}/${member.id}`}
                    fw={member.user_id === userId ? 700 : undefined}
                  >
                    {member.team_name}
                    {seasonComplete && index === 0 && ' 🏆'}
                  </Anchor>
                </Table.Td>
                {!isMobile && (
                  <Table.Td>{member.users?.display_name ?? 'Unknown'}</Table.Td>
                )}
                {visibleRounds.map((round) => (
                  <Table.Td key={round} style={{ textAlign: 'right' }}>
                    {getRoundPoints(member.round_points, round)}
                  </Table.Td>
                ))}
                <Table.Td style={{ textAlign: 'right' }}>
                  {member.total_points ?? 0}
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
    </Card>
  );
}

export function LeagueDashboardContent({
  currentRound,
  isCommissioner,
  isMobile,
  league,
  leagueGameCardsError,
  leagueId,
  members,
  roundComplete,
  roundStatusLoading,
  seasonComplete,
  userId,
  widgetSnapshot,
  widgetSnapshotLoading,
  onOpenDraft,
  onOpenLobby,
  onOpenRoster,
  onOpenSettings,
  onOpenStandings,
  onStartNextDraft,
  onOpenTransition,
}: LeagueDashboardContentProps) {
  return (
    <Container size="lg" py="xl">
      <Stack gap="xl">
        <LeagueHeaderSection
          currentRound={currentRound}
          isCommissioner={isCommissioner}
          league={league}
          members={members}
          roundComplete={roundComplete}
          roundStatusLoading={roundStatusLoading}
          seasonComplete={seasonComplete}
          userId={userId}
          onOpenDraft={onOpenDraft}
          onOpenLobby={onOpenLobby}
          onOpenRoster={onOpenRoster}
          onOpenSettings={onOpenSettings}
          onOpenStandings={onOpenStandings}
          onStartNextDraft={onStartNextDraft}
          onOpenTransition={onOpenTransition}
        />

        <LeagueInviteCodeCard inviteCode={league.invite_code} />

        <LeagueStandingsCard
          currentRound={currentRound}
          isMobile={isMobile}
          leagueId={leagueId}
          members={members}
          seasonComplete={seasonComplete}
          userId={userId}
        />

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
