import type { NHLPlayoffSeries } from '@sportsnot/types';

export const bracket: NHLPlayoffSeries[] = [
  {
    seriesCode: 'A',
    round: 1,
    topSeedTeam: { id: 13, name: 'Florida Panthers', abbreviation: 'FLA' },
    bottomSeedTeam: {
      id: 12,
      name: 'Carolina Hurricanes',
      abbreviation: 'CAR',
    },
    topSeedWins: 4,
    bottomSeedWins: 2,
    matchupTeams: {
      topSeed: {
        team: { id: 13, name: 'Florida Panthers' },
        seriesRecord: { wins: 4, losses: 2 },
      },
      bottomSeed: {
        team: { id: 12, name: 'Carolina Hurricanes' },
        seriesRecord: { wins: 2, losses: 4 },
      },
    },
    isComplete: true,
    seriesWinner: { id: 13, name: 'Florida Panthers' },
  },
  {
    seriesCode: 'H',
    round: 1,
    topSeedTeam: { id: 22, name: 'Edmonton Oilers', abbreviation: 'EDM' },
    bottomSeedTeam: { id: 25, name: 'Dallas Stars', abbreviation: 'DAL' },
    topSeedWins: 4,
    bottomSeedWins: 3,
    matchupTeams: {
      topSeed: {
        team: { id: 22, name: 'Edmonton Oilers' },
        seriesRecord: { wins: 4, losses: 3 },
      },
      bottomSeed: {
        team: { id: 25, name: 'Dallas Stars' },
        seriesRecord: { wins: 3, losses: 4 },
      },
    },
    isComplete: true,
    seriesWinner: { id: 22, name: 'Edmonton Oilers' },
  },
] as const;
