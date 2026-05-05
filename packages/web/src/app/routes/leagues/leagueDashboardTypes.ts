export interface LeagueMemberRow {
  id: string;
  user_id: string;
  team_name: string;
  total_points: number;
  users?: { display_name?: string; avatar_url?: string } | null;
}
