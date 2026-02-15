import type { NHLGame } from '@sportsnot/types';

export const gamesR2: NHLGame[] = [
  {
    id: 2024030211,
    gameType: '3',
    season: '20242025',
    gameDate: '2025-05-03',
    startTimeUTC: '2025-05-03T23:00:00Z',
    homeTeam: {
      id: 13,
      name: 'Florida Panthers',
      abbreviation: 'FLA',
      score: 3,
    },
    awayTeam: {
      id: 12,
      name: 'Carolina Hurricanes',
      abbreviation: 'CAR',
      score: 1,
    },
    gameState: 'FINAL',
  },
  {
    id: 2024030212,
    gameType: '3',
    season: '20242025',
    gameDate: '2025-05-05',
    startTimeUTC: '2025-05-05T23:00:00Z',
    homeTeam: {
      id: 13,
      name: 'Florida Panthers',
      abbreviation: 'FLA',
      score: 4,
    },
    awayTeam: {
      id: 12,
      name: 'Carolina Hurricanes',
      abbreviation: 'CAR',
      score: 2,
    },
    gameState: 'FINAL',
  },
] as const;
