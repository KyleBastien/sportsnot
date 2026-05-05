import {
  Badge,
  Button,
  Card,
  Group,
  ScrollArea,
  Stack,
  Table,
  Text,
} from '@mantine/core';
import { MobileCardList, useIsMobile } from '@sportsnot/ui';
import { isDraftPositionFull, MAX_COMPARE } from './draftPageHelpers';
import type {
  ComparePlayer,
  DraftablePlayer,
  DraftRosterComposition,
  MySlotCounts,
  PlayerStatRow,
  RegSeasonStatRow,
  TeamStatRow,
} from './draftPageTypes';

interface AvailablePlayerBoardProps {
  playerStats: PlayerStatRow[];
  teamStats: TeamStatRow[];
  draftedPlayerIds: Set<number>;
  draftedTeamIds: Set<number>;
  positionFilter: string;
  searchQuery: string;
  canPick: boolean;
  onSelectPlayer: (player: DraftablePlayer) => void;
  comparePlayers: ComparePlayer[];
  onToggleCompare: (player: ComparePlayer) => void;
  isRound1: boolean;
  regSeasonStats: RegSeasonStatRow[];
  mySlotCounts: MySlotCounts;
  roster: DraftRosterComposition;
}

function buildComparePlayer(player: {
  id: number;
  fullName: string;
  position: string;
  team: string;
  goals: number;
  assists: number;
  points: number;
}): ComparePlayer {
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

export function DraftAvailablePlayerBoard({
  playerStats,
  teamStats,
  draftedPlayerIds,
  draftedTeamIds,
  positionFilter,
  searchQuery,
  canPick,
  onSelectPlayer,
  comparePlayers,
  onToggleCompare,
  isRound1,
  regSeasonStats,
  mySlotCounts,
  roster,
}: AvailablePlayerBoardProps) {
  const isMobile = useIsMobile();
  const query = searchQuery.toLowerCase();

  const regSeasonMap = new Map(
    regSeasonStats.map((row) => [row.player_id, row])
  );

  const useRegSeasonFallback =
    isRound1 &&
    (playerStats.length === 0 ||
      playerStats.every((player) => (player.games_played ?? 0) === 0));

  const skaterRows = useRegSeasonFallback
    ? regSeasonStats
        .filter((player) => player.position === 'F' || player.position === 'D')
        .filter((player) => !draftedPlayerIds.has(player.player_id))
        .map((player) => ({
          id: player.player_id,
          fullName: player.player_name ?? `Player #${player.player_id}`,
          firstName: '',
          lastName: '',
          position: player.position ?? 'F',
          team: player.team_abbreviation ?? 'NHL',
          teamId: 0,
          goals: player.goals ?? 0,
          assists: player.assists ?? 0,
          points: player.points ?? 0,
          gamesPlayed: player.games_played ?? 0,
          regSeasonPts: player.points ?? 0,
        }))
    : playerStats
        .filter((player) => !draftedPlayerIds.has(player.player_id))
        .filter((player) => !player.is_injured)
        .map((player) => {
          const regSeason = regSeasonMap.get(player.player_id);
          return {
            id: player.player_id,
            fullName:
              player.player_name ??
              regSeason?.player_name ??
              `Player #${player.player_id}`,
            firstName: '',
            lastName: '',
            position: player.position ?? regSeason?.position ?? 'F',
            team:
              player.team_abbreviation ?? regSeason?.team_abbreviation ?? 'NHL',
            teamId: 0,
            goals: player.goals ?? 0,
            assists: player.assists ?? 0,
            points: (player.goals ?? 0) + (player.assists ?? 0),
            gamesPlayed: player.games_played ?? 0,
            regSeasonPts: regSeason?.points ?? 0,
          };
        });

  const teamRows = teamStats
    .filter((team) => !draftedTeamIds.has(team.team_id))
    .filter((team) => !team.is_eliminated)
    .map((team) => ({
      id: team.team_id,
      fullName: team.team_name ?? `Team #${team.team_id}`,
      firstName: '',
      lastName: '',
      position: 'G' as const,
      team: team.team_abbreviation ?? `Team #${team.team_id}`,
      teamId: team.team_id,
      wins: team.wins ?? 0,
      shutouts: team.shutouts ?? 0,
    }));

  const filteredSkaters = skaterRows
    .filter((player) => {
      if (
        positionFilter !== 'ALL' &&
        positionFilter !== 'F' &&
        positionFilter !== 'D'
      ) {
        return false;
      }

      if (positionFilter === 'F' && player.position !== 'F') {
        return false;
      }

      if (positionFilter === 'D' && player.position !== 'D') {
        return false;
      }

      if (query && !player.fullName.toLowerCase().includes(query)) {
        return false;
      }

      return true;
    })
    .sort((left, right) =>
      isRound1
        ? right.regSeasonPts - left.regSeasonPts || right.points - left.points
        : right.points - left.points || right.goals - left.goals
    );

  const filteredTeams = teamRows
    .filter((team) => {
      if (positionFilter !== 'ALL' && positionFilter !== 'G') {
        return false;
      }

      if (query && !team.fullName.toLowerCase().includes(query)) {
        return false;
      }

      return true;
    })
    .sort((left, right) => right.wins - left.wins);

  const showSkaters = positionFilter !== 'G';
  const showTeams = positionFilter === 'ALL' || positionFilter === 'G';

  return (
    <Stack gap="md">
      {showSkaters && (
        <>
          <Text fw={600} size="sm">
            Skaters ({filteredSkaters.length} available)
          </Text>
          {isMobile ? (
            <ScrollArea h={300}>
              <MobileCardList emptyMessage="No available skaters match your filters">
                {filteredSkaters.map((player) => {
                  const isCompared = comparePlayers.some(
                    (entry) => entry.id === player.id
                  );
                  const compareFull = comparePlayers.length >= MAX_COMPARE;

                  return (
                    <Card key={player.id} padding="sm" radius="sm" withBorder>
                      <Group justify="space-between" mb={4}>
                        <Group gap="xs">
                          <Text fw={500} size="sm">
                            {player.fullName}
                          </Text>
                          <Badge size="xs" variant="light">
                            {player.position}
                          </Badge>
                        </Group>
                        <Text
                          size="sm"
                          fw={600}
                          style={{ fontVariantNumeric: 'tabular-nums' }}
                        >
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
                      <Group gap="xs">
                        <Button
                          size="xs"
                          variant={isCompared ? 'filled' : 'outline'}
                          color={isCompared ? 'blue' : 'gray'}
                          disabled={!isCompared && compareFull}
                          onClick={() =>
                            onToggleCompare(buildComparePlayer(player))
                          }
                        >
                          {isCompared ? 'Compared' : 'Compare'}
                        </Button>
                        {canPick && (
                          <Button
                            size="xs"
                            variant="light"
                            disabled={isDraftPositionFull(
                              player.position,
                              mySlotCounts,
                              roster
                            )}
                            onClick={() =>
                              onSelectPlayer({
                                id: player.id,
                                fullName: player.fullName,
                                firstName: player.firstName,
                                lastName: player.lastName,
                                position: player.position,
                                team: player.team,
                                teamId: player.teamId,
                              })
                            }
                          >
                            Draft
                          </Button>
                        )}
                      </Group>
                    </Card>
                  );
                })}
              </MobileCardList>
            </ScrollArea>
          ) : (
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
                    {filteredSkaters.map((player) => {
                      const isCompared = comparePlayers.some(
                        (entry) => entry.id === player.id
                      );
                      const compareFull = comparePlayers.length >= MAX_COMPARE;

                      return (
                        <Table.Tr key={player.id}>
                          <Table.Td>{player.fullName}</Table.Td>
                          <Table.Td>
                            <Badge size="xs" variant="light">
                              {player.position}
                            </Badge>
                          </Table.Td>
                          {isRound1 && (
                            <Table.Td
                              style={{
                                textAlign: 'right',
                                fontWeight: 600,
                              }}
                            >
                              {player.regSeasonPts}
                            </Table.Td>
                          )}
                          <Table.Td style={{ textAlign: 'right' }}>
                            {player.goals}
                          </Table.Td>
                          <Table.Td style={{ textAlign: 'right' }}>
                            {player.assists}
                          </Table.Td>
                          <Table.Td
                            style={{
                              textAlign: 'right',
                              fontWeight: 600,
                            }}
                          >
                            {player.points}
                          </Table.Td>
                          <Table.Td style={{ textAlign: 'right' }}>
                            {player.gamesPlayed}
                          </Table.Td>
                          <Table.Td>
                            <Button
                              size="xs"
                              variant={isCompared ? 'filled' : 'outline'}
                              color={isCompared ? 'blue' : 'gray'}
                              disabled={!isCompared && compareFull}
                              onClick={() =>
                                onToggleCompare(buildComparePlayer(player))
                              }
                            >
                              {isCompared ? 'Compared' : 'Compare'}
                            </Button>
                          </Table.Td>
                          {canPick && (
                            <Table.Td>
                              <Button
                                size="xs"
                                variant="light"
                                disabled={isDraftPositionFull(
                                  player.position,
                                  mySlotCounts,
                                  roster
                                )}
                                onClick={() =>
                                  onSelectPlayer({
                                    id: player.id,
                                    fullName: player.fullName,
                                    firstName: player.firstName,
                                    lastName: player.lastName,
                                    position: player.position,
                                    team: player.team,
                                    teamId: player.teamId,
                                  })
                                }
                              >
                                Draft
                              </Button>
                            </Table.Td>
                          )}
                        </Table.Tr>
                      );
                    })}
                    {filteredSkaters.length === 0 && (
                      <Table.Tr>
                        <Table.Td
                          colSpan={(isRound1 ? 8 : 7) + (canPick ? 1 : 0)}
                        >
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
          )}
        </>
      )}

      {showTeams && (
        <>
          <Text fw={600} size="sm">
            Teams / Goaltending ({filteredTeams.length} available)
          </Text>
          <Table striped highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Team</Table.Th>
                <Table.Th style={{ textAlign: 'right' }}>Wins</Table.Th>
                <Table.Th style={{ textAlign: 'right' }}>Shutouts</Table.Th>
                {canPick && <Table.Th />}
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {filteredTeams.map((team) => (
                <Table.Tr key={team.teamId}>
                  <Table.Td>{team.fullName}</Table.Td>
                  <Table.Td style={{ textAlign: 'right' }}>
                    {team.wins}
                  </Table.Td>
                  <Table.Td style={{ textAlign: 'right' }}>
                    {team.shutouts}
                  </Table.Td>
                  {canPick && (
                    <Table.Td>
                      <Button
                        size="xs"
                        variant="light"
                        disabled={isDraftPositionFull(
                          'G',
                          mySlotCounts,
                          roster
                        )}
                        onClick={() =>
                          onSelectPlayer({
                            id: team.teamId,
                            fullName: team.fullName,
                            firstName: '',
                            lastName: '',
                            position: 'G',
                            team: team.team,
                            teamId: team.teamId,
                          })
                        }
                      >
                        Draft
                      </Button>
                    </Table.Td>
                  )}
                </Table.Tr>
              ))}
              {filteredTeams.length === 0 && (
                <Table.Tr>
                  <Table.Td colSpan={canPick ? 4 : 3}>
                    <Text c="dimmed" ta="center" size="sm">
                      No available teams match your filters
                    </Text>
                  </Table.Td>
                </Table.Tr>
              )}
            </Table.Tbody>
          </Table>
        </>
      )}
    </Stack>
  );
}
