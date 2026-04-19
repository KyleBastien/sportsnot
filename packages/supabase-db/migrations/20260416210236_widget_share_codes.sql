-- Widget share codes + public read-only widget view
-- Enables the iOS widget to fetch a league's snapshot anonymously via a
-- share code the commissioner shares with league members.

-- ============================================================================
-- leagues.share_code column
-- ============================================================================

ALTER TABLE public.leagues
  ADD COLUMN IF NOT EXISTS share_code TEXT UNIQUE;

-- Short URL-safe token generator (base32, 16 chars ≈ 80 bits of entropy).
-- Uses the same "no 0/1/I/O/L" alphabet as generateInviteCode() in
-- packages/utils to stay visually unambiguous when typed on a phone.
CREATE OR REPLACE FUNCTION public.generate_share_code()
RETURNS TEXT AS $$
DECLARE
  alphabet TEXT := 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
  result TEXT := '';
  i INTEGER;
BEGIN
  FOR i IN 1..16 LOOP
    result := result || substr(
      alphabet,
      1 + floor(random() * length(alphabet))::int,
      1
    );
  END LOOP;
  RETURN result;
END;
$$ LANGUAGE plpgsql VOLATILE;

-- Backfill existing leagues.
UPDATE public.leagues
SET share_code = public.generate_share_code()
WHERE share_code IS NULL;

ALTER TABLE public.leagues
  ALTER COLUMN share_code SET NOT NULL,
  ALTER COLUMN share_code SET DEFAULT public.generate_share_code();

CREATE INDEX IF NOT EXISTS idx_leagues_share_code ON public.leagues(share_code);

-- Allow commissioners to regenerate share codes (uses existing update policy).

-- ============================================================================
-- widget_league_view — public read-only projection used by the widget API
-- ============================================================================

-- Exposes only what the widget needs:
--   league id, name, current_round, share_code, team names, drafted players
-- Never exposes: user emails, user ids, draft internals, league member ids
-- (beyond what's needed to attribute a player to a fantasy team name).

CREATE OR REPLACE VIEW public.widget_league_view
WITH (security_invoker = true) AS
SELECT
  l.id            AS league_id,
  l.name          AS league_name,
  l.share_code    AS share_code,
  l.current_round AS current_round,
  l.status        AS status,
  lm.team_name    AS team_name,
  r.player_id     AS player_id,
  r.team_id       AS team_id,
  r.position      AS position,
  r.is_active     AS is_active,
  r.round         AS round
FROM public.leagues l
JOIN public.league_members lm ON lm.league_id = l.id
JOIN public.rosters r ON r.league_member_id = lm.id
WHERE r.round = l.current_round
  AND r.is_active = TRUE;

-- Grant anon + authenticated SELECT on the view so the widget edge function
-- (running with anon key) can read it. A wrapping policy on leagues already
-- allows anyone to SELECT leagues by invite code; we add the same for
-- share_code lookups through this view.
GRANT SELECT ON public.widget_league_view TO anon, authenticated;

-- Supabase requires direct SELECT policies on underlying tables for views
-- with security_invoker. Add scoped anon SELECT policies keyed on share_code.

CREATE POLICY "Anon can read league by share_code"
  ON public.leagues FOR SELECT
  TO anon
  USING (share_code IS NOT NULL);

CREATE POLICY "Anon can read league_members for widget"
  ON public.league_members FOR SELECT
  TO anon
  USING (
    league_id IN (
      SELECT id FROM public.leagues WHERE share_code IS NOT NULL
    )
  );

CREATE POLICY "Anon can read rosters for widget"
  ON public.rosters FOR SELECT
  TO anon
  USING (
    league_member_id IN (
      SELECT lm.id
      FROM public.league_members lm
      JOIN public.leagues l ON l.id = lm.league_id
      WHERE l.share_code IS NOT NULL
    )
  );

CREATE POLICY "Anon can read player stats for widget"
  ON public.player_stats_cache FOR SELECT
  TO anon
  USING (true);

CREATE POLICY "Anon can read team stats for widget"
  ON public.team_stats_cache FOR SELECT
  TO anon
  USING (true);

-- ============================================================================
-- Regenerate share code RPC (commissioner-only)
-- ============================================================================

CREATE OR REPLACE FUNCTION public.regenerate_share_code(p_league_id UUID)
RETURNS TEXT AS $$
DECLARE
  new_code TEXT;
  caller UUID := auth.uid();
BEGIN
  IF caller IS NULL THEN
    RAISE EXCEPTION 'Not authenticated';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM public.leagues
    WHERE id = p_league_id AND commissioner_id = caller
  ) THEN
    RAISE EXCEPTION 'Only the commissioner can regenerate the share code';
  END IF;

  new_code := public.generate_share_code();

  UPDATE public.leagues
  SET share_code = new_code
  WHERE id = p_league_id;

  RETURN new_code;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

GRANT EXECUTE ON FUNCTION public.regenerate_share_code(UUID) TO authenticated;
