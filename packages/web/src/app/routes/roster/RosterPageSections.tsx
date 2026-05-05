import {
  Alert,
  Button,
  Card,
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
import type { IrModalState, RosterMemberOption } from './rosterTypes';

export function RosterMemberSelect({
  memberOptions,
  selectedMemberId,
  onMemberChange,
  label,
}: {
  memberOptions: RosterMemberOption[];
  selectedMemberId: string;
  onMemberChange: (value: string | null) => void;
  label?: string;
}) {
  if (memberOptions.length <= 1) {
    return null;
  }

  return (
    <Select
      label={label}
      data={memberOptions}
      value={selectedMemberId}
      onChange={onMemberChange}
      w={300}
      allowDeselect={false}
    />
  );
}

export function RosterSummaryHeader({
  rosterTitle,
  round,
  roundPoints,
  totalPoints,
}: {
  rosterTitle: string;
  round: number;
  roundPoints: number;
  totalPoints: number;
}) {
  return (
    <Group justify="space-between">
      <div>
        <Title order={2}>{rosterTitle}</Title>
        <Text c="dimmed">Round {round}</Text>
      </div>
      <Group gap="md">
        <RosterPointCard label={`Round ${round} Points`} value={roundPoints} />
        <RosterPointCard label="Total Points" value={totalPoints} />
      </Group>
    </Group>
  );
}

export function RosterScoringText() {
  return (
    <Text size="sm" c="dimmed">
      Scoring: Goal = {SCORING.goal}pt · Assist = {SCORING.assist}pt · Win ={' '}
      {SCORING.win}pts · Shutout = {SCORING.shutout}pts
    </Text>
  );
}

export function IrActivationModal({
  irModal,
  onCloseIrModal,
  selectedInjuredSlotId,
  onSelectedInjuredSlotIdChange,
  onActivateIr,
  activating,
  playerNameMap,
  teamNameMap,
}: {
  irModal: IrModalState | null;
  onCloseIrModal: () => void;
  selectedInjuredSlotId: string | null;
  onSelectedInjuredSlotIdChange: (value: string) => void;
  onActivateIr: () => void;
  activating: boolean;
  playerNameMap: Map<number, string>;
  teamNameMap: Map<number, string>;
}) {
  return (
    <Modal
      opened={!!irModal}
      onClose={onCloseIrModal}
      title="Activate IR Player"
    >
      {irModal && (
        <Stack gap="md">
          <Alert color="orange">
            Activating an IR player will remove all points from the injured
            player and retroactively grant the IR player&apos;s points for this
            round.
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
  );
}

function RosterPointCard({ label, value }: { label: string; value: number }) {
  return (
    <Card padding="md" radius="md" withBorder>
      <Stack gap={0} align="center">
        <Text size="sm" c="dimmed">
          {label}
        </Text>
        <Text fw={700} size="xl">
          {value}
        </Text>
      </Stack>
    </Card>
  );
}
