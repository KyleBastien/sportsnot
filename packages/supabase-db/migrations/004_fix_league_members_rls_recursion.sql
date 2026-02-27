-- Fix infinite recursion in league_members SELECT policy.
-- The old policy queried league_members from within its own SELECT policy,
-- causing Postgres to re-evaluate the same policy in an infinite loop.
-- Solution: use a SECURITY DEFINER function that bypasses RLS.

CREATE OR REPLACE FUNCTION public.get_user_league_ids()
RETURNS SETOF uuid
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
STABLE
AS $$
  SELECT league_id
  FROM public.league_members
  WHERE user_id = auth.uid();
$$;

-- Replace the self-referencing league_members SELECT policy
DROP POLICY IF EXISTS "Members can read league members"
  ON public.league_members;

CREATE POLICY "Members can read league members"
  ON public.league_members FOR SELECT
  USING (
    league_id IN (SELECT public.get_user_league_ids())
  );

-- Also update the leagues SELECT policy that cross-references league_members,
-- so all membership checks go through the same bypass function.
DROP POLICY IF EXISTS "League members can read their leagues"
  ON public.leagues;

CREATE POLICY "League members can read their leagues"
  ON public.leagues FOR SELECT
  USING (
    id IN (SELECT public.get_user_league_ids())
  );
