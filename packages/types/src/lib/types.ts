// User types
export interface User {
  id: string;
  email: string;
  displayName: string;
  avatarUrl?: string;
  createdAt: string;
  updatedAt: string;
}

// League types
export type LeagueStatus = 'setup' | 'drafting' | 'active' | 'completed';

export interface League {
  id: string;
  name: string;
  commissionerId: string;
  inviteCode: string;
  maxParticipants: number;
  currentRound: number;
  status: LeagueStatus;
  allowIrSlots: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface LeagueMember {
  id: string;
  leagueId: string;
  userId: string;
  teamName: string;
  totalPoints: number;
  joinedAt: string;
  user?: User;
}

// Draft types
export type DraftStatus = 'pending' | 'active' | 'completed';
export type Position = 'F' | 'D' | 'G' | 'IR_F' | 'IR_D';

export interface Draft {
  id: string;
  leagueId: string;
  round: number;
  status: DraftStatus;
  currentPick: number;
  draftOrder: string[]; // Array of user IDs
  startedAt?: string;
  completedAt?: string;
}

export interface DraftPick {
  id: string;
  draftId: string;
  leagueMemberId: string;
  pickNumber: number;
  playerId?: number; // NHL API player ID
  teamId?: number; // NHL API team ID (for goalie picks)
  position: Position;
  pickedAt: string;
}

// Roster types
export interface RosterSlot {
  id: string;
  leagueMemberId: string;
  round: number;
  playerId?: number;
  teamId?: number;
  position: Position;
  isActive: boolean;
  pointsEarned: number;
  activatedFromIr: boolean;
}

// Scoring
export interface PlayerStats {
  playerId: number;
  nhlSeason: string;
  playoffRound: number;
  playerName?: string;
  teamAbbreviation?: string;
  position?: 'F' | 'D';
  goals: number;
  assists: number;
  gamesPlayed: number;
  isInjured: boolean;
  lastUpdated: string;
}

export interface TeamStats {
  teamId: number;
  nhlSeason: string;
  playoffRound: number;
  teamName?: string;
  teamAbbreviation?: string;
  wins: number;
  shutouts: number;
  isEliminated: boolean;
  lastUpdated: string;
}

// Roster composition constants
export const ROSTER_COMPOSITION = {
  forwards: 5,
  defensemen: 3,
  goalies: 1,
  irForwards: 1,
  irDefensemen: 1,
} as const;

/**
 * Returns roster composition based on whether IR slots are enabled.
 * When IR is disabled, irForwards and irDefensemen are set to 0.
 */
export function getRosterComposition(allowIrSlots: boolean) {
  return {
    forwards: ROSTER_COMPOSITION.forwards,
    defensemen: ROSTER_COMPOSITION.defensemen,
    goalies: ROSTER_COMPOSITION.goalies,
    irForwards: allowIrSlots ? ROSTER_COMPOSITION.irForwards : 0,
    irDefensemen: allowIrSlots ? ROSTER_COMPOSITION.irDefensemen : 0,
  };
}

// Scoring constants
export const SCORING = {
  goal: 1,
  assist: 1,
  win: 2,
  shutout: 4, // replaces win points
} as const;
