export interface RosterSlotRow {
  id: string;
  league_member_id: string;
  round: number;
  player_id: number | null;
  team_id: number | null;
  position: string;
  is_active: boolean;
  points_earned: number;
  activated_from_ir: boolean;
  is_eliminated?: boolean;
}

export interface LeagueMemberRow {
  id: string;
  user_id: string;
  team_name: string;
  users?: { display_name?: string } | null;
}

export interface RosterGroup {
  position: string;
  label: string;
  players: RosterSlotRow[];
}

export interface RosterMemberOption {
  value: string;
  label: string;
}

export interface IrModalState {
  irSlotId: string;
  candidates: RosterSlotRow[];
}
