-- Fix refresh_league_standings so total/player/goalie points stay
-- cumulative across rounds while round_points remains per-round.
CREATE OR REPLACE FUNCTION public.refresh_league_standings(
  p_league_id UUID,
  p_round INTEGER
)
RETURNS VOID AS $$
BEGIN
  WITH cumulative AS (
    SELECT
      member.id AS league_member_id,
      COALESCE(
        SUM(r.points_earned) FILTER (WHERE r.player_id IS NOT NULL),
        0
      ) AS player_pts,
      COALESCE(
        SUM(r.points_earned) FILTER (
          WHERE r.team_id IS NOT NULL
            AND r.player_id IS NULL
        ),
        0
      ) AS goalie_pts
    FROM public.league_members member
    LEFT JOIN public.rosters r
      ON r.league_member_id = member.id
      AND r.round <= p_round
      AND r.is_active = TRUE
      AND r.position NOT IN ('IR_F', 'IR_D')
    WHERE member.league_id = p_league_id
    GROUP BY member.id
  ), current_totals AS (
    SELECT
      member.id AS league_member_id,
      COALESCE(
        SUM(r.points_earned) FILTER (WHERE r.player_id IS NOT NULL),
        0
      ) AS player_pts,
      COALESCE(
        SUM(r.points_earned) FILTER (
          WHERE r.team_id IS NOT NULL
            AND r.player_id IS NULL
        ),
        0
      ) AS goalie_pts
    FROM public.league_members member
    LEFT JOIN public.rosters r
      ON r.league_member_id = member.id
      AND r.round = p_round
      AND r.is_active = TRUE
      AND r.position NOT IN ('IR_F', 'IR_D')
    WHERE member.league_id = p_league_id
    GROUP BY member.id
  )
  UPDATE public.league_members lm
  SET
    player_points = COALESCE(cumulative.player_pts, 0),
    goalie_points = COALESCE(cumulative.goalie_pts, 0),
    total_points = COALESCE(cumulative.player_pts, 0)
      + COALESCE(cumulative.goalie_pts, 0),
    round_points = COALESCE(lm.round_points, '{}'::jsonb)
      || jsonb_build_object(
        p_round::text,
        COALESCE(current_totals.player_pts, 0)
          + COALESCE(current_totals.goalie_pts, 0)
      )
  FROM cumulative
  JOIN current_totals
    ON current_totals.league_member_id = cumulative.league_member_id
  WHERE lm.id = cumulative.league_member_id
    AND lm.league_id = p_league_id;
END;
$$ LANGUAGE plpgsql;
