import { useRef } from 'react';
import {
  Modal,
  Group,
  Stack,
  Text,
  Avatar,
  Badge,
  Table,
  ScrollArea,
  Skeleton,
  Button,
} from '@mantine/core';
import { useMediaQuery } from '@mantine/hooks';
import { useQuery } from '@tanstack/react-query';
import { useVirtualizer } from '@tanstack/react-virtual';
import { getPlayer, getPlayerGameLog } from '@sportsnot/nhl-api';
import { usePlayerDetailContext } from '../context/PlayerDetailContext';
import { useCompareContext } from '../context/CompareContext';

const CURRENT_SEASON = '20252026';

export function PlayerDetailModal() {
  const { selectedPlayerId, closePlayerDetail } = usePlayerDetailContext();
  const { addPlayer, removePlayer, players, isFull } = useCompareContext();
  const isMobile = useMediaQuery('(max-width: 48em)');

  const opened = selectedPlayerId !== null;

  const { data: player, isLoading: playerLoading } = useQuery({
    queryKey: ['player-detail', selectedPlayerId],
    queryFn: () => getPlayer(selectedPlayerId!),
    enabled: !!selectedPlayerId,
  });

  const { data: gameLog, isLoading: gameLogLoading } = useQuery({
    queryKey: ['player-game-log', selectedPlayerId],
    queryFn: () => getPlayerGameLog(selectedPlayerId!, CURRENT_SEASON, 3),
    enabled: !!selectedPlayerId,
  });

  const isInCompare = players.some((p) => p.playerId === selectedPlayerId);

  const handleCompareToggle = () => {
    if (!player || !selectedPlayerId) return;
    if (isInCompare) {
      removePlayer(selectedPlayerId);
    } else {
      addPlayer({
        playerId: player.id,
        name: player.fullName,
        teamAbbrev: player.currentTeam?.abbreviation ?? '',
        position: player.primaryPosition?.abbreviation ?? '',
        headshot: player.headshot,
        stats: buildStatsFromGameLog(gameLog ?? []),
      });
    }
  };

  const isLoading = playerLoading || gameLogLoading;
  const allGames = gameLog ?? [];
  const useVirtual = allGames.length > 20;

  return (
    <Modal
      opened={opened}
      onClose={closePlayerDetail}
      title="Player Details"
      fullScreen={!!isMobile}
      size="lg"
    >
      {isLoading ? (
        <Stack gap="md">
          <Group>
            <Skeleton height={80} circle />
            <Stack gap="xs">
              <Skeleton height={20} width={200} />
              <Skeleton height={14} width={120} />
            </Stack>
          </Group>
          <Skeleton height={14} width="100%" />
          <Skeleton height={14} width="100%" />
          <Skeleton height={200} />
        </Stack>
      ) : player ? (
        <Stack gap="md">
          {/* Player header */}
          <Group justify="space-between" align="flex-start">
            <Group>
              <Avatar
                src={player.headshot}
                alt={player.fullName}
                size={80}
                radius="xl"
              />
              <Stack gap={4}>
                <Text size="xl" fw={700}>
                  {player.fullName}
                </Text>
                <Group gap="xs">
                  <Text size="sm" c="dimmed">
                    {player.currentTeam?.name ?? 'Free Agent'}
                  </Text>
                  <Badge size="sm" variant="light">
                    {player.primaryPosition?.abbreviation ?? ''}
                  </Badge>
                </Group>
                <Group gap="xs">
                  <Text size="xs" c="dimmed">
                    #{player.primaryNumber ?? '—'}
                  </Text>
                  <Text size="xs" c="dimmed">
                    {player.height} / {player.weight} lbs
                  </Text>
                  <Text size="xs" c="dimmed">
                    Shoots: {player.shootsCatches}
                  </Text>
                </Group>
              </Stack>
            </Group>
            <Button
              variant={isInCompare ? 'filled' : 'outline'}
              color={isInCompare ? 'red' : 'blue'}
              size="sm"
              disabled={!isInCompare && isFull}
              onClick={handleCompareToggle}
            >
              {isInCompare ? 'Remove from Compare' : 'Add to Compare'}
            </Button>
          </Group>

          {/* Season totals */}
          {allGames.length > 0 && (
            <>
              <Text fw={600} size="sm">
                Playoff Totals
              </Text>
              <SeasonTotals games={allGames} />
            </>
          )}

          {/* Game log */}
          <Text fw={600} size="sm">
            Game Log ({allGames.length} games)
          </Text>
          {allGames.length === 0 ? (
            <Text c="dimmed" size="sm">
              No playoff game data available.
            </Text>
          ) : useVirtual ? (
            <VirtualizedGameLog games={allGames} />
          ) : (
            <ScrollArea>
              <GameLogTable games={allGames} />
            </ScrollArea>
          )}
        </Stack>
      ) : (
        <Text c="dimmed">Player not found.</Text>
      )}
    </Modal>
  );
}

