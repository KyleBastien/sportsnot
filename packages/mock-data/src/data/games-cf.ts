import type { NHLGame } from '@sportsnot/types';

export const gamesCf: NHLGame[] = [
  {
    id: 2024030311,
    gameType: '3',
    season: '20242025',
    gameDate: '2025-05-17',
    startTimeUTC: '2025-05-17T23:00:00Z',
    homeTeam: {
      id: 13,
      name: 'Florida Panthers',
      abbreviation: 'FLA',
      score: 2,
    },
    awayTeam: {
      id: 22,
      name: 'Edmonton Oilers',
      abbreviation: 'EDM',
      score: 3,
    },
    gameState: 'FINAL',
  },
  {
    id: 2024030312,
    gameType: '3',
    season: '20242025',
    gameDate: '2025-05-19',
    startTimeUTC: '2025-05-19T23:00:00Z',
    homeTeam: {
      id: 13,
      name: 'Florida Panthers',
      abbreviation: 'FLA',
      score: 4,
    },
    awayTeam: {
      id: 22,
      name: 'Edmonton Oilers',
      abbreviation: 'EDM',
      score: 1,
    },
    gameState: 'FINAL',
  },
] as const;
