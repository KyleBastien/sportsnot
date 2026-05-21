import {
  Alert,
  Card,
  Center,
  Container,
  Loader,
  Stack,
  Text,
  Title,
} from '@mantine/core';
import { ScrollArea, Table, Button } from '@mantine/core';
import { useIsMobile } from '@sportsnot/ui';
import { resolvePickName } from '@sportsnot/utils';
import {
  DraftAvailablePlayersCard,
  DraftCompareTray,
  DraftConfirmPickModal,
  DraftFilterControls,
  DraftHistoryCard,
  DraftMyTeamCard,
  DraftRoomHeader,
} from './DraftPageSections';
import type { Position } from '@sportsnot/types';
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

interface DraftPageCompleteViewProps {
  draftOrder: string[];
  picks: DraftPickRow[];
  playerNameMap: Map<number, string>;
  teamNameMap: Map<number, string>;
  onBackToLeague: () => void;
}

interface DraftPageViewProps {
  draft: DraftStateRow;
  currentPicker: DraftMemberRow | undefined;
  isMyTurn: boolean;
  isCommissioner: boolean;
  canPick: boolean;
  positionFilter: string;
  onPositionFilterChange: (value: string) => void;
  searchQuery: string;
  onSearchQueryChange: (value: string) => void;
  picks: DraftPickRow[];
  playerNameMap: Map<number, string>;
  teamNameMap: Map<number, string>;
  playerTeamAbbreviationMap: Map<number, string>;
  teamAbbreviationMap: Map<number, string>;
  myTeamOpened: boolean;
  onToggleMyTeam: () => void;
  myRosterSlots: MyRosterGroup[];
  playerStats: PlayerStatRow[];
  cumulativePlayerStats: PlayerStatRow[];
  teamStats: TeamStatRow[];
  cumulativeTeamStats: TeamStatRow[];
  isDraftPoolSyncing: boolean;
  onSelectPlayer: (player: DraftablePlayer) => void;
  comparePlayers: ComparePlayer[];
  onToggleCompare: (player: ComparePlayer) => void;
  onRemoveCompare: (playerId: number) => void;
  onClearCompare: () => void;
  isRound1: boolean;
  mySlotCounts: MySlotCounts;
  regSeasonStats: RegSeasonStatRow[];
  roster: DraftRosterComposition;
  confirmPlayer: DraftablePlayer | null;
  onCloseConfirm: () => void;
  pickError: string | null;
  confirmPosition: Position;
  onConfirmPositionChange: (value: Position) => void;
  allowIrSlots: boolean;
  submitting: boolean;
  onConfirmPick: () => void;
  draftedPlayerIds: Set<number>;
  draftedTeamIds: Set<number>;
}

export function DraftPageLoadingState() {
  return (
    <Center h="50vh">
      <Loader size="lg" />
    </Center>
  );
}

export function DraftPageNoDraftState() {
  return (
    <Container size="md" py="xl">
      <Alert color="navy" title="No Active Draft">
        No draft has been started for this league yet.
      </Alert>
    </Container>
  );
}

export function DraftPageCompleteView({
  draftOrder,
  picks,
  playerNameMap,
  teamNameMap,
  onBackToLeague,
}: DraftPageCompleteViewProps) {
  const isMobile = useIsMobile();

  return (
    <Container size="md" py="xl">
      <Stack gap="lg" align="center">
        <Title order={2}>Draft Complete</Title>
        <Text c="dimmed">
          All {draftOrder.length} picks have been made. The draft is complete!
        </Text>
        <CardHistoryTable
          picks={picks}
          playerNameMap={playerNameMap}
          teamNameMap={teamNameMap}
          isMobile={isMobile}
        />
        <Button variant="filled" size="md" onClick={onBackToLeague}>
          Back to League
        </Button>
      </Stack>
    </Container>
  );
}

