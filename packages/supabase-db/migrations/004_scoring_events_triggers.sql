-- Migration: Populate scoring_events from stat sync triggers
-- Extends recalculate_player_points and recalculate_team_points to insert
-- scoring_events records when stats change (delta-based).
-- Uses cumulative stat count as game_id for idempotency via unique constraint.
-- E.g., player's 4th goal -> game_id=4, event_type='goal' -> unique per player.

-- ============================================================================
-- Add unique index for team events (player_id IS NULL)
-- The existing constraint (game_id, player_id, event_type) doesn't cover NULLs
-- ============================================================================

CREATE UNIQUE INDEX IF NOT EXISTS uq_scoring_events_game_team_event
  ON public.scoring_events (game_id, team_id, event_type)
  WHERE player_id IS NULL;

-- ============================================================================
-- FUNCTION: Recalculate player points AND create scoring events
-- ============================================================================

CREATE OR REPLACE FUNCTION public.recalculate_player_points()
RETURNS TRIGGER AS $$
DECLARE
  r RECORD;
  new_points INTEGER;
  old_goals INTEGER;
  old_assists INTEGER;
  i INTEGER;
  v_league_id UUID;
BEGIN
  -- Calculate points: goal=1, assist=1
  new_points := COALESCE(NEW.goals, 0) + COALESCE(NEW.assists, 0);

  -- Determine old values (0 for INSERT since OLD is null)
  old_goals := CASE WHEN TG_OP = 'UPDATE' THEN COALESCE(OLD.goals, 0) ELSE 0 END;
  old_assists := CASE WHEN TG_OP = 'UPDATE' THEN COALESCE(OLD.assists, 0) ELSE 0 END;

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

    -- Get league_id for this member
    SELECT league_id INTO v_league_id
    FROM public.league_members
    WHERE id = r.league_member_id;

    -- Create scoring events for each new goal (idempotent via unique constraint)
    -- game_id = cumulative goal number (e.g., goal #4 -> game_id=4)
    FOR i IN (old_goals + 1)..COALESCE(NEW.goals, 0) LOOP
      INSERT INTO public.scoring_events (
        league_id, member_id, roster_id, player_id, event_type,
        points, game_id, game_date, description
      ) VALUES (
        v_league_id, r.league_member_id, r.id, NEW.player_id, 'goal',
        1, i, CURRENT_DATE,
        COALESCE(NEW.player_name, 'Player ' || NEW.player_id) || ' scored a goal'
      )
      ON CONFLICT (game_id, player_id, event_type) DO NOTHING;
    END LOOP;

    -- Create scoring events for each new assist
    -- game_id = cumulative assist number
    FOR i IN (old_assists + 1)..COALESCE(NEW.assists, 0) LOOP
      INSERT INTO public.scoring_events (
        league_id, member_id, roster_id, player_id, event_type,
        points, game_id, game_date, description
      ) VALUES (
        v_league_id, r.league_member_id, r.id, NEW.player_id, 'assist',
        1, i, CURRENT_DATE,
        COALESCE(NEW.player_name, 'Player ' || NEW.player_id) || ' recorded an assist'
      )
      ON CONFLICT (game_id, player_id, event_type) DO NOTHING;
    END LOOP;
  END LOOP;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- FUNCTION: Recalculate team points AND create scoring events
-- ============================================================================

CREATE OR REPLACE FUNCTION public.recalculate_team_points()
RETURNS TRIGGER AS $$
DECLARE
  r RECORD;
  new_points INTEGER;
  old_wins INTEGER;
  old_shutouts INTEGER;
  i INTEGER;
  v_league_id UUID;
BEGIN
  -- Scoring: win=2, shutout=4 (shutout replaces win points, not additive)
  -- A shutout is also a win, so: (wins - shutouts) * 2 + shutouts * 4
  new_points := (COALESCE(NEW.wins, 0) - COALESCE(NEW.shutouts, 0)) * 2
              + COALESCE(NEW.shutouts, 0) * 4;

  -- Determine old values (0 for INSERT since OLD is null)
  old_wins := CASE WHEN TG_OP = 'UPDATE' THEN COALESCE(OLD.wins, 0) ELSE 0 END;
  old_shutouts := CASE WHEN TG_OP = 'UPDATE' THEN COALESCE(OLD.shutouts, 0) ELSE 0 END;

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

    -- Get league_id for this member
    SELECT league_id INTO v_league_id
    FROM public.league_members
    WHERE id = r.league_member_id;

    -- Create scoring events for each new win (non-shutout wins)
    -- game_id = cumulative win number for idempotency
    -- Shutouts are also wins, so create 'win' events for non-shutout wins only
    FOR i IN (old_wins + 1)..COALESCE(NEW.wins, 0) LOOP
      -- Skip if this win number corresponds to a shutout
      -- Shutouts get their own event type with higher points
      IF i <= COALESCE(NEW.shutouts, 0) THEN
        CONTINUE;
      END IF;
      INSERT INTO public.scoring_events (
        league_id, member_id, roster_id, team_id, player_id, event_type,
        points, game_id, game_date, description
      ) VALUES (
        v_league_id, r.league_member_id, r.id, NEW.team_id, NULL, 'win',
        2, i, CURRENT_DATE,
        COALESCE(NEW.team_name, 'Team ' || NEW.team_id) || ' won'
      )
      ON CONFLICT DO NOTHING;
    END LOOP;

    -- Create scoring events for each new shutout
    -- game_id = cumulative shutout number
    FOR i IN (old_shutouts + 1)..COALESCE(NEW.shutouts, 0) LOOP
      INSERT INTO public.scoring_events (
        league_id, member_id, roster_id, team_id, player_id, event_type,
        points, game_id, game_date, description
      ) VALUES (
        v_league_id, r.league_member_id, r.id, NEW.team_id, NULL, 'shutout',
        4, i, CURRENT_DATE,
        COALESCE(NEW.team_name, 'Team ' || NEW.team_id) || ' recorded a shutout'
      )
      ON CONFLICT DO NOTHING;
    END LOOP;
  END LOOP;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
