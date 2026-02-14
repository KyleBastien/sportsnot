-- SportsNot Initial Schema Migration
-- Creates all tables, functions, triggers, and RLS policies

-- ============================================================================
-- TABLES
-- ============================================================================

-- Users profile table (extends Supabase auth.users)
CREATE TABLE public.users (
  id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  email TEXT NOT NULL UNIQUE,
  display_name TEXT NOT NULL,
  avatar_url TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Leagues
CREATE TABLE public.leagues (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  commissioner_id UUID REFERENCES public.users(id) NOT NULL,
  invite_code TEXT UNIQUE NOT NULL,
  max_participants INTEGER DEFAULT 12 CHECK (max_participants BETWEEN 2 AND 12),
  current_round INTEGER DEFAULT 0,
  status TEXT DEFAULT 'setup' CHECK (status IN ('setup', 'drafting', 'active', 'completed')),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- League members (participants in a league)
CREATE TABLE public.league_members (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  league_id UUID REFERENCES public.leagues(id) ON DELETE CASCADE NOT NULL,
  user_id UUID REFERENCES public.users(id) ON DELETE CASCADE NOT NULL,
  team_name TEXT NOT NULL,
  total_points INTEGER DEFAULT 0,
  joined_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(league_id, user_id)
);

-- Drafts (one per league per round)
CREATE TABLE public.drafts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  league_id UUID REFERENCES public.leagues(id) ON DELETE CASCADE NOT NULL,
  round INTEGER NOT NULL,
  status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'active', 'completed')),
  current_pick INTEGER DEFAULT 1,
  draft_order JSONB NOT NULL DEFAULT '[]'::jsonb,
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  UNIQUE(league_id, round)
);

-- Draft picks
CREATE TABLE public.draft_picks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  draft_id UUID REFERENCES public.drafts(id) ON DELETE CASCADE NOT NULL,
  league_member_id UUID REFERENCES public.league_members(id) ON DELETE CASCADE NOT NULL,
  pick_number INTEGER NOT NULL,
  player_id INTEGER,
  team_id INTEGER,
  position TEXT NOT NULL CHECK (position IN ('F', 'D', 'G', 'IR_F', 'IR_D')),
  picked_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(draft_id, pick_number),
  UNIQUE(draft_id, player_id),
  UNIQUE(draft_id, team_id)
);

-- Rosters (current round active roster)
CREATE TABLE public.rosters (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  league_member_id UUID REFERENCES public.league_members(id) ON DELETE CASCADE NOT NULL,
  round INTEGER NOT NULL,
  player_id INTEGER,
  team_id INTEGER,
  position TEXT NOT NULL CHECK (position IN ('F', 'D', 'G', 'IR_F', 'IR_D')),
  is_active BOOLEAN DEFAULT TRUE,
  points_earned INTEGER DEFAULT 0,
  activated_from_ir BOOLEAN DEFAULT FALSE,
  UNIQUE(league_member_id, round, player_id),
  UNIQUE(league_member_id, round, team_id)
);

-- Player stats cache
CREATE TABLE public.player_stats_cache (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  player_id INTEGER NOT NULL,
  nhl_season TEXT NOT NULL,
  playoff_round INTEGER NOT NULL,
  player_name TEXT,
  team_abbreviation TEXT,
  position TEXT CHECK (position IN ('F', 'D')),
  goals INTEGER DEFAULT 0,
  assists INTEGER DEFAULT 0,
  games_played INTEGER DEFAULT 0,
  is_injured BOOLEAN DEFAULT FALSE,
  last_updated TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(player_id, nhl_season, playoff_round)
);

-- Team stats cache
CREATE TABLE public.team_stats_cache (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  team_id INTEGER NOT NULL,
  nhl_season TEXT NOT NULL,
  playoff_round INTEGER NOT NULL,
  team_name TEXT,
  team_abbreviation TEXT,
  wins INTEGER DEFAULT 0,
  shutouts INTEGER DEFAULT 0,
  is_eliminated BOOLEAN DEFAULT FALSE,
  last_updated TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(team_id, nhl_season, playoff_round)
);

-- ============================================================================
-- INDEXES
-- ============================================================================

