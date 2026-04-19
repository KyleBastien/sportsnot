-- Add regular_season_stats_cache table
-- Stores aggregated regular season stats for playoff-eligible players
-- Used by the DraftPage to show regular season performance during Round 1 draft

CREATE TABLE IF NOT EXISTS public.regular_season_stats_cache (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  player_id INTEGER NOT NULL,
  nhl_season TEXT NOT NULL,
  player_name TEXT,
  team_abbreviation TEXT,
  position TEXT CHECK (position IN ('F', 'D', 'G')),
  goals INTEGER DEFAULT 0,
  assists INTEGER DEFAULT 0,
  points INTEGER DEFAULT 0,
  games_played INTEGER DEFAULT 0,
  last_updated TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(player_id, nhl_season)
);

CREATE INDEX idx_regular_season_stats_player
  ON public.regular_season_stats_cache(player_id, nhl_season);

ALTER TABLE public.regular_season_stats_cache ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Authenticated users can read regular season stats"
  ON public.regular_season_stats_cache FOR SELECT
  USING (auth.role() = 'authenticated');
