-- Add standings breakdown columns to league_members
-- Enables the standings page to display player/goalie point breakdown and round-by-round points

ALTER TABLE public.league_members
  ADD COLUMN IF NOT EXISTS player_points INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS goalie_points INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS round_points JSONB DEFAULT '{}'::jsonb;

-- Refresh league standings by aggregating roster points_earned into league_members
-- Called after sync-nhl-stats updates roster points
CREATE OR REPLACE FUNCTION public.refresh_league_standings(p_league_id UUID, p_round INTEGER)
RETURNS VOID AS $$
BEGIN
  UPDATE public.league_members lm
  SET
    player_points = sub.player_pts,
    goalie_points = sub.goalie_pts,
    total_points = sub.player_pts + sub.goalie_pts,
    round_points = COALESCE(lm.round_points, '{}'::jsonb)
      || jsonb_build_object(p_round::text, sub.player_pts + sub.goalie_pts)
  FROM (
    SELECT
      r.league_member_id,
      COALESCE(SUM(r.points_earned) FILTER (WHERE r.player_id IS NOT NULL), 0) AS player_pts,
      COALESCE(SUM(r.points_earned) FILTER (WHERE r.team_id IS NOT NULL AND r.player_id IS NULL), 0) AS goalie_pts
    FROM public.rosters r
    WHERE r.round = p_round
      AND r.is_active = TRUE
      AND r.league_member_id IN (
        SELECT id FROM public.league_members WHERE league_id = p_league_id
      )
    GROUP BY r.league_member_id
  ) sub
  WHERE lm.id = sub.league_member_id
    AND lm.league_id = p_league_id;
END;
$$ LANGUAGE plpgsql;
