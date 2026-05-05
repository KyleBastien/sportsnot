import {
  Badge,
  Button,
  Card,
  Group,
  ScrollArea,
  Table,
  Text,
} from '@mantine/core';
import { MobileCardList } from '@sportsnot/ui';
import { isDraftPositionFull, MAX_COMPARE } from './draftPageHelpers';
import { DraftSkaterRow } from './draftAvailablePlayerBoardUtils';
import type {
  ComparePlayer,
  DraftRosterComposition,
  MySlotCounts,
} from './draftPageTypes';

interface DraftAvailableSkaterSectionProps {
  players: DraftSkaterRow[];
  comparePlayers: ComparePlayer[];
  onToggleCompare: (player: ComparePlayer) => void;
  onSelectPlayer: (player: DraftSkaterRow) => void;
  canPick: boolean;
  isMobile: boolean;
  isRound1: boolean;
  mySlotCounts: MySlotCounts;
  roster: DraftRosterComposition;
}

export function DraftAvailableSkaterSection({
  players,
  comparePlayers,
  onToggleCompare,
  onSelectPlayer,
  canPick,
  isMobile,
  isRound1,
  mySlotCounts,
  roster,
}: DraftAvailableSkaterSectionProps) {
  if (isMobile) {
    return (
      <ScrollArea h={300}>
        <MobileCardList emptyMessage="No available skaters match your filters">
          {players.map((player) => (
            <DraftSkaterMobileCard
              key={player.id}
              player={player}
              comparePlayers={comparePlayers}
              onToggleCompare={onToggleCompare}
              onSelectPlayer={onSelectPlayer}
              canPick={canPick}
              isRound1={isRound1}
              mySlotCounts={mySlotCounts}
              roster={roster}
            />
          ))}
        </MobileCardList>
      </ScrollArea>
    );
  }

  return (
    <ScrollArea h={300}>
      <Table.ScrollContainer minWidth={600}>
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Player</Table.Th>
              <Table.Th>Pos</Table.Th>
              {isRound1 && (
                <Table.Th style={{ textAlign: 'right' }}>
                  Reg Season Pts
                </Table.Th>
              )}
              <Table.Th style={{ textAlign: 'right' }}>G</Table.Th>
              <Table.Th style={{ textAlign: 'right' }}>A</Table.Th>
              <Table.Th style={{ textAlign: 'right' }}>Pts</Table.Th>
              <Table.Th style={{ textAlign: 'right' }}>GP</Table.Th>
              <Table.Th />
              {canPick && <Table.Th />}
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {players.map((player) => (
              <DraftSkaterDesktopRow
                key={player.id}
                player={player}
                comparePlayers={comparePlayers}
                onToggleCompare={onToggleCompare}
                onSelectPlayer={onSelectPlayer}
                canPick={canPick}
                isRound1={isRound1}
                mySlotCounts={mySlotCounts}
                roster={roster}
              />
            ))}
            {players.length === 0 && (
              <Table.Tr>
                <Table.Td colSpan={(isRound1 ? 8 : 7) + (canPick ? 1 : 0)}>
                  <Text c="dimmed" ta="center" size="sm">
                    No available skaters match your filters
                  </Text>
                </Table.Td>
              </Table.Tr>
            )}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
    </ScrollArea>
  );
}

function DraftSkaterMobileCard({
  player,
  comparePlayers,
  onToggleCompare,
  onSelectPlayer,
  canPick,
  isRound1,
  mySlotCounts,
  roster,
}: Omit<DraftAvailableSkaterSectionProps, 'players' | 'isMobile'> & {
  player: DraftSkaterRow;
}) {
  const isCompared = comparePlayers.some((entry) => entry.id === player.id);
  const compareFull = comparePlayers.length >= MAX_COMPARE;

  return (
    <Card padding="sm" radius="sm" withBorder>
      <Group justify="space-between" mb={4}>
        <Group gap="xs">
          <Text fw={500} size="sm">
            {player.fullName}
          </Text>
          <Badge size="xs" variant="light">
            {player.position}
          </Badge>
        </Group>
        <Text size="sm" fw={600} style={{ fontVariantNumeric: 'tabular-nums' }}>
          {player.points} pts
        </Text>
      </Group>
      <Group gap="xs" mb={4}>
        <Text size="xs" c="dimmed">
          G: {player.goals}
        </Text>
        <Text size="xs" c="dimmed">
          A: {player.assists}
        </Text>
        <Text size="xs" c="dimmed">
          GP: {player.gamesPlayed}
        </Text>
        {isRound1 && (
          <Text size="xs" c="dimmed">
            Reg: {player.regSeasonPts}
          </Text>
        )}
      </Group>
      <DraftSkaterActions
        player={player}
        onToggleCompare={onToggleCompare}
        onSelectPlayer={onSelectPlayer}
        canPick={canPick}
        mySlotCounts={mySlotCounts}
        roster={roster}
        isCompared={isCompared}
        compareFull={compareFull}
      />
    </Card>
  );
}