export function DraftPageView(props: DraftPageViewProps) {
  return (
    <Container size="xl" py="xl">
      <Stack gap="xl">
        <DraftRoomHeader
          draft={props.draft}
          currentPicker={props.currentPicker}
          isMyTurn={props.isMyTurn}
          isCommissioner={props.isCommissioner}
        />
        <DraftFilterControls
          positionFilter={props.positionFilter}
          onPositionFilterChange={props.onPositionFilterChange}
          searchQuery={props.searchQuery}
          onSearchQueryChange={props.onSearchQueryChange}
        />
        <DraftHistoryCard
          picks={props.picks}
          playerNameMap={props.playerNameMap}
          teamNameMap={props.teamNameMap}
        />
        <DraftMyTeamCard
          myTeamOpened={props.myTeamOpened}
          onToggleMyTeam={props.onToggleMyTeam}
          myRosterSlots={props.myRosterSlots}
          playerNameMap={props.playerNameMap}
          teamNameMap={props.teamNameMap}
          playerTeamAbbreviationMap={props.playerTeamAbbreviationMap}
          teamAbbreviationMap={props.teamAbbreviationMap}
        />
        <DraftAvailablePlayersCard
          playerStats={props.playerStats}
          cumulativePlayerStats={props.cumulativePlayerStats}
          teamStats={props.teamStats}
          cumulativeTeamStats={props.cumulativeTeamStats}
          isDraftPoolSyncing={props.isDraftPoolSyncing}
          canPick={props.canPick}
          currentPicker={props.currentPicker}
          draftedPlayerIds={props.draftedPlayerIds}
          draftedTeamIds={props.draftedTeamIds}
          positionFilter={props.positionFilter}
          searchQuery={props.searchQuery}
          onSelectPlayer={props.onSelectPlayer}
          comparePlayers={props.comparePlayers}
          onToggleCompare={props.onToggleCompare}
          isRound1={props.isRound1}
          mySlotCounts={props.mySlotCounts}
          regSeasonStats={props.regSeasonStats}
          roster={props.roster}
        />
        <DraftCompareTray
          comparePlayers={props.comparePlayers}
          onClearCompare={props.onClearCompare}
          onRemoveCompare={props.onRemoveCompare}
        />
        <DraftConfirmPickModal
          confirmPlayer={props.confirmPlayer}
          onCloseConfirm={props.onCloseConfirm}
          pickError={props.pickError}
          confirmPosition={props.confirmPosition}
          onConfirmPositionChange={props.onConfirmPositionChange}
          mySlotCounts={props.mySlotCounts}
          roster={props.roster}
          allowIrSlots={props.allowIrSlots}
          onConfirmPick={props.onConfirmPick}
          submitting={props.submitting}
        />
      </Stack>
    </Container>
  );
}

function CardHistoryTable({
  picks,
  playerNameMap,
  teamNameMap,
  isMobile,
}: {
  picks: DraftPickRow[];
  playerNameMap: Map<number, string>;
  teamNameMap: Map<number, string>;
  isMobile: boolean;
}) {
  return (
    <Card shadow="sm" padding="lg" radius="md" withBorder w="100%">
      <Title order={4} mb="sm">
        Draft History
      </Title>
      <ScrollArea h={400}>
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Pick</Table.Th>
              <Table.Th>Team</Table.Th>
              <Table.Th>Player</Table.Th>
              {!isMobile && <Table.Th>Position</Table.Th>}
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {picks.map((pick) => (
              <Table.Tr key={pick.id}>
                <Table.Td>{pick.pick_number}</Table.Td>
                <Table.Td>
                  {pick.league_members?.team_name ?? 'Unknown'}
                </Table.Td>
                <Table.Td>
                  {resolvePickName(
                    pick.player_id,
                    pick.team_id,
                    playerNameMap,
                    teamNameMap
                  )}
                </Table.Td>
                {!isMobile && <Table.Td>{pick.position}</Table.Td>}
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </ScrollArea>
    </Card>
  );
}
