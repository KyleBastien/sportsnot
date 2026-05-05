import {
  Alert,
  Button,
  Card,
  Container,
  Group,
  Modal,
  Radio,
  Select,
  Stack,
  Text,
  Title,
} from '@mantine/core';
import { SCORING } from '@sportsnot/types';
import { resolvePickName } from '@sportsnot/utils';
import { RosterGroupSection } from './RosterGroupSection';
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
        {memberOptions.length > 1 && (
          <Select
            data={memberOptions}
            value={selectedMemberId}
            onChange={onMemberChange}
            w={300}
            allowDeselect={false}
          />
        )}
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
        {memberOptions.length > 1 && (
          <Select
            label="View roster"
            data={memberOptions}
            value={selectedMemberId}
            onChange={onMemberChange}
            w={300}
            allowDeselect={false}
          />
        )}
        <Group justify="space-between">
          <div>
            <Title order={2}>{rosterTitle}</Title>
            <Text c="dimmed">Round {round}</Text>
          </div>
          <Group gap="md">
            <Card padding="md" radius="md" withBorder>
              <Stack gap={0} align="center">
                <Text size="sm" c="dimmed">
                  Round {round} Points
                </Text>
                <Text fw={700} size="xl">
                  {roundPoints}
                </Text>
              </Stack>
            </Card>
            <Card padding="md" radius="md" withBorder>
              <Stack gap={0} align="center">
                <Text size="sm" c="dimmed">
                  Total Points
                </Text>
                <Text fw={700} size="xl">
                  {totalPoints}
                </Text>
              </Stack>
            </Card>
          </Group>
        </Group>

        <Text size="sm" c="dimmed">
          Scoring: Goal = {SCORING.goal}pt · Assist = {SCORING.assist}pt · Win ={' '}
          {SCORING.win}pts · Shutout = {SCORING.shutout}pts
        </Text>

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

        <Modal
          opened={!!irModal}
          onClose={onCloseIrModal}
          title="Activate IR Player"
        >
          {irModal && (
            <Stack gap="md">
              <Alert color="orange">
                Activating an IR player will remove all points from the injured
                player and retroactively grant the IR player&apos;s points for
                this round.
              </Alert>
              <Text fw={500} size="sm">
                Select the injured player to replace:
              </Text>
              <Radio.Group
                value={selectedInjuredSlotId ?? ''}
                onChange={onSelectedInjuredSlotIdChange}
              >
                <Stack gap="xs">
                  {irModal.candidates.map((candidate) => (
                    <Radio
                      key={candidate.id}
                      value={candidate.id}
                      label={resolvePickName(
                        candidate.player_id,
                        candidate.team_id,
                        playerNameMap,
                        teamNameMap
                      )}
                    />
                  ))}
                </Stack>
              </Radio.Group>
              <Group justify="flex-end">
                <Button variant="subtle" onClick={onCloseIrModal}>
                  Cancel
                </Button>
                <Button
                  color="orange"
                  onClick={onActivateIr}
                  loading={activating}
                  disabled={!selectedInjuredSlotId}
                >
                  Activate IR Player
                </Button>
              </Group>
            </Stack>
          )}
        </Modal>
      </Stack>
    </Container>
  );
}
