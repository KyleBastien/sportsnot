import type { NHLGame } from '@sportsnot/types';

export const gamesScf: NHLGame[] = [
  {
    id: 2024030411,
    gameType: '3',
    season: '20242025',
    gameDate: '2025-05-31',
    startTimeUTC: '2025-06-01T00:00:00Z',
    homeTeam: {
      id: 22,
      name: 'Edmonton Oilers',
      abbreviation: 'EDM',
      score: 3,
    },
    awayTeam: {
      id: 13,
      name: 'Florida Panthers',
      abbreviation: 'FLA',
      score: 2,
    },
    gameState: 'FINAL',
  },
  {
    id: 2024030412,
    gameType: '3',
    season: '20242025',
    gameDate: '2025-06-02',
    startTimeUTC: '2025-06-03T00:00:00Z',
    homeTeam: {
      id: 22,
      name: 'Edmonton Oilers',
      abbreviation: 'EDM',
      score: 1,
    },
    awayTeam: {
      id: 13,
      name: 'Florida Panthers',
      abbreviation: 'FLA',
      score: 4,
    },
    gameState: 'FINAL',
  },
] as const;
