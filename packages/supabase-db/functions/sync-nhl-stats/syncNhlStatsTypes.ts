export const NHL_API_BASE = 'https://api-web.nhle.com/v1';
export const DEFAULT_SEASON = '20252026';
export const FINAL_GAME_STATES = new Set(['OFF', 'FINAL']);
export const LIVE_GAME_STATES = new Set(['LIVE', 'CRIT']);

export interface PlayerGameLog {
  gameId: number;
  goals: number;
  assists: number;
}

export interface BoxscorePlayer {
  playerId: number;
  goals?: number;
  assists?: number;
}

export interface BoxscoreTeamStats {
  forwards?: BoxscorePlayer[];
  defense?: BoxscorePlayer[];
  goalies?: BoxscorePlayer[];
}

export interface SeriesStatus {
  round?: number;
}

export interface NhlScoreGameLite {
  id: number;
  gameType: number;
  gameState: string;
  gameDate?: string;
  homeTeam?: { id?: number; abbrev?: string; score?: number };
  awayTeam?: { id?: number; abbrev?: string; score?: number };
  seriesStatus?: SeriesStatus | null;
}

export interface ScoreboardResponse {
  games?: NhlScoreGameLite[];
}

export interface BracketTeam {
  id: number;
  abbrev: string;
  name?: { default?: string };
}

export interface BracketSeries {
  playoffRound: number;
  topSeedTeam?: BracketTeam;
  bottomSeedTeam?: BracketTeam;
}

export interface BracketResponse {
  series?: BracketSeries[];
}

export interface TeamRosterPlayer {
  id: number;
  firstName: { default: string };
  lastName: { default: string };
}

export interface TeamRosterResponse {
  forwards?: TeamRosterPlayer[];
  defensemen?: TeamRosterPlayer[];
}

export interface EligibleTeam {
  id: number;
  abbrev: string;
  name: string;
}

export interface EligiblePlayer {
  id: number;
  playerName: string;
  position: 'F' | 'D';
  teamId: number;
  teamAbbrev: string;
}

export interface LeagueRow {
  id: string;
  current_round: number | null;
  status: string;
}

export interface RosterRow {
  league_member_id: string;
  player_id: number | null;
  team_id: number | null;
}

export interface PlayerStatsRow {
  player_id: number;
  goals: number;
  assists: number;
}

export interface TeamStatsRow {
  team_id: number;
  wins: number;
  shutouts: number;
}

export interface LiveDelta {
  goals: number;
  assists: number;
  teamAbbrev: string | null;
}
