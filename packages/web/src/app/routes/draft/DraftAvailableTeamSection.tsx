import { Button, Table, Text } from '@mantine/core';
import { isDraftPositionFull } from './draftPageHelpers';
import { DraftTeamRow } from './draftAvailablePlayerBoardUtils';
import type { DraftRosterComposition, MySlotCounts } from './draftPageTypes';

interface DraftAvailableTeamSectionProps {
  teams: DraftTeamRow[];
  canPick: boolean;
  mySlotCounts: MySlotCounts;
  roster: DraftRosterComposition;
  onSelectPlayer: (player: {
    id: number;
    fullName: string;
    firstName: string;
    lastName: string;
    position: 'G';
    team: string;
    teamId: number;
  }) => void;
}

export function DraftAvailableTeamSection({
  teams,
  canPick,
  mySlotCounts,
  roster,
  onSelectPlayer,
}: DraftAvailableTeamSectionProps) {
  return (
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
        {teams.map((team) => (
          <Table.Tr key={team.teamId}>
            <Table.Td>{team.fullName}</Table.Td>
            <Table.Td style={{ textAlign: 'right' }}>{team.wins}</Table.Td>
            <Table.Td style={{ textAlign: 'right' }}>{team.shutouts}</Table.Td>
            {canPick && (
              <Table.Td>
                <Button
                  size="xs"
                  variant="light"
                  disabled={isDraftPositionFull('G', mySlotCounts, roster)}
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
        {teams.length === 0 && (
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
  );
}
