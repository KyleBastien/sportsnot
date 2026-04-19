-- Fix: Exclude IR slots (IR_F, IR_D) from standings and point calculations.
-- IR players should not count toward team totals until activated.

-- 1. Fix refresh_league_standings to exclude IR positions
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
      AND r.position NOT IN ('IR_F', 'IR_D')
      AND r.league_member_id IN (
        SELECT id FROM public.league_members WHERE league_id = p_league_id
      )
    GROUP BY r.league_member_id
  ) sub
  WHERE lm.id = sub.league_member_id
    AND lm.league_id = p_league_id;
END;
$$ LANGUAGE plpgsql;

-- 2. Fix calculate_member_points to exclude IR positions
CREATE OR REPLACE FUNCTION public.calculate_member_points(p_member_id UUID, p_round INTEGER)
RETURNS INTEGER AS $$
DECLARE
  total INTEGER := 0;
BEGIN
  SELECT COALESCE(SUM(points_earned), 0) INTO total
  FROM public.rosters
  WHERE league_member_id = p_member_id
    AND round = p_round
    AND is_active = TRUE
    AND position NOT IN ('IR_F', 'IR_D');
  RETURN total;
END;
$$ LANGUAGE plpgsql;
