import type { Position } from '@sportsnot/types';

export type DraftRosterPosition = 'F' | 'D' | 'G' | 'IR_F' | 'IR_D';

export interface DraftablePlayer {
  id: number;
  fullName: string;
  firstName: string;
  lastName: string;
  position: string;
  team: string;
  teamId: number;
  headshot?: string;
}

export interface DraftMemberRow {
  id: string;
  user_id: string;
  team_name: string;
  total_points: number;
  users?: { display_name?: string } | null;
}

export interface DraftPickRow {
  id: string;
  pick_number: number;
  player_id: number | null;
  team_id: number | null;
  position: string;
  league_members?: { team_name: string; user_id: string } | null;
}

export interface DraftStateRow {
  id: string;
  league_id: string;
  round: number;
  status: string;
  current_pick: number;
  draft_order: string[];
  draft_picks: DraftPickRow[];
  completed_at?: string | null;
}

export interface PlayerStatRow {
  player_id: number;
  player_name: string;
  position: string;
  team_abbreviation: string;
  is_injured: boolean;
  goals: number;
  assists: number;
  games_played: number;
}

export interface TeamStatRow {
  team_id: number;
  team_name: string;
  team_abbreviation: string;
  is_eliminated: boolean;
  wins: number;
  shutouts: number;
}

export interface ComparePlayer {
  id: number;
  fullName: string;
  position: string;
  team: string;
  goals: number;
  assists: number;
  points: number;
}

export interface RegSeasonStatRow {
  player_id: number;
  player_name: string;
  team_abbreviation: string;
  position: string;
  goals: number;
  assists: number;
  points: number;
  games_played: number;
}

export interface DraftRosterComposition {
  forwards: number;
  defensemen: number;
  goalies: number;
  irForwards: number;
  irDefensemen: number;
}

export type MySlotCounts = Record<DraftRosterPosition, number>;

export interface MyRosterGroup {
  position: DraftRosterPosition;
  label: string;
  filled: DraftPickRow[];
  emptyCount: number;
}

export interface DraftConfirmPositionOption {
  label: string;
  value: Position;
  disabled?: boolean;
}
