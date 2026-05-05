import { Button, Container, Stack } from '@mantine/core';
import {
  RoundTransitionAction,
  RoundTransitionHistory,
  RoundTransitionStandings,
  RoundTransitionSummary,
} from './RoundTransitionSections';

interface TransitionMemberRow {
  id: string;
  user_id: string;
  team_name: string;
  total_points: number;
  users?: { display_name?: string } | null;
}

interface CompletedDraftRow {
  id: string;
  round: number;
  status: string;
  completed_at: string | null;
}

interface RoundTransitionPageViewProps {
  leagueName: string;
  currentRound: number;
  nextRound: number;
  sortedMembers: TransitionMemberRow[];
  currentUserId: string | undefined;
  isMobile: boolean;
  completedDrafts: CompletedDraftRow[];
  isCommissioner: boolean;
  starting: boolean;
  onStartReDraft: () => void;
  onBackToLeague: () => void;
}

export function RoundTransitionPageView({
  leagueName,
  currentRound,
  nextRound,
  sortedMembers,
  currentUserId,
  isMobile,
  completedDrafts,
  isCommissioner,
  starting,
  onStartReDraft,
  onBackToLeague,
}: RoundTransitionPageViewProps) {
  return (
    <Container size="md" py="xl">
      <Stack gap="xl">
        <RoundTransitionSummary
          leagueName={leagueName}
          currentRound={currentRound}
          nextRound={nextRound}
        />
        <RoundTransitionStandings
          currentRound={currentRound}
          sortedMembers={sortedMembers}
          currentUserId={currentUserId}
          isMobile={isMobile}
        />
        <RoundTransitionHistory completedDrafts={completedDrafts} />
        <RoundTransitionAction
          isCommissioner={isCommissioner}
          nextRound={nextRound}
          starting={starting}
          onStartReDraft={onStartReDraft}
        />
        <Button variant="subtle" onClick={onBackToLeague}>
          Back to League
        </Button>
      </Stack>
    </Container>
  );
}
