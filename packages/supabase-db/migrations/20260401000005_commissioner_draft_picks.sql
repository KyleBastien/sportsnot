-- Allow commissioners to insert draft picks for any member in their league
CREATE POLICY "Commissioner can insert draft picks for league members"
  ON public.draft_picks FOR INSERT
  WITH CHECK (
    EXISTS (
      SELECT 1
      FROM public.drafts d
      JOIN public.leagues l ON l.id = d.league_id
      JOIN public.league_members lm ON lm.league_id = l.id
      WHERE d.id = draft_id
        AND lm.id = league_member_id
        AND l.commissioner_id = auth.uid()
    )
  );

-- Allow commissioners to manage rosters for any member in their league
CREATE POLICY "Commissioner can manage league rosters"
  ON public.rosters FOR ALL
  USING (
    league_member_id IN (
      SELECT lm.id FROM public.league_members lm
      JOIN public.leagues l ON l.id = lm.league_id
      WHERE l.commissioner_id = auth.uid()
    )
  )
  WITH CHECK (
    league_member_id IN (
      SELECT lm.id FROM public.league_members lm
      JOIN public.leagues l ON l.id = lm.league_id
      WHERE l.commissioner_id = auth.uid()
    )
  );