CREATE INDEX idx_leagues_commissioner ON public.leagues(commissioner_id);
CREATE INDEX idx_leagues_invite_code ON public.leagues(invite_code);
CREATE INDEX idx_league_members_league ON public.league_members(league_id);
CREATE INDEX idx_league_members_user ON public.league_members(user_id);
CREATE INDEX idx_drafts_league ON public.drafts(league_id);
CREATE INDEX idx_draft_picks_draft ON public.draft_picks(draft_id);
CREATE INDEX idx_draft_picks_member ON public.draft_picks(league_member_id);
CREATE INDEX idx_rosters_member_round ON public.rosters(league_member_id, round);
CREATE INDEX idx_player_stats_player ON public.player_stats_cache(player_id, nhl_season, playoff_round);
CREATE INDEX idx_team_stats_team ON public.team_stats_cache(team_id, nhl_season, playoff_round);

-- ============================================================================
-- FUNCTIONS & TRIGGERS
-- ============================================================================

-- Auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION public.handle_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER set_updated_at_users
  BEFORE UPDATE ON public.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

CREATE TRIGGER set_updated_at_leagues
  BEFORE UPDATE ON public.leagues
  FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

-- Auto-create user profile on signup
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO public.users (id, email, display_name)
  VALUES (
    NEW.id,
    NEW.email,
    COALESCE(NEW.raw_user_meta_data->>'display_name', split_part(NEW.email, '@', 1))
  );
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- Calculate member points from roster
CREATE OR REPLACE FUNCTION public.calculate_member_points(p_member_id UUID, p_round INTEGER)
RETURNS INTEGER AS $$
DECLARE
  total INTEGER := 0;
BEGIN
  SELECT COALESCE(SUM(points_earned), 0) INTO total
  FROM public.rosters
  WHERE league_member_id = p_member_id
    AND round = p_round
    AND is_active = TRUE;
  RETURN total;
END;
$$ LANGUAGE plpgsql;

-- Validate roster composition
CREATE OR REPLACE FUNCTION public.validate_roster_composition(p_member_id UUID, p_round INTEGER)
RETURNS BOOLEAN AS $$
DECLARE
  f_count INTEGER;
  d_count INTEGER;
  g_count INTEGER;
BEGIN
  SELECT
    COUNT(*) FILTER (WHERE position = 'F' AND is_active = TRUE),
    COUNT(*) FILTER (WHERE position = 'D' AND is_active = TRUE),
    COUNT(*) FILTER (WHERE position = 'G' AND is_active = TRUE)
  INTO f_count, d_count, g_count
  FROM public.rosters
  WHERE league_member_id = p_member_id AND round = p_round;

  RETURN f_count <= 5 AND d_count <= 3 AND g_count <= 1;
END;
$$ LANGUAGE plpgsql;

-- Handle IR activation with retroactive points
CREATE OR REPLACE FUNCTION public.activate_ir_player(
  p_league_member_id UUID,
  p_round INTEGER,
  p_injured_roster_id UUID,
  p_ir_roster_id UUID
)
RETURNS VOID AS $$
DECLARE
  injured_pos TEXT;
  ir_pos TEXT;
BEGIN
  -- Get positions
  SELECT position INTO injured_pos FROM public.rosters WHERE id = p_injured_roster_id;
  SELECT position INTO ir_pos FROM public.rosters WHERE id = p_ir_roster_id;

  -- Validate position match (F replaces F, D replaces D)
  IF (injured_pos = 'F' AND ir_pos != 'IR_F') OR (injured_pos = 'D' AND ir_pos != 'IR_D') THEN
    RAISE EXCEPTION 'IR player position does not match injured player position';
  END IF;

  -- Deactivate injured player (lose all their points)
  UPDATE public.rosters
  SET is_active = FALSE, points_earned = 0
  WHERE id = p_injured_roster_id;

  -- Activate IR player into the main roster position
  UPDATE public.rosters
  SET position = injured_pos, is_active = TRUE, activated_from_ir = TRUE
  WHERE id = p_ir_roster_id;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- ROW LEVEL SECURITY
-- ============================================================================

ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.leagues ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.league_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.drafts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.draft_picks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.rosters ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.player_stats_cache ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.team_stats_cache ENABLE ROW LEVEL SECURITY;

