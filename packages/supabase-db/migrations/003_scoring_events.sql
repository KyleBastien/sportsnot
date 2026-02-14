-- Migration: Create scoring_events table for tracking individual scoring events
-- Enables granular scoring history queries per league member

-- ============================================================================
-- TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.scoring_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  league_id UUID NOT NULL REFERENCES public.leagues(id) ON DELETE CASCADE,
  member_id UUID NOT NULL REFERENCES public.league_members(id) ON DELETE CASCADE,
  roster_id UUID NOT NULL REFERENCES public.rosters(id) ON DELETE CASCADE,
  player_id INTEGER,
  team_id INTEGER,
  event_type TEXT NOT NULL CHECK (event_type IN ('goal', 'assist', 'win', 'shutout')),
  points INTEGER NOT NULL,
  game_id INTEGER NOT NULL,
  game_date DATE NOT NULL,
  description TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- INDEXES
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_scoring_events_league_member_created
  ON public.scoring_events (league_id, member_id, created_at);

-- ============================================================================
-- UNIQUE CONSTRAINT (idempotency)
-- ============================================================================

ALTER TABLE public.scoring_events
  ADD CONSTRAINT uq_scoring_events_game_player_event
  UNIQUE (game_id, player_id, event_type);

-- ============================================================================
-- ROW LEVEL SECURITY
-- ============================================================================

ALTER TABLE public.scoring_events ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can read scoring events for their leagues"
  ON public.scoring_events FOR SELECT
  USING (
    league_id IN (
      SELECT league_id FROM public.league_members
      WHERE user_id = auth.uid()
    )
  );

-- ============================================================================
-- REALTIME
-- ============================================================================

ALTER PUBLICATION supabase_realtime ADD TABLE public.scoring_events;
