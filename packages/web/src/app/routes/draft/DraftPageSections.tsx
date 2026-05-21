import {
  Alert,
  Badge,
  Button,
  Card,
  Collapse,
  Group,
  Modal,
  ScrollArea,
  SegmentedControl,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
  UnstyledButton,
} from '@mantine/core';
import { MobileCardList, useIsMobile } from '@sportsnot/ui';
import { resolvePickName } from '@sportsnot/utils';
import type { Position } from '@sportsnot/types';
import {
  buildConfirmPositionOptions,
  isConfirmPositionFull,
  sortDraftHistory,
} from './draftPageHelpers';
import { DraftAvailablePlayerBoard } from './DraftAvailablePlayerBoard';
import type {
  ComparePlayer,
  DraftMemberRow,
  DraftPickRow,
  DraftRosterComposition,
  DraftStateRow,
  DraftablePlayer,
  MyRosterGroup,
  MySlotCounts,
  PlayerStatRow,
  RegSeasonStatRow,
  TeamStatRow,
} from './draftPageTypes';

export function DraftRoomHeader({
  draft,
  currentPicker,
  isMyTurn,
  isCommissioner,
}: {
  draft: DraftStateRow;
  currentPicker: DraftMemberRow | undefined;
  isMyTurn: boolean;
  isCommissioner: boolean;
}) {
  return (
    <Group justify="space-between">
      <div>
        <Title order={2}>Draft Room</Title>
        <Text c="dimmed">Round {draft.round}</Text>
        {draft.round === 3 && (
          <Text size="sm" c="blue">
            Conference Finals &amp; Stanley Cup Final
          </Text>
        )}
      </div>
      <Card padding="md" radius="md" withBorder>
        <Stack gap={4} align="center">
          <Text size="sm" c="dimmed">
            Pick #{draft.current_pick}
          </Text>
          <Text fw={700} size="lg">
            {currentPicker?.team_name ?? 'Waiting...'}
          </Text>
          {isMyTurn && (
            <Badge color="green" size="lg">
              Your Turn!
            </Badge>
          )}
          {isCommissioner && !isMyTurn && (
            <Badge color="orange" size="lg">
              Picking for: {currentPicker?.team_name ?? 'Unknown'}
            </Badge>
          )}
        </Stack>
      </Card>
    </Group>
  );
}

export function DraftFilterControls({
  positionFilter,
  onPositionFilterChange,
  searchQuery,
  onSearchQueryChange,
}: {
  positionFilter: string;
  onPositionFilterChange: (value: string) => void;
  searchQuery: string;
  onSearchQueryChange: (value: string) => void;
}) {
  return (
    <Group>
      <SegmentedControl
        value={positionFilter}
        onChange={onPositionFilterChange}
        data={[
          { label: 'All', value: 'ALL' },
          { label: 'Forwards', value: 'F' },
          { label: 'Defense', value: 'D' },
          { label: 'Goalies', value: 'G' },
        ]}
      />
      <TextInput
        placeholder="Search players..."
        value={searchQuery}
        onChange={(event) => onSearchQueryChange(event.currentTarget.value)}
        style={{ flex: 1 }}
      />
    </Group>
  );
}

export function DraftHistoryCard({
  picks,
  playerNameMap,
  teamNameMap,
}: {
  picks: DraftPickRow[];
  playerNameMap: Map<number, string>;
  teamNameMap: Map<number, string>;
}) {
  return (
    <Card shadow="sm" padding="md" radius="md" withBorder>
      <Title order={4} mb="sm">
        Draft History
      </Title>
      {picks.length === 0 ? (
        <Text c="dimmed" size="sm">
          No picks yet
        </Text>
      ) : (
        <ScrollArea h={400}>
          <Stack gap="xs">
            {sortDraftHistory(picks).map((pick) => (
              <Group key={pick.id} justify="space-between">
                <Text size="sm">
                  #{pick.pick_number} -{' '}
                  {pick.league_members?.team_name ?? 'Unknown'}
                  {' · '}
                  {resolvePickName(
                    pick.player_id,
                    pick.team_id,
                    playerNameMap,
                    teamNameMap
                  )}
                </Text>
                <Badge variant="light" size="sm">
                  {pick.position}
                </Badge>
              </Group>
            ))}
          </Stack>
        </ScrollArea>
      )}
    </Card>
  );
}