-- Users policies
CREATE POLICY "Users can read own profile"
  ON public.users FOR SELECT
  USING (auth.uid() = id);

CREATE POLICY "Users can update own profile"
  ON public.users FOR UPDATE
  USING (auth.uid() = id)
  WITH CHECK (auth.uid() = id);

CREATE POLICY "Users can read other users in same league"
  ON public.users FOR SELECT
  USING (
    id IN (
      SELECT lm.user_id FROM public.league_members lm
      WHERE lm.league_id IN (
        SELECT lm2.league_id FROM public.league_members lm2
        WHERE lm2.user_id = auth.uid()
      )
    )
  );

-- Leagues policies
CREATE POLICY "League members can read their leagues"
  ON public.leagues FOR SELECT
  USING (
    id IN (
      SELECT league_id FROM public.league_members
      WHERE user_id = auth.uid()
    )
  );

CREATE POLICY "Anyone can read league by invite code"
  ON public.leagues FOR SELECT
  USING (true);

CREATE POLICY "Authenticated users can create leagues"
  ON public.leagues FOR INSERT
  WITH CHECK (auth.uid() = commissioner_id);

CREATE POLICY "Commissioners can update their leagues"
  ON public.leagues FOR UPDATE
  USING (auth.uid() = commissioner_id)
  WITH CHECK (auth.uid() = commissioner_id);

-- League members policies
CREATE POLICY "Members can read league members"
  ON public.league_members FOR SELECT
  USING (
    league_id IN (
      SELECT league_id FROM public.league_members
      WHERE user_id = auth.uid()
    )
  );

CREATE POLICY "Users can join leagues"
  ON public.league_members FOR INSERT
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can leave leagues"
  ON public.league_members FOR DELETE
  USING (auth.uid() = user_id);

-- Drafts policies
CREATE POLICY "League members can read drafts"
  ON public.drafts FOR SELECT
  USING (
    league_id IN (
      SELECT league_id FROM public.league_members
      WHERE user_id = auth.uid()
    )
  );

CREATE POLICY "Commissioners can manage drafts"
  ON public.drafts FOR ALL
  USING (
    league_id IN (
      SELECT id FROM public.leagues
      WHERE commissioner_id = auth.uid()
    )
  );

-- Draft picks policies
CREATE POLICY "League members can read draft picks"
  ON public.draft_picks FOR SELECT
  USING (
    draft_id IN (
      SELECT d.id FROM public.drafts d
      JOIN public.league_members lm ON lm.league_id = d.league_id
      WHERE lm.user_id = auth.uid()
    )
  );

CREATE POLICY "Members can insert own draft picks"
  ON public.draft_picks FOR INSERT
  WITH CHECK (
    league_member_id IN (
      SELECT id FROM public.league_members
      WHERE user_id = auth.uid()
    )
  );

-- Rosters policies
CREATE POLICY "League members can read rosters"
  ON public.rosters FOR SELECT
  USING (
    league_member_id IN (
      SELECT lm.id FROM public.league_members lm
      WHERE lm.league_id IN (
        SELECT lm2.league_id FROM public.league_members lm2
        WHERE lm2.user_id = auth.uid()
      )
    )
  );

CREATE POLICY "Members can manage own rosters"
  ON public.rosters FOR ALL
  USING (
    league_member_id IN (
      SELECT id FROM public.league_members
      WHERE user_id = auth.uid()
    )
  );

-- Stats cache is readable by all authenticated users
CREATE POLICY "Authenticated users can read player stats"
  ON public.player_stats_cache FOR SELECT
  USING (auth.role() = 'authenticated');

CREATE POLICY "Authenticated users can read team stats"
  ON public.team_stats_cache FOR SELECT
  USING (auth.role() = 'authenticated');

-- ============================================================================
-- REALTIME
-- ============================================================================

ALTER PUBLICATION supabase_realtime ADD TABLE public.drafts;
ALTER PUBLICATION supabase_realtime ADD TABLE public.draft_picks;
ALTER PUBLICATION supabase_realtime ADD TABLE public.rosters;
ALTER PUBLICATION supabase_realtime ADD TABLE public.league_members;
