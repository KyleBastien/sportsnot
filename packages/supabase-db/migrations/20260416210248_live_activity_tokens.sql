-- Live Activity push tokens
-- Stores APNs push-to-start and per-activity tokens registered by the iOS
-- app so the push-live-activity-updates edge function can fan out updates.

CREATE TABLE public.live_activity_tokens (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  league_id UUID REFERENCES public.leagues(id) ON DELETE CASCADE NOT NULL,
  -- Hashed APNs token (sha256 hex). We never store the plaintext token.
  token_hash TEXT NOT NULL,
  -- Plaintext token, encrypted-at-rest by Postgres TDE. Required for APNs
  -- push; treated as sensitive data (never selected by anon).
  token TEXT NOT NULL,
  platform TEXT NOT NULL DEFAULT 'ios' CHECK (platform IN ('ios')),
  -- 'activity' = an individual Live Activity push token
  -- 'start'    = push-to-start token (starts a new Live Activity from push)
  kind TEXT NOT NULL CHECK (kind IN ('activity', 'start')),
  -- APNs bundle identifier the token was issued for (sanity check).
  bundle_id TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  expires_at TIMESTAMPTZ,
  UNIQUE(league_id, token_hash)
);

CREATE INDEX idx_live_activity_tokens_league
  ON public.live_activity_tokens(league_id);

CREATE INDEX idx_live_activity_tokens_expires
  ON public.live_activity_tokens(expires_at);

ALTER TABLE public.live_activity_tokens ENABLE ROW LEVEL SECURITY;

-- No anon or authenticated SELECT: tokens are only read by the service role
-- (the push-live-activity-updates edge function). Anon can INSERT via the
-- register-live-activity-token edge function, which uses the service role
-- internally, so no anon INSERT policy is needed here either.

CREATE POLICY "Commissioners can see their league's token counts"
  ON public.live_activity_tokens FOR SELECT
  TO authenticated
  USING (
    league_id IN (
      SELECT id FROM public.leagues WHERE commissioner_id = auth.uid()
    )
  );
