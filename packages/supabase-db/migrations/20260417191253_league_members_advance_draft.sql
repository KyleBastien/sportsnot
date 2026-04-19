-- League members need to advance the draft's current_pick (and mark it
-- completed on the final pick) after submitting their own pick. The existing
-- "Commissioners can manage drafts" policy silently blocked these updates for
-- non-commissioner members, causing the draft to appear stuck on the same
-- picker after a pick was inserted.
CREATE POLICY "League members can advance draft"
  ON public.drafts FOR UPDATE
  USING (
    league_id IN (
      SELECT league_id FROM public.league_members
      WHERE user_id = auth.uid()
    )
  )
  WITH CHECK (
    league_id IN (
      SELECT league_id FROM public.league_members
      WHERE user_id = auth.uid()
    )
  );
