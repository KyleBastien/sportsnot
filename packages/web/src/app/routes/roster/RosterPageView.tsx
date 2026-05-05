import { Alert, Container, Stack, Text, Title } from '@mantine/core';
import { RosterGroupSection } from './RosterGroupSection';
import {
  IrActivationModal,
  RosterMemberSelect,
  RosterScoringText,
  RosterSummaryHeader,
} from './RosterPageSections';
import type {
  IrModalState,
  RosterGroup,
  RosterMemberOption,
  RosterSlotRow,
} from './rosterTypes';

interface RosterPageViewProps {
  memberOptions: RosterMemberOption[];
  selectedMemberId: string;
  onMemberChange: (value: string | null) => void;
  rosterTitle: string;
  round: number;
  roundPoints: number;
  totalPoints: number;
  groupedSlots: RosterGroup[];
  slots: RosterSlotRow[];
  isOwnRoster: boolean;
  playerStatsLoading: boolean;
  injuredPlayerIds: Set<number>;
  playerNameMap: Map<number, string>;
  teamNameMap: Map<number, string>;
  playerTeamAbbreviationMap: Map<number, string>;
  teamAbbreviationMap: Map<number, string>;
  isMobile: boolean;
  onOpenIrModal: (slotId: string, candidates: RosterSlotRow[]) => void;
  irModal: IrModalState | null;
  selectedInjuredSlotId: string | null;
  onSelectedInjuredSlotIdChange: (value: string) => void;
  onCloseIrModal: () => void;
  onActivateIr: () => void;
  activating: boolean;
}

interface EmptyRosterStateProps {
  rosterTitle: string;
  round: number;
  memberOptions: RosterMemberOption[];
  selectedMemberId: string;
  onMemberChange: (value: string | null) => void;
  isOwnRoster: boolean;
}

export function RosterPageErrorState() {
  return (
    <Container size="md" py="xl">
      <Alert color="red" title="Error">
        Could not load roster.
      </Alert>
    </Container>
  );
}

export function RosterPageEmptyState({
  rosterTitle,
  round,
  memberOptions,
  selectedMemberId,
  onMemberChange,
  isOwnRoster,
}: EmptyRosterStateProps) {
  return (
    <Container size="md" py="xl">
      <Stack gap="lg" align="center">
        <Title order={2}>{rosterTitle}</Title>
        <Text c="dimmed">Round {round}</Text>
        <RosterMemberSelect
          memberOptions={memberOptions}
          selectedMemberId={selectedMemberId}
          onMemberChange={onMemberChange}
        />
        <Alert color="navy" title="No Roster Yet">
          {isOwnRoster
            ? `Your roster for Round ${round} has not been set yet. Waiting for the draft to begin.`
            : `This team's roster for Round ${round} has not been set yet.`}
        </Alert>
      </Stack>
    </Container>
  );
}

export function RosterPageView({
  memberOptions,
  selectedMemberId,
  onMemberChange,
  rosterTitle,
  round,
  roundPoints,
  totalPoints,
  groupedSlots,
  slots,
  isOwnRoster,
  playerStatsLoading,
  injuredPlayerIds,
  playerNameMap,
  teamNameMap,
  playerTeamAbbreviationMap,
  teamAbbreviationMap,
  isMobile,
  onOpenIrModal,
  irModal,
  selectedInjuredSlotId,
  onSelectedInjuredSlotIdChange,
  onCloseIrModal,
  onActivateIr,
  activating,
}: RosterPageViewProps) {
  return (
    <Container size="lg" py="xl">
      <Stack gap="xl">
        <RosterMemberSelect
          label="View roster"
          memberOptions={memberOptions}
          selectedMemberId={selectedMemberId}
          onMemberChange={onMemberChange}
        />
        <RosterSummaryHeader
          rosterTitle={rosterTitle}
          round={round}
          roundPoints={roundPoints}
          totalPoints={totalPoints}
        />
        <RosterScoringText />
        {groupedSlots.map((group) => (
          <RosterGroupSection
            key={group.position}
            group={group}
            slots={slots}
            isOwnRoster={isOwnRoster}
            playerStatsLoading={playerStatsLoading}
            injuredPlayerIds={injuredPlayerIds}
            playerNameMap={playerNameMap}
            teamNameMap={teamNameMap}
            playerTeamAbbreviationMap={playerTeamAbbreviationMap}
            teamAbbreviationMap={teamAbbreviationMap}
            isMobile={isMobile}
            onOpenIrModal={onOpenIrModal}
          />
        ))}
        <IrActivationModal
          irModal={irModal}
          onCloseIrModal={onCloseIrModal}
          selectedInjuredSlotId={selectedInjuredSlotId}
          onSelectedInjuredSlotIdChange={onSelectedInjuredSlotIdChange}
          onActivateIr={onActivateIr}
          activating={activating}
          playerNameMap={playerNameMap}
          teamNameMap={teamNameMap}
        />
      </Stack>
    </Container>
  );
}
