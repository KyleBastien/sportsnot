import { Badge, Button, Card, Group, Table, Text, Title } from '@mantine/core';
import { DataRow, MobileCardList } from '@sportsnot/ui';
import { resolvePickName } from '@sportsnot/utils';
import {
  groupHasActions,
  getInjuredReplacementCandidates,
  getSlotNhlTeamAbbreviation,
} from './rosterUtils';
import type { RosterGroup, RosterSlotRow } from './rosterTypes';

interface RosterGroupSectionProps {
  group: RosterGroup;
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
}

function RosterStatusBadges({ slot }: { slot: RosterSlotRow }) {
  return (
    <Group gap={4}>
      {slot.is_eliminated ? (
        <Badge color="red" size="sm">
          Eliminated
        </Badge>
      ) : slot.is_active ? (
        <Badge color="green" size="sm">
          Active
        </Badge>
      ) : (
        <Badge color="gray" size="sm">
          Inactive
        </Badge>
      )}
      {slot.activated_from_ir && (
        <Badge color="orange" size="sm">
          From IR
        </Badge>
      )}
    </Group>
  );
}

function RosterSlotActionButton({
  slot,
  injuredCandidates,
  onOpenIrModal,
}: {
  slot: RosterSlotRow;
  injuredCandidates: RosterSlotRow[];
  onOpenIrModal: (slotId: string, candidates: RosterSlotRow[]) => void;
}) {
  if (
    (slot.position !== 'IR_F' && slot.position !== 'IR_D') ||
    slot.activated_from_ir ||
    injuredCandidates.length === 0
  ) {
    return null;
  }

  return (
    <Button
      size="xs"
      variant="outline"
      color="orange"
      onClick={() => onOpenIrModal(slot.id, injuredCandidates)}
    >
      Activate IR
    </Button>
  );
}

function MobileRosterSlotCard({
  slot,
  slots,
  injuredPlayerIds,
  playerNameMap,
  teamNameMap,
  playerTeamAbbreviationMap,
  teamAbbreviationMap,
  playerStatsLoading,
  isOwnRoster,
  onOpenIrModal,
}: {
  slot: RosterSlotRow;
  slots: RosterSlotRow[];
  injuredPlayerIds: Set<number>;
  playerNameMap: Map<number, string>;
  teamNameMap: Map<number, string>;
  playerTeamAbbreviationMap: Map<number, string>;
  teamAbbreviationMap: Map<number, string>;
  playerStatsLoading: boolean;
  isOwnRoster: boolean;
  onOpenIrModal: (slotId: string, candidates: RosterSlotRow[]) => void;
}) {
  const injuredCandidates = getInjuredReplacementCandidates(
    slot,
    slots,
    injuredPlayerIds
  );

  return (
    <Card key={slot.id} padding="sm" radius="sm" withBorder>
      <Group justify="space-between" mb={4}>
        <Text
          fw={500}
          size="sm"
          style={
            slot.is_eliminated ? { textDecoration: 'line-through' } : undefined
          }
        >
          {resolvePickName(
            slot.player_id,
            slot.team_id,
            playerNameMap,
            teamNameMap
          )}
        </Text>
        <Text size="sm" fw={500}>
          {slot.points_earned ?? 0}
        </Text>
      </Group>
      <DataRow
        label="NHL Team"
        value={getSlotNhlTeamAbbreviation(
          slot,
          playerTeamAbbreviationMap,
          teamAbbreviationMap
        )}
      />
      <DataRow label="Status" value={<RosterStatusBadges slot={slot} />} />
      {!playerStatsLoading && isOwnRoster && (
        <Button
          size="xs"
          variant="outline"
          color="orange"
          mt="xs"
          fullWidth
          onClick={() => onOpenIrModal(slot.id, injuredCandidates)}
          disabled={injuredCandidates.length === 0 || slot.activated_from_ir}
          style={
            slot.position !== 'IR_F' && slot.position !== 'IR_D'
              ? { display: 'none' }
              : undefined
          }
        >
          Activate IR
        </Button>
      )}
    </Card>
  );
}

