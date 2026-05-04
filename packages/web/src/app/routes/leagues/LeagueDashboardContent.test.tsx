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
  it('shows cumulative round columns and total points on desktop', () => {
    renderStandingsCard({ currentRound: 3, isMobile: false });

    expect(screen.getByRole('columnheader', { name: 'Round 1' })).toBeTruthy();
    expect(screen.getByRole('columnheader', { name: 'Round 2' })).toBeTruthy();
    expect(screen.getByRole('columnheader', { name: 'Round 3' })).toBeTruthy();
    expect(screen.queryByRole('columnheader', { name: 'Round 4' })).toBeNull();
    expect(
      screen.getByRole('columnheader', { name: 'Total Points' })
    ).toBeTruthy();

    expect(getRowCellTexts('Ice Dominators')).toEqual([
      '1',
      'Ice Dominators',
      'Alice',
      '10',
      '20',
      '30',
      '60',
    ]);
    expect(getRowCellTexts('Puck Dynasty')).toEqual([
      '2',
      'Puck Dynasty',
      'Bob',
      '35',
      '0',
      '0',
      '35',
    ]);
  });

  it('shows only total points during round 1', () => {
    renderStandingsCard({ currentRound: 1, isMobile: false });

    expect(screen.queryByRole('columnheader', { name: 'Round 1' })).toBeNull();
    expect(
      screen.getByRole('columnheader', { name: 'Total Points' })
    ).toBeTruthy();
    expect(getRowCellTexts('Ice Dominators')).toEqual([
      '1',
      'Ice Dominators',
      'Alice',
      '60',
    ]);
  });

  it('shows only current round plus total points on mobile', () => {
    renderStandingsCard({ currentRound: 3, isMobile: true });

    expect(screen.queryByRole('columnheader', { name: 'Manager' })).toBeNull();
    expect(screen.queryByRole('columnheader', { name: 'Round 1' })).toBeNull();
    expect(screen.queryByRole('columnheader', { name: 'Round 2' })).toBeNull();
    expect(screen.getByRole('columnheader', { name: 'Round 3' })).toBeTruthy();
    expect(
      screen.getByRole('columnheader', { name: 'Total Points' })
    ).toBeTruthy();

    expect(getRowCellTexts('Ice Dominators')).toEqual([
      '1',
      'Ice Dominators',
      '30',
      '60',
    ]);
    expect(getRowCellTexts('Puck Dynasty')).toEqual([
      '2',
      'Puck Dynasty',
      '0',
      '35',
    ]);
  });
});
