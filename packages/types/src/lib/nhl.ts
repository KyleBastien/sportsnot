// NHL API types
export interface NHLPlayer {
  id: number;
  fullName: string;
  firstName: string;
  lastName: string;
  primaryNumber?: string;
  birthDate: string;
  currentAge: number;
  nationality: string;
  height: string;
  weight: number;
  shootsCatches: 'L' | 'R';
  primaryPosition: {
    code: string;
    name: string;
    type: string;
    abbreviation: string;
  };
  currentTeam?: {
    id: number;
    name: string;
    abbreviation: string;
  };
  headshot?: string;
}

export interface NHLTeam {
  id: number;
  name: string;
  abbreviation: string;
  teamName: string;
  locationName: string;
  division: {
    id: number;
    name: string;
  };
  conference: {
    id: number;
    name: string;
  };
  logo?: string;
}

export interface NHLGame {
  id: number;
  gameType: string;
  season: string;
  gameDate: string;
  startTimeUTC: string;
  homeTeam: {
    id: number;
    name: string;
    abbreviation: string;
    score?: number;
  };
  awayTeam: {
    id: number;
    name: string;
    abbreviation: string;
    score?: number;
  };
  gameState: 'FUT' | 'PRE' | 'LIVE' | 'FINAL' | 'OFF';
  period?: number;
  periodTimeRemaining?: string;
}

export interface NHLPlayoffSeries {
  seriesCode: string;
  round: number;
  topSeedTeam?: {
    id: number;
    name: string;
    abbreviation?: string;
  };
  bottomSeedTeam?: {
    id: number;
    name: string;
    abbreviation?: string;
  };
  topSeedWins?: number;
  bottomSeedWins?: number;
  matchupTeams?: {
    topSeed: {
      team: { id: number; name: string };
      seriesRecord: { wins: number; losses: number };
    };
    bottomSeed: {
      team: { id: number; name: string };
      seriesRecord: { wins: number; losses: number };
    };
  };
  isComplete: boolean;
  seriesWinner?: {
    id: number;
    name: string;
  };
}

export interface NHLPlayerGameStats {
  playerId: number;
  gameId: number;
  goals: number;
  assists: number;
  points: number;
  plusMinus: number;
  penaltyMinutes: number;
  shots: number;
  timeOnIce: string;
}

export interface NHLGoalieGameStats {
  playerId: number;
  gameId: number;
  decision?: 'W' | 'L' | 'O';
  shotsAgainst: number;
  goalsAgainst: number;
  saves: number;
  savePercentage: number;
  shutout: boolean;
  timeOnIce: string;
}

export interface NHLPlayerStats {
  gameId: number;
  gameDate: string;
  teamAbbrev: string;
  homeRoadFlag?: string;
  opponentAbbrev: string;
  commonName?: { default: string; fr?: string };
  opponentCommonName?: { default: string; fr?: string };
  goals: number;
  assists: number;
  points?: number;
  plusMinus?: number;
  pim: number;
  shots?: number;
  shifts?: number;
  toi: string;
  powerPlayGoals?: number;
  powerPlayPoints?: number;
  shorthandedGoals?: number;
  shorthandedPoints?: number;
  gameWinningGoals?: number;
  otGoals?: number;
  gamesStarted?: number;
  decision?: string;
  shotsAgainst?: number;
  goalsAgainst?: number;
  savePctg?: number;
  shutouts?: number;
}