function DesktopRosterTable({
  group,
  slots,
  injuredPlayerIds,
  playerNameMap,
  teamNameMap,
  playerTeamAbbreviationMap,
  teamAbbreviationMap,
  playerStatsLoading,
  isOwnRoster,
  onOpenIrModal,
}: {
  group: RosterGroup;
  slots: RosterSlotRow[];
  injuredPlayerIds: Set<number>;
  playerNameMap: Map<number, string>;
  teamNameMap: Map<number, string>;
  playerTeamAbbreviationMap: Map<number, string>;
  teamAbbreviationMap: Map<number, string>;
  playerStatsLoading: boolean;
  isOwnRoster: boolean;
  onOpenIrModal: (slotId: string, candidates: RosterSlotRow[]) => void;
}) {
  const hasAnyActions =
    isOwnRoster &&
    !playerStatsLoading &&
    groupHasActions(group.position, group.players, slots, injuredPlayerIds);

  return (
    <Table.ScrollContainer minWidth={640}>
      <Table>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Player/Team</Table.Th>
            <Table.Th>NHL Team</Table.Th>
            <Table.Th>Status</Table.Th>
            <Table.Th style={{ textAlign: 'right' }}>Points</Table.Th>
            {hasAnyActions && <Table.Th>Actions</Table.Th>}
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {group.players.map((slot) => {
            const injuredCandidates = getInjuredReplacementCandidates(
              slot,
              slots,
              injuredPlayerIds
            );

            return (
              <Table.Tr key={slot.id}>
                <Table.Td>
                  <span
                    style={
                      slot.is_eliminated
                        ? { textDecoration: 'line-through' }
                        : undefined
                    }
                  >
                    {resolvePickName(
                      slot.player_id,
                      slot.team_id,
                      playerNameMap,
                      teamNameMap
                    )}
                  </span>
                </Table.Td>
                <Table.Td>
                  {getSlotNhlTeamAbbreviation(
                    slot,
                    playerTeamAbbreviationMap,
                    teamAbbreviationMap
                  )}
                </Table.Td>
                <Table.Td>
                  <RosterStatusBadges slot={slot} />
                </Table.Td>
                <Table.Td style={{ textAlign: 'right' }}>
                  {slot.points_earned ?? 0}
                </Table.Td>
                {hasAnyActions && (
                  <Table.Td>
                    <RosterSlotActionButton
                      slot={slot}
                      injuredCandidates={injuredCandidates}
                      onOpenIrModal={onOpenIrModal}
                    />
                  </Table.Td>
                )}
              </Table.Tr>
            );
          })}
        </Table.Tbody>
      </Table>
    </Table.ScrollContainer>
  );
}

export function RosterGroupSection({
  group,
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
}: RosterGroupSectionProps) {
  return (
    <Card shadow="sm" padding="md" radius="md" withBorder>
      <Group justify="space-between" mb="sm">
        <Title order={4}>{group.label}</Title>
        <Badge variant="light">
          {group.players.length} player
          {group.players.length !== 1 ? 's' : ''}
        </Badge>
      </Group>

      {group.players.length === 0 ? (
        <Text c="dimmed" size="sm">
          No player drafted in this slot
        </Text>
      ) : isMobile ? (
        <MobileCardList>
          {group.players.map((slot) => (
            <MobileRosterSlotCard
              key={slot.id}
              slot={slot}
              slots={slots}
              injuredPlayerIds={injuredPlayerIds}
              playerNameMap={playerNameMap}
              teamNameMap={teamNameMap}
              playerTeamAbbreviationMap={playerTeamAbbreviationMap}
              teamAbbreviationMap={teamAbbreviationMap}
              playerStatsLoading={playerStatsLoading}
              isOwnRoster={isOwnRoster}
              onOpenIrModal={onOpenIrModal}
            />
          ))}
        </MobileCardList>
      ) : (
        <DesktopRosterTable
          group={group}
          slots={slots}
          injuredPlayerIds={injuredPlayerIds}
          playerNameMap={playerNameMap}
          teamNameMap={teamNameMap}
          playerTeamAbbreviationMap={playerTeamAbbreviationMap}
          teamAbbreviationMap={teamAbbreviationMap}
          playerStatsLoading={playerStatsLoading}
          isOwnRoster={isOwnRoster}
          onOpenIrModal={onOpenIrModal}
        />
      )}
    </Card>
  );
}
