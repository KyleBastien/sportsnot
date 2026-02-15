import type { NHLGame } from '@sportsnot/types';

export const gamesR1: NHLGame[] = [
  {
    id: 2024030111,
    gameType: '3',
    season: '20242025',
    gameDate: '2025-04-19',
    startTimeUTC: '2025-04-19T23:00:00Z',
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
  {
    id: 2024030112,
    gameType: '3',
    season: '20242025',
    gameDate: '2025-04-21',
    startTimeUTC: '2025-04-21T23:00:00Z',
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
      score: 5,
    },
    gameState: 'FINAL',
  },
  {
    id: 2024030181,
    gameType: '3',
    season: '20242025',
    gameDate: '2025-04-19',
    startTimeUTC: '2025-04-20T02:00:00Z',
    homeTeam: {
      id: 22,
      name: 'Edmonton Oilers',
      abbreviation: 'EDM',
      score: 5,
    },
    awayTeam: { id: 25, name: 'Dallas Stars', abbreviation: 'DAL', score: 3 },
    gameState: 'FINAL',
  },
  {
    id: 2024030182,
    gameType: '3',
    season: '20242025',
    gameDate: '2025-04-21',
    startTimeUTC: '2025-04-22T02:00:00Z',
    homeTeam: {
      id: 22,
      name: 'Edmonton Oilers',
      abbreviation: 'EDM',
      score: 2,
    },
    awayTeam: { id: 25, name: 'Dallas Stars', abbreviation: 'DAL', score: 4 },
    gameState: 'FINAL',
  },
] as const;