interface GameLogEntry {
  gameId: number;
  gameDate: string;
  opponentAbbrev: string;
  goals: number;
  assists: number;
  points: number;
  plusMinus: number;
  pim: number;
  shots: number;
  toi: string;
}

function GameLogTableHead() {
  return (
    <Table.Thead>
      <Table.Tr>
        <Table.Th>Date</Table.Th>
        <Table.Th>vs</Table.Th>
        <Table.Th style={{ textAlign: 'right' }}>G</Table.Th>
        <Table.Th style={{ textAlign: 'right' }}>A</Table.Th>
        <Table.Th style={{ textAlign: 'right' }}>Pts</Table.Th>
        <Table.Th style={{ textAlign: 'right' }}>+/-</Table.Th>
        <Table.Th style={{ textAlign: 'right' }}>PIM</Table.Th>
        <Table.Th style={{ textAlign: 'right' }}>SOG</Table.Th>
        <Table.Th style={{ textAlign: 'right' }}>TOI</Table.Th>
      </Table.Tr>
    </Table.Thead>
  );
}

function GameLogRow({ game }: { game: GameLogEntry }) {
  return (
    <Table.Tr key={game.gameId}>
      <Table.Td>
        <Text size="sm">
          {new Date(game.gameDate).toLocaleDateString('en-US', {
            month: 'short',
            day: 'numeric',
          })}
        </Text>
      </Table.Td>
      <Table.Td>
        <Text size="sm">{game.opponentAbbrev}</Text>
      </Table.Td>
      <Table.Td style={{ textAlign: 'right' }}>{game.goals}</Table.Td>
      <Table.Td style={{ textAlign: 'right' }}>{game.assists}</Table.Td>
      <Table.Td style={{ textAlign: 'right', fontWeight: 600 }}>
        {game.points}
      </Table.Td>
      <Table.Td style={{ textAlign: 'right' }}>
        {game.plusMinus > 0 ? `+${game.plusMinus}` : game.plusMinus}
      </Table.Td>
      <Table.Td style={{ textAlign: 'right' }}>{game.pim}</Table.Td>
      <Table.Td style={{ textAlign: 'right' }}>{game.shots}</Table.Td>
      <Table.Td style={{ textAlign: 'right' }}>{game.toi}</Table.Td>
    </Table.Tr>
  );
}

function GameLogTable({ games }: { games: GameLogEntry[] }) {
  return (
    <Table striped highlightOnHover>
      <GameLogTableHead />
      <Table.Tbody>
        {games.map((game) => (
          <GameLogRow key={game.gameId} game={game} />
        ))}
      </Table.Tbody>
    </Table>
  );
}

