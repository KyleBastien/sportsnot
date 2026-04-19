-- Allow the anon role to read regular_season_stats_cache so the
-- widget-league-snapshot edge function can fall back to it for
-- player names when player_stats_cache.player_name is NULL.
CREATE POLICY "Anon can read regular season stats for widget"
  ON regular_season_stats_cache
  FOR SELECT
  TO anon
  USING (true);