function DraftSkaterDesktopRow({
  player,
  comparePlayers,
  onToggleCompare,
  onSelectPlayer,
  canPick,
  isRound1,
  mySlotCounts,
  roster,
}: Omit<DraftAvailableSkaterSectionProps, 'players' | 'isMobile'> & {
  player: DraftSkaterRow;
}) {
  const isCompared = comparePlayers.some((entry) => entry.id === player.id);
  const compareFull = comparePlayers.length >= MAX_COMPARE;

  return (
    <Table.Tr>
      <Table.Td>{player.fullName}</Table.Td>
      <Table.Td>
        <Badge size="xs" variant="light">
          {player.position}
        </Badge>
      </Table.Td>
      {isRound1 && (
        <Table.Td style={{ textAlign: 'right', fontWeight: 600 }}>
          {player.regSeasonPts}
        </Table.Td>
      )}
      <Table.Td style={{ textAlign: 'right' }}>{player.goals}</Table.Td>
      <Table.Td style={{ textAlign: 'right' }}>{player.assists}</Table.Td>
      <Table.Td style={{ textAlign: 'right', fontWeight: 600 }}>
        {player.points}
      </Table.Td>
      <Table.Td style={{ textAlign: 'right' }}>{player.gamesPlayed}</Table.Td>
      <Table.Td>
        <DraftCompareButton
          player={player}
          onToggleCompare={onToggleCompare}
          isCompared={isCompared}
          compareFull={compareFull}
        />
      </Table.Td>
      {canPick && (
        <Table.Td>
          <DraftSelectButton
            player={player}
            onSelectPlayer={onSelectPlayer}
            mySlotCounts={mySlotCounts}
            roster={roster}
          />
        </Table.Td>
      )}
    </Table.Tr>
  );
}

function DraftSkaterActions({
  player,
  onToggleCompare,
  onSelectPlayer,
  canPick,
  mySlotCounts,
  roster,
  isCompared,
  compareFull,
}: Omit<
  DraftAvailableSkaterSectionProps,
  'players' | 'isMobile' | 'isRound1'
> & {
  player: DraftSkaterRow;
  isCompared: boolean;
  compareFull: boolean;
}) {
  return (
    <Group gap="xs">
      <DraftCompareButton
        player={player}
        onToggleCompare={onToggleCompare}
        isCompared={isCompared}
        compareFull={compareFull}
      />
      {canPick && (
        <DraftSelectButton
          player={player}
          onSelectPlayer={onSelectPlayer}
          mySlotCounts={mySlotCounts}
          roster={roster}
        />
      )}
    </Group>
  );
}

function DraftCompareButton({
  player,
  onToggleCompare,
  isCompared,
  compareFull,
}: {
  player: DraftSkaterRow;
  onToggleCompare: (player: ComparePlayer) => void;
  isCompared: boolean;
  compareFull: boolean;
}) {
  return (
    <Button
      size="xs"
      variant={isCompared ? 'filled' : 'outline'}
      color={isCompared ? 'blue' : 'gray'}
      disabled={!isCompared && compareFull}
      onClick={() => onToggleCompare(toComparePlayer(player))}
    >
      {isCompared ? 'Compared' : 'Compare'}
    </Button>
  );
}

function DraftSelectButton({
  player,
  onSelectPlayer,
  mySlotCounts,
  roster,
}: {
  player: DraftSkaterRow;
  onSelectPlayer: (player: DraftSkaterRow) => void;
  mySlotCounts: MySlotCounts;
  roster: DraftRosterComposition;
}) {
  return (
    <Button
      size="xs"
      variant="light"
      disabled={isDraftPositionFull(player.position, mySlotCounts, roster)}
      onClick={() => onSelectPlayer(player)}
    >
      Draft
    </Button>
  );
}

function toComparePlayer(player: DraftSkaterRow): ComparePlayer {
  return {
    id: player.id,
    fullName: player.fullName,
    position: player.position,
    team: player.team,
    goals: player.goals,
    assists: player.assists,
    points: player.points,
  };
}
