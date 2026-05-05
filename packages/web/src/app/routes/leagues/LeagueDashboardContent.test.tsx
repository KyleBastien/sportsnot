import { afterEach, describe, expect, it } from '@rstest/core';
import { MantineProvider } from '@mantine/core';
import { cleanup, render, screen, within } from '@testing-library/react';
import type { ComponentProps } from 'react';
import { MemoryRouter } from 'react-router-dom';
import {
  getVisibleStandingsRounds,
  LeagueStandingsCard,
  type LeagueMemberRow,
} from './LeagueDashboardContent';

const members: LeagueMemberRow[] = [
  {
    id: 'member-1',
    user_id: 'user-1',
    team_name: 'Ice Dominators',
    total_points: 60,
    round_points: {
      1: 10,
      2: 20,
      3: 30,
      4: 0,
    },
    users: { display_name: 'Alice' },
  },
  {
    id: 'member-2',
    user_id: 'user-2',
    team_name: 'Puck Dynasty',
    total_points: 35,
    round_points: {
      1: 35,
    },
    users: { display_name: 'Bob' },
  },
];

function renderStandingsCard(
  overrides: Partial<ComponentProps<typeof LeagueStandingsCard>> = {}
) {
  render(
    <MantineProvider>
      <MemoryRouter>
        <LeagueStandingsCard
          currentRound={3}
          isMobile={false}
          leagueId="league-1"
          members={members}
          seasonComplete={false}
          userId="user-2"
          {...overrides}
        />
      </MemoryRouter>
    </MantineProvider>
  );
}

function getRowCellTexts(teamName: string): string[] {
  const row = screen.getByRole('link', { name: teamName }).closest('tr');

  if (!row) {
    throw new Error(`Could not find row for ${teamName}`);
  }

  return within(row)
    .getAllByRole('cell')
    .map((cell) => cell.textContent?.trim() ?? '');
}

function expectVisibleHeaders(headers: string[]) {
  headers.forEach((header) => {
    expect(screen.getByRole('columnheader', { name: header })).toBeTruthy();
  });
}

function expectHiddenHeaders(headers: string[]) {
  headers.forEach((header) => {
    expect(screen.queryByRole('columnheader', { name: header })).toBeNull();
  });
}

interface StandingsCardScenario {
  name: string;
  props: Partial<ComponentProps<typeof LeagueStandingsCard>>;
  visibleHeaders: string[];
  hiddenHeaders: string[];
  expectedRows: Record<string, string[]>;
}

const standingsCardScenarios: StandingsCardScenario[] = [
  {
    name: 'shows cumulative round columns and total points on desktop',
    props: { currentRound: 3, isMobile: false },
    visibleHeaders: [
      'Rank',
      'Team',
      'Manager',
      'Round 1',
      'Round 2',
      'Round 3',
      'Total Points',
    ],
    hiddenHeaders: ['Round 4'],
    expectedRows: {
      'Ice Dominators': [
        '1',
        'Ice Dominators',
        'Alice',
        '10',
        '20',
        '30',
        '60',
      ],
      'Puck Dynasty': ['2', 'Puck Dynasty', 'Bob', '35', '0', '0', '35'],
    },
  },
  {
    name: 'shows only total points during round 1',
    props: { currentRound: 1, isMobile: false },
    visibleHeaders: ['Rank', 'Team', 'Manager', 'Total Points'],
    hiddenHeaders: ['Round 1', 'Round 2', 'Round 3', 'Round 4'],
    expectedRows: {
      'Ice Dominators': ['1', 'Ice Dominators', 'Alice', '60'],
    },
  },
  {
    name: 'shows only current round plus total points on mobile',
    props: { currentRound: 3, isMobile: true },
    visibleHeaders: ['Rank', 'Team', 'Round 3', 'Total Points'],
    hiddenHeaders: ['Manager', 'Round 1', 'Round 2', 'Round 4'],
    expectedRows: {
      'Ice Dominators': ['1', 'Ice Dominators', '30', '60'],
      'Puck Dynasty': ['2', 'Puck Dynasty', '0', '35'],
    },
  },
];

afterEach(() => {
  cleanup();
});

describe('getVisibleStandingsRounds', () => {
  it('shows cumulative desktop rounds for rounds 2 through 4', () => {
    expect(getVisibleStandingsRounds(1, false)).toEqual([]);
    expect(getVisibleStandingsRounds(2, false)).toEqual([1, 2]);
    expect(getVisibleStandingsRounds(4, false)).toEqual([1, 2, 3, 4]);
  });

  it('shows only the current round on mobile after round 1', () => {
    expect(getVisibleStandingsRounds(1, true)).toEqual([]);
    expect(getVisibleStandingsRounds(2, true)).toEqual([2]);
    expect(getVisibleStandingsRounds(4, true)).toEqual([4]);
  });

  it('clamps out-of-range rounds to the playoff bounds', () => {
    expect(getVisibleStandingsRounds(0, false)).toEqual([]);
    expect(getVisibleStandingsRounds(8, false)).toEqual([1, 2, 3, 4]);
  });
});

describe('LeagueStandingsCard', () => {
  standingsCardScenarios.forEach((scenario) => {
    it(scenario.name, () => {
      renderStandingsCard(scenario.props);

      expectVisibleHeaders(scenario.visibleHeaders);
      expectHiddenHeaders(scenario.hiddenHeaders);

      Object.entries(scenario.expectedRows).forEach(
        ([teamName, expectedCells]) => {
          expect(getRowCellTexts(teamName)).toEqual(expectedCells);
        }
      );
    });
  });
});
