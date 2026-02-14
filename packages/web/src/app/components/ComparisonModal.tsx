import {
  Modal,
  Group,
  Stack,
  Text,
  Avatar,
  Badge,
  Table,
  ScrollArea,
} from '@mantine/core';
import { useMediaQuery } from '@mantine/hooks';
import { useCompareContext, type ComparePlayer } from '../context/CompareContext';

interface ComparisonModalProps {
  opened: boolean;
  onClose: () => void;
}

interface StatDef {
  key: string;
  label: string;
  format?: (value: number) => string; // eslint-disable-line no-unused-vars
  higherIsBetter?: boolean;
}

const SKATER_STATS: StatDef[] = [
  { key: 'goals', label: 'Goals' },
  { key: 'assists', label: 'Assists' },
  { key: 'points', label: 'Points' },
  { key: 'gamesPlayed', label: 'GP' },
  { key: 'plusMinus', label: '+/-' },
  {
    key: 'pointsPerGame',
    label: 'Pts/GP',
    format: (v: number) => v.toFixed(2),
  },
];

const GOALIE_STATS: StatDef[] = [
  { key: 'wins', label: 'Wins' },
  { key: 'shutouts', label: 'Shutouts' },
  { key: 'gaa', label: 'GAA', format: (v: number) => v.toFixed(2), higherIsBetter: false },
  {
    key: 'savePercentage',
    label: 'SV%',
    format: (v: number) => v.toFixed(3),
  },
  { key: 'gamesPlayed', label: 'GP' },
];

function isGoalie(player: ComparePlayer): boolean {
  return player.position === 'G';
}

function getStatDefs(players: ComparePlayer[]): StatDef[] {
  const hasGoalie = players.some(isGoalie);
  const hasSkater = players.some((p) => !isGoalie(p));

  if (hasGoalie && !hasSkater) return GOALIE_STATS;
  if (hasSkater && !hasGoalie) return SKATER_STATS;
  // Mixed: show both sets
  return [...SKATER_STATS, ...GOALIE_STATS];
}

function getStatValue(player: ComparePlayer, key: string): number | null {
  if (key === 'pointsPerGame') {
    const gp = player.stats['gamesPlayed'] ?? 0;
    const pts = player.stats['points'] ?? 0;
    return gp > 0 ? pts / gp : 0;
  }
  return player.stats[key] ?? null;
}

function findBestIndex(
  values: (number | null)[],
  higherIsBetter: boolean
): number | null {
  let bestIdx: number | null = null;
  let bestVal: number | null = null;
  for (let i = 0; i < values.length; i++) {
    const v = values[i];
    if (v === null) continue;
    if (
      bestVal === null ||
      (higherIsBetter ? v > bestVal : v < bestVal)
    ) {
      bestVal = v;
      bestIdx = i;
    }
  }
  // Only highlight if more than one non-null value
  const nonNull = values.filter((v) => v !== null);
  if (nonNull.length < 2) return null;
  return bestIdx;
}

export function ComparisonModal({ opened, onClose }: ComparisonModalProps) {
  const { players, draftedPlayerIds, draftedTeamIds } = useCompareContext();
  const isMobile = useMediaQuery('(max-width: 48em)');

  const statDefs = getStatDefs(players);

  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title="Player Comparison"
      fullScreen={!!isMobile}
      size="xl"
    >
      <ScrollArea>
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Stat</Table.Th>
              {players.map((player) => {
                const isDrafted =
                  (player.position === 'G'
                    ? draftedTeamIds?.has(player.playerId)
                    : draftedPlayerIds?.has(player.playerId)) ?? false;
                return (
                <Table.Th key={player.playerId} style={{ textAlign: 'center' }}>
                  <Stack align="center" gap={4}>
                    <Avatar
                      src={player.headshot}
                      alt={player.name}
                      size="md"
                      radius="xl"
                    />
                    <Text size="sm" fw={500} c={isDrafted ? 'dimmed' : undefined}>
                      {player.name}
                    </Text>
                    <Group gap={4} justify="center">
                      <Text size="xs" c="dimmed">
                        {player.teamAbbrev}
                      </Text>
                      <Badge size="xs" variant="light">
                        {player.position}
                      </Badge>
                    </Group>
                    {isDrafted && (
                      <Badge size="xs" variant="light" color="red">
                        Drafted
                      </Badge>
                    )}
                    {player.stats['fantasyPoints'] != null && (
                      <Badge size="sm" variant="filled" color="green">
                        {player.stats['fantasyPoints']} pts
                      </Badge>
                    )}
                  </Stack>
                </Table.Th>
                );
              })}
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {statDefs.map((stat) => {
              const values = players.map((p) => getStatValue(p, stat.key));
              const higherIsBetter = stat.higherIsBetter !== false;
              const bestIdx = findBestIndex(values, higherIsBetter);

              return (
                <Table.Tr key={stat.key}>
                  <Table.Td>
                    <Text size="sm" fw={500}>
                      {stat.label}
                    </Text>
                  </Table.Td>
                  {values.map((val, idx) => {
                    const isBest = bestIdx === idx;
                    const formatted =
                      val === null
                        ? '—'
                        : stat.format
                          ? stat.format(val)
                          : String(val);

                    return (
                      <Table.Td
                        key={players[idx].playerId}
                        style={{ textAlign: 'center' }}
                      >
                        <Text
                          size="sm"
                          fw={isBest ? 700 : 400}
                          c={isBest ? 'blue' : undefined}
                        >
                          {formatted}
                        </Text>
                      </Table.Td>
                    );
                  })}
                </Table.Tr>
              );
            })}
          </Table.Tbody>
        </Table>
      </ScrollArea>
    </Modal>
  );
}
