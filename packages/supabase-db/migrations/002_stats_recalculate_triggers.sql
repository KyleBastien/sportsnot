-- Migration: Auto-recalculate roster and member points when stats change
-- Scoring rules: goal=1, assist=1, win=2, shutout=4 (shutout replaces win points)

-- ============================================================================
-- FUNCTION: Recalculate points for player stat changes
-- ============================================================================

CREATE OR REPLACE FUNCTION public.recalculate_player_points()
RETURNS TRIGGER AS $$
DECLARE
  r RECORD;
  new_points INTEGER;
BEGIN
  -- Calculate points: goal=1, assist=1
  new_points := COALESCE(NEW.goals, 0) + COALESCE(NEW.assists, 0);

  -- Update all active roster slots referencing this player
  FOR r IN
    SELECT ros.id, ros.league_member_id
    FROM public.rosters ros
    WHERE ros.player_id = NEW.player_id
      AND ros.is_active = TRUE
  LOOP
    UPDATE public.rosters
    SET points_earned = new_points
    WHERE id = r.id;

    -- Recalculate league_members.total_points by summing active roster slot points
    UPDATE public.league_members
    SET total_points = (
      SELECT COALESCE(SUM(points_earned), 0)
      FROM public.rosters
      WHERE league_member_id = r.league_member_id
        AND is_active = TRUE
    )
    WHERE id = r.league_member_id;
  END LOOP;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- FUNCTION: Recalculate points for team stat changes
-- ============================================================================

CREATE OR REPLACE FUNCTION public.recalculate_team_points()
RETURNS TRIGGER AS $$
DECLARE
  r RECORD;
  new_points INTEGER;
BEGIN
  -- Scoring: win=2, shutout=4 (shutout replaces win points, not additive)
  -- A shutout is also a win, so: (wins - shutouts) * 2 + shutouts * 4
  new_points := (COALESCE(NEW.wins, 0) - COALESCE(NEW.shutouts, 0)) * 2
              + COALESCE(NEW.shutouts, 0) * 4;

  -- Update all active roster slots referencing this team
  FOR r IN
    SELECT ros.id, ros.league_member_id
    FROM public.rosters ros
    WHERE ros.team_id = NEW.team_id
      AND ros.is_active = TRUE
  LOOP
    UPDATE public.rosters
    SET points_earned = new_points
    WHERE id = r.id;

    -- Recalculate league_members.total_points by summing active roster slot points
    UPDATE public.league_members
    SET total_points = (
      SELECT COALESCE(SUM(points_earned), 0)
      FROM public.rosters
      WHERE league_member_id = r.league_member_id
        AND is_active = TRUE
    )
    WHERE id = r.league_member_id;
  END LOOP;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- TRIGGERS
-- ============================================================================

-- INSERT trigger fires for all new rows
CREATE TRIGGER trg_recalculate_player_points_insert
  AFTER INSERT ON public.player_stats_cache
  FOR EACH ROW
  EXECUTE FUNCTION public.recalculate_player_points();

-- UPDATE trigger fires only when row data actually changed
CREATE TRIGGER trg_recalculate_player_points_update
  AFTER UPDATE ON public.player_stats_cache
  FOR EACH ROW
  WHEN (OLD.* IS DISTINCT FROM NEW.*)
  EXECUTE FUNCTION public.recalculate_player_points();

-- INSERT trigger fires for all new rows
CREATE TRIGGER trg_recalculate_team_points_insert
  AFTER INSERT ON public.team_stats_cache
  FOR EACH ROW
  EXECUTE FUNCTION public.recalculate_team_points();

-- UPDATE trigger fires only when row data actually changed
CREATE TRIGGER trg_recalculate_team_points_update
  AFTER UPDATE ON public.team_stats_cache
  FOR EACH ROW
  WHEN (OLD.* IS DISTINCT FROM NEW.*)
  EXECUTE FUNCTION public.recalculate_team_points();
