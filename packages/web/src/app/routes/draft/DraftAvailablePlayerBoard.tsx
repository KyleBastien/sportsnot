import { Stack, Text } from '@mantine/core';
import { useIsMobile } from '@sportsnot/ui';
import { DraftAvailableSkaterSection } from './DraftAvailableSkaterSection';
import { DraftAvailableTeamSection } from './DraftAvailableTeamSection';
import {
  buildSkaterRows,
  buildTeamRows,
  filterSkaterRows,
  filterTeamRows,
} from './draftAvailablePlayerBoardUtils';
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
  cumulativePlayerStats: PlayerStatRow[];
  teamStats: TeamStatRow[];
  cumulativeTeamStats: TeamStatRow[];
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

export function DraftAvailablePlayerBoard({
  playerStats,
  cumulativePlayerStats,
  teamStats,
  cumulativeTeamStats,
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
  const filteredSkaters = filterSkaterRows({
    skaterRows: buildSkaterRows({
      playerStats,
      cumulativePlayerStats,
      regSeasonStats,
      draftedPlayerIds,
      isRound1,
    }),
    positionFilter,
    searchQuery,
    isRound1,
  });
  const filteredTeams = filterTeamRows({
    teamRows: buildTeamRows({
      teamStats,
      cumulativeTeamStats,
      draftedTeamIds,
    }),
    positionFilter,
    searchQuery,
  });

  return (
    <Stack gap="md">
      {positionFilter !== 'G' && (
        <>
          <Text fw={600} size="sm">
            Skaters ({filteredSkaters.length} available)
          </Text>
          <DraftAvailableSkaterSection
            players={filteredSkaters}
            comparePlayers={comparePlayers}
            onToggleCompare={onToggleCompare}
            onSelectPlayer={onSelectPlayer}
            canPick={canPick}
            isMobile={isMobile}
            isRound1={isRound1}
            mySlotCounts={mySlotCounts}
            roster={roster}
          />
        </>
      )}

      {(positionFilter === 'ALL' || positionFilter === 'G') && (
        <>
          <Text fw={600} size="sm">
            Teams / Goaltending ({filteredTeams.length} available)
          </Text>
          <DraftAvailableTeamSection
            teams={filteredTeams}
            canPick={canPick}
            mySlotCounts={mySlotCounts}
            roster={roster}
            onSelectPlayer={onSelectPlayer}
          />
        </>
      )}
    </Stack>
  );
}