export function DraftMyTeamCard({
  myTeamOpened,
  onToggleMyTeam,
  myRosterSlots,
  playerNameMap,
  teamNameMap,
}: {
  myTeamOpened: boolean;
  onToggleMyTeam: () => void;
  myRosterSlots: MyRosterGroup[];
  playerNameMap: Map<number, string>;
  teamNameMap: Map<number, string>;
}) {
  return (
    <Card shadow="sm" padding="md" radius="md" withBorder>
      <UnstyledButton onClick={onToggleMyTeam} w="100%">
        <Group justify="space-between">
          <Title order={4}>My Team</Title>
          <Text size="sm" c="dimmed">
            {myTeamOpened ? '▲ Collapse' : '▼ Expand'}
          </Text>
        </Group>
      </UnstyledButton>
      <Collapse in={myTeamOpened}>
        <Stack gap="sm" mt="sm">
          {myRosterSlots.map((group) => (
            <DraftRosterGroupBlock
              key={group.position}
              group={group}
              playerNameMap={playerNameMap}
              teamNameMap={teamNameMap}
            />
          ))}
        </Stack>
      </Collapse>
    </Card>
  );
}

export function DraftAvailablePlayersCard(props: {
  playerStats: PlayerStatRow[];
  cumulativePlayerStats: PlayerStatRow[];
  teamStats: TeamStatRow[];
  cumulativeTeamStats: TeamStatRow[];
  isDraftPoolSyncing: boolean;
  canPick: boolean;
  currentPicker: DraftMemberRow | undefined;
  draftedPlayerIds: Set<number>;
  draftedTeamIds: Set<number>;
  positionFilter: string;
  searchQuery: string;
  onSelectPlayer: (player: DraftablePlayer) => void;
  comparePlayers: ComparePlayer[];
  onToggleCompare: (player: ComparePlayer) => void;
  isRound1: boolean;
  mySlotCounts: MySlotCounts;
  regSeasonStats: RegSeasonStatRow[];
  roster: DraftRosterComposition;
}) {
  const {
    playerStats,
    cumulativePlayerStats,
    teamStats,
    cumulativeTeamStats,
    isDraftPoolSyncing,
    canPick,
    currentPicker,
    ...boardProps
  } = props;

  return (
    <Card shadow="sm" padding="md" radius="md" withBorder>
      <Title order={4} mb="sm">
        Available Players
      </Title>
      {!playerStats.length && !teamStats.length ? (
        <DraftPoolEmptyState
          isDraftPoolSyncing={isDraftPoolSyncing}
          canPick={canPick}
          currentPicker={currentPicker}
        />
      ) : (
        <DraftAvailablePlayerBoard
          playerStats={playerStats}
          cumulativePlayerStats={cumulativePlayerStats}
          teamStats={teamStats}
          cumulativeTeamStats={cumulativeTeamStats}
          canPick={canPick}
          {...boardProps}
        />
      )}
    </Card>
  );
}

