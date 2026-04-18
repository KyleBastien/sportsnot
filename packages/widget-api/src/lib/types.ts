// Shared payload types for the iOS widget + widget-api client.
// These are the on-the-wire shapes returned by the
// widget-league-snapshot edge function. Keep in sync with
// packages/supabase-db/functions/widget-league-snapshot/index.ts and the
// SportsNotWidgetShared Swift package in ios/.

export type WidgetGameState =
  | 'FUT' // future / not started
  | 'PRE' // pregame
  | 'LIVE'
  | 'FINAL'
  | 'OFF';

export interface WidgetGame {
  id: number;
  startsAt: string; // ISO8601
  state: WidgetGameState;
  homeTeamId: number;
  homeTeamAbbrev: string;
  homeTeamName: string;
  homeScore: number;
  awayTeamId: number;
  awayTeamAbbrev: string;
  awayTeamName: string;
  awayScore: number;
  period: number | null;
  timeRemaining: string | null;
  /** True if at least one drafted player in the featured league is in this game. */
  hasDraftedPlayers: boolean;
}

export type WidgetPosition = 'F' | 'D' | 'G' | 'IR_F' | 'IR_D';

export interface WidgetDraftedPlayer {
  playerId: number | null;
  /** Present when this slot is a team/goalie slot instead of a skater. */
  teamId: number | null;
  name: string;
  teamAbbrev: string;
  position: WidgetPosition;
  /** The id of the scheduled game today the player is in, or null if off-day. */
  gameId: number | null;
  fantasyPoints: number;
  /** Fantasy team name that drafted this player. */
  ownedByTeamName: string;
}

export interface WidgetSnapshot {
  league: {
    id: string;
    name: string;
    shareCode: string;
    currentRound: number;
    status: 'setup' | 'drafting' | 'active' | 'completed';
  };
  date: string; // YYYY-MM-DD (league timezone, default UTC)
  generatedAt: string; // ISO8601
  games: WidgetGame[];
  players: WidgetDraftedPlayer[];
}

export interface RegisterLiveActivityTokenRequest {
  shareCode: string;
  token: string;
  kind: 'activity' | 'start';
  bundleId: string;
  expiresAt?: string;
}
