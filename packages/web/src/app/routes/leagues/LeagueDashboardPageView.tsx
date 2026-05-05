import { Container, Stack } from '@mantine/core';
import { LeagueMemberRow } from './leagueDashboardTypes';
import {
  LeagueActiveGamesSection,
  LeagueDashboardHeader,
  LeagueInviteCodeCard,
  LeagueStandingsCard,
} from './LeagueDashboardSections';

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
        <LeagueDashboardHeader
          league={league}
          statusColor={statusColor}
          membersCount={members.length}
          isCommissioner={isCommissioner}
          currentUserTeamName={currentUserTeamName}
          seasonComplete={seasonComplete}
          roundComplete={roundComplete}
          roundStatusLoading={roundStatusLoading}
          onOpenSettings={onOpenSettings}
          onStartDraft={onStartDraft}
          onGoToDraft={onGoToDraft}
          onOpenRoster={onOpenRoster}
          onOpenStandings={onOpenStandings}
          onStartNextDraft={onStartNextDraft}
        />
        <LeagueInviteCodeCard inviteCode={league.invite_code} />
        <LeagueStandingsCard
          leagueId={league.id}
          sortedMembers={sortedMembers}
          currentUserId={currentUserId}
          isMobile={isMobile}
          seasonComplete={seasonComplete}
        />
        <LeagueActiveGamesSection
          leagueStatus={league.status}
          widgetSnapshot={widgetSnapshot}
          widgetSnapshotLoading={widgetSnapshotLoading}
          leagueGameCardsError={leagueGameCardsError}
        />
      </Stack>
    </Container>
  );
}