export function DraftCompareTray({
  comparePlayers,
  onClearCompare,
  onRemoveCompare,
}: {
  comparePlayers: ComparePlayer[];
  onClearCompare: () => void;
  onRemoveCompare: (playerId: number) => void;
}) {
  const isMobile = useIsMobile();

  if (comparePlayers.length === 0) {
    return null;
  }

  return (
    <Card
      shadow="sm"
      padding="md"
      radius="md"
      withBorder
      data-testid="compare-tray"
    >
      <Group justify="space-between" mb="sm">
        <Title order={4}>Compare ({comparePlayers.length})</Title>
        <Button size="xs" variant="subtle" color="red" onClick={onClearCompare}>
          Clear All
        </Button>
      </Group>
      {isMobile ? (
        <MobileCardList>
          {comparePlayers.map((player) => (
            <DraftCompareCard
              key={player.id}
              player={player}
              onRemoveCompare={onRemoveCompare}
            />
          ))}
        </MobileCardList>
      ) : (
        <Table.ScrollContainer minWidth={600}>
          <Table striped>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Player</Table.Th>
                <Table.Th style={{ textAlign: 'right' }}>Goals</Table.Th>
                <Table.Th style={{ textAlign: 'right' }}>Assists</Table.Th>
                <Table.Th style={{ textAlign: 'right' }}>Points</Table.Th>
                <Table.Th />
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {comparePlayers.map((player) => (
                <DraftCompareRow
                  key={player.id}
                  player={player}
                  onRemoveCompare={onRemoveCompare}
                />
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      )}
    </Card>
  );
}

export function DraftConfirmPickModal({
  confirmPlayer,
  onCloseConfirm,
  pickError,
  confirmPosition,
  onConfirmPositionChange,
  mySlotCounts,
  roster,
  allowIrSlots,
  onConfirmPick,
  submitting,
}: {
  confirmPlayer: DraftablePlayer | null;
  onCloseConfirm: () => void;
  pickError: string | null;
  confirmPosition: Position;
  onConfirmPositionChange: (value: Position) => void;
  mySlotCounts: MySlotCounts;
  roster: DraftRosterComposition;
  allowIrSlots: boolean;
  onConfirmPick: () => void;
  submitting: boolean;
}) {
  return (
    <Modal
      opened={Boolean(confirmPlayer)}
      onClose={onCloseConfirm}
      title="Confirm Draft Pick"
    >
      {confirmPlayer && (
        <Stack gap="md">
          {pickError && (
            <Alert color="red" title="Pick Failed">
              {pickError}
            </Alert>
          )}
          <Text>
            Draft <strong>{confirmPlayer.fullName}</strong> (
            {confirmPlayer.team})?
          </Text>
          <SegmentedControl
            value={confirmPosition}
            onChange={(value) => onConfirmPositionChange(value as Position)}
            data={buildConfirmPositionOptions(
              confirmPlayer.position,
              mySlotCounts,
              roster,
              allowIrSlots
            )}
          />
          <Group justify="flex-end">
            <Button variant="subtle" onClick={onCloseConfirm}>
              Cancel
            </Button>
            <Button
              onClick={onConfirmPick}
              loading={submitting}
              disabled={isConfirmPositionFull(
                confirmPosition,
                mySlotCounts,
                roster
              )}
            >
              Confirm Pick
            </Button>
          </Group>
        </Stack>
      )}
    </Modal>
  );
}

function DraftRosterGroupBlock({
  group,
  playerNameMap,
  teamNameMap,
}: {
  group: MyRosterGroup;
  playerNameMap: Map<number, string>;
  teamNameMap: Map<number, string>;
}) {
  return (
    <div>
      <Text fw={600} size="sm" mb={4}>
        {group.label} ({group.filled.length}/
        {group.filled.length + group.emptyCount})
      </Text>
      <Stack gap={4}>
        {group.filled.map((pick) => (
          <Group key={pick.id} gap="xs">
            <Badge variant="light" size="sm">
              {pick.position}
            </Badge>
            <Text size="sm">
              {resolvePickName(
                pick.player_id,
                pick.team_id,
                playerNameMap,
                teamNameMap
              )}
            </Text>
          </Group>
        ))}
        {Array.from({ length: group.emptyCount }).map((_, index) => (
          <Text key={`empty-${group.position}-${index}`} size="sm" c="dimmed">
            Empty {group.label} slot
          </Text>
        ))}
      </Stack>
    </div>
  );
}

function DraftPoolEmptyState({
  isDraftPoolSyncing,
  canPick,
  currentPicker,
}: {
  isDraftPoolSyncing: boolean;
  canPick: boolean;
  currentPicker: DraftMemberRow | undefined;
}) {
  return (
    <Stack gap="sm">
      <Text size="sm" c="dimmed">
        No player data available yet.
      </Text>
      {isDraftPoolSyncing && (
        <Alert color="blue" title="Syncing current round data">
          Loading the current round draft pool now. This usually takes a few
          seconds.
        </Alert>
      )}
      {canPick ? (
        <Alert color="green" title="It's your turn!">
          Once player data is synced, you'll see a selectable list here.
        </Alert>
      ) : (
        <Alert color="navy">
          Waiting for {currentPicker?.team_name ?? 'the next drafter'} to make
          their pick...
        </Alert>
      )}
    </Stack>
  );
}

function DraftCompareCard({
  player,
  onRemoveCompare,
}: {
  player: ComparePlayer;
  onRemoveCompare: (playerId: number) => void;
}) {
  return (
    <Card padding="sm" radius="sm" withBorder>
      <Group justify="space-between" mb={4}>
        <Text fw={500} size="sm">
          {player.fullName} ({player.team})
        </Text>
        <Button
          size="xs"
          variant="subtle"
          color="red"
          onClick={() => onRemoveCompare(player.id)}
          aria-label={`Remove ${player.fullName}`}
        >
          ✕
        </Button>
      </Group>
      <Group gap="xs">
        <Badge size="sm" variant="light">
          G: {player.goals}
        </Badge>
        <Badge size="sm" variant="light">
          A: {player.assists}
        </Badge>
        <Badge size="sm" variant="filled" color="blue">
          Pts: {player.points}
        </Badge>
      </Group>
    </Card>
  );
}

function DraftCompareRow({
  player,
  onRemoveCompare,
}: {
  player: ComparePlayer;
  onRemoveCompare: (playerId: number) => void;
}) {
  return (
    <Table.Tr>
      <Table.Td>
        {player.fullName} ({player.team})
      </Table.Td>
      <Table.Td style={{ textAlign: 'right' }}>{player.goals}</Table.Td>
      <Table.Td style={{ textAlign: 'right' }}>{player.assists}</Table.Td>
      <Table.Td style={{ textAlign: 'right', fontWeight: 600 }}>
        {player.points}
      </Table.Td>
      <Table.Td>
        <Button
          size="xs"
          variant="subtle"
          color="red"
          onClick={() => onRemoveCompare(player.id)}
          aria-label={`Remove ${player.fullName}`}
        >
          ✕
        </Button>
      </Table.Td>
    </Table.Tr>
  );
}
