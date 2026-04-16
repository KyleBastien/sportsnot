-- Add allow_ir_slots setting to leagues table
-- Defaults to TRUE so existing leagues retain current behavior (IR enabled)
ALTER TABLE public.leagues
  ADD COLUMN allow_ir_slots BOOLEAN NOT NULL DEFAULT TRUE;

-- Trigger function: prevent IR draft picks when allow_ir_slots is false
CREATE OR REPLACE FUNCTION public.check_ir_draft_pick()
RETURNS TRIGGER AS $$
DECLARE
  v_league_id UUID;
  v_allow_ir BOOLEAN;
BEGIN
  -- Only check IR positions
  IF NEW.position NOT IN ('IR_F', 'IR_D') THEN
    RETURN NEW;
  END IF;

  -- Look up the league via draft → league
  SELECT d.league_id INTO v_league_id
  FROM public.drafts d
  WHERE d.id = NEW.draft_id;

  SELECT l.allow_ir_slots INTO v_allow_ir
  FROM public.leagues l
  WHERE l.id = v_league_id;

  IF v_allow_ir = FALSE THEN
    RAISE EXCEPTION 'IR slots are disabled for this league';
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_check_ir_draft_pick
  BEFORE INSERT ON public.draft_picks
  FOR EACH ROW
  EXECUTE FUNCTION public.check_ir_draft_pick();
