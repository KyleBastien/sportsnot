import {
  Alert,
  Button,
  Card,
  Group,
  Modal,
  Radio,
  Select,
  SegmentedControl,
  Stack,
  Text,
  Title,
} from '@mantine/core';
import { SCORING } from '@sportsnot/types';
import { resolvePickName } from '@sportsnot/utils';
import { getAvailableRounds } from '../../utils/roundUtils';
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
  currentRound,
  roundPoints,
  totalPoints,
  isHistorical,
}: {
  rosterTitle: string;
  round: number;
  currentRound: number;
  roundPoints: number;
  totalPoints: number;
  isHistorical: boolean;
}) {
  return (
    <Group justify="space-between">
      <div>
        <Title order={2}>{rosterTitle}</Title>
        <Text c="dimmed">
          {isHistorical
            ? `Viewing Round ${round} snapshot · League is in Round ${currentRound}`
            : `Round ${round}`}
        </Text>
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

export function RosterRoundSelect({
  currentRound,
  selectedRound,
  onRoundChange,
}: {
  currentRound: number;
  selectedRound: string;
  onRoundChange: (value: string) => void;
}) {
  if (currentRound <= 1) {
    return null;
  }

  return (
    <Stack gap={4}>
      <Text size="sm" fw={500}>
        View round
      </Text>
      <SegmentedControl
        fullWidth
        value={selectedRound}
        onChange={onRoundChange}
        data={getAvailableRounds(currentRound).map((round) => ({
          label: `Round ${round}`,
          value: String(round),
        }))}
      />
    </Stack>
  );
}

export function HistoricalRosterNotice({
  round,
  currentRound,
}: {
  round: number;
  currentRound: number;
}) {
  return (
    <Alert color="blue" title="Historical snapshot">
      Viewing Round {round} while league is in Round {currentRound}. Historical
      rosters are read-only.
    </Alert>
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