function VirtualizedGameLog({ games }: { games: GameLogEntry[] }) {
  const scrollRef = useRef<HTMLDivElement>(null);

  const virtualizer = useVirtualizer({
    count: games.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => 36,
    overscan: 5,
  });

  return (
    <div ref={scrollRef} style={{ height: 400, overflow: 'auto' }}>
      <Table striped highlightOnHover>
        <GameLogTableHead />
        <Table.Tbody>
          {virtualizer.getVirtualItems().length > 0 &&
            virtualizer.getVirtualItems()[0].start > 0 && (
              <Table.Tr>
                <Table.Td
                  colSpan={9}
                  style={{
                    height: virtualizer.getVirtualItems()[0].start,
                    padding: 0,
                  }}
                />
              </Table.Tr>
            )}
          {virtualizer.getVirtualItems().map((virtualRow) => (
            <Table.Tr
              key={games[virtualRow.index].gameId}
              data-index={virtualRow.index}
              ref={virtualizer.measureElement}
            >
              <Table.Td>
                <Text size="sm">
                  {new Date(
                    games[virtualRow.index].gameDate
                  ).toLocaleDateString('en-US', {
                    month: 'short',
                    day: 'numeric',
                  })}
                </Text>
              </Table.Td>
              <Table.Td>
                <Text size="sm">{games[virtualRow.index].opponentAbbrev}</Text>
              </Table.Td>
              <Table.Td style={{ textAlign: 'right' }}>
                {games[virtualRow.index].goals}
              </Table.Td>
              <Table.Td style={{ textAlign: 'right' }}>
                {games[virtualRow.index].assists}
              </Table.Td>
              <Table.Td style={{ textAlign: 'right', fontWeight: 600 }}>
                {games[virtualRow.index].points}
              </Table.Td>
              <Table.Td style={{ textAlign: 'right' }}>
                {games[virtualRow.index].plusMinus > 0
                  ? `+${games[virtualRow.index].plusMinus}`
                  : games[virtualRow.index].plusMinus}
              </Table.Td>
              <Table.Td style={{ textAlign: 'right' }}>
                {games[virtualRow.index].pim}
              </Table.Td>
              <Table.Td style={{ textAlign: 'right' }}>
                {games[virtualRow.index].shots}
              </Table.Td>
              <Table.Td style={{ textAlign: 'right' }}>
                {games[virtualRow.index].toi}
              </Table.Td>
            </Table.Tr>
          ))}
          {virtualizer.getVirtualItems().length > 0 && (
            <Table.Tr>
              <Table.Td
                colSpan={9}
                style={{
                  height:
                    virtualizer.getTotalSize() -
                    virtualizer.getVirtualItems()[
                      virtualizer.getVirtualItems().length - 1
                    ].end,
                  padding: 0,
                }}
              />
            </Table.Tr>
          )}
        </Table.Tbody>
      </Table>
    </div>
  );
}

interface SeasonTotalsProps {
  games: Array<{
    goals: number;
    assists: number;
    points: number;
    plusMinus: number;
    pim: number;
    shots: number;
  }>;
}

function SeasonTotals({ games }: SeasonTotalsProps) {
  const totals = games.reduce(
    (acc, g) => ({
      goals: acc.goals + g.goals,
      assists: acc.assists + g.assists,
      points: acc.points + g.points,
      plusMinus: acc.plusMinus + g.plusMinus,
      pim: acc.pim + g.pim,
      shots: acc.shots + g.shots,
    }),
    { goals: 0, assists: 0, points: 0, plusMinus: 0, pim: 0, shots: 0 }
  );

  return (
    <Group gap="lg">
      <StatBadge label="G" value={totals.goals} />
      <StatBadge label="A" value={totals.assists} />
      <StatBadge label="Pts" value={totals.points} />
      <StatBadge label="+/-" value={totals.plusMinus} />
      <StatBadge label="PIM" value={totals.pim} />
      <StatBadge label="SOG" value={totals.shots} />
      <StatBadge label="GP" value={games.length} />
    </Group>
  );
}

function StatBadge({ label, value }: { label: string; value: number }) {
  return (
    <Stack gap={0} align="center">
      <Text size="lg" fw={700}>
        {value}
      </Text>
      <Text size="xs" c="dimmed">
        {label}
      </Text>
    </Stack>
  );
}

function buildStatsFromGameLog(
  games: Array<{
    goals: number;
    assists: number;
    points: number;
  }>
): Record<string, number> {
  const totals = games.reduce(
    (acc, g) => ({
      goals: acc.goals + g.goals,
      assists: acc.assists + g.assists,
      points: acc.points + g.points,
    }),
    { goals: 0, assists: 0, points: 0 }
  );
  return { ...totals, gamesPlayed: games.length };
}
