-- Schedule the sync-nhl-stats edge function via pg_cron.
--
-- Prerequisites (one-time, run by hand in the Supabase dashboard):
--   1. Extensions enabled:  pg_cron, pg_net   (both already on in SportsNot)
--   2. Vault secret named `service_role_key` containing the project's
--      service_role JWT. Create via Dashboard → Project Settings → Vault.
--      We use Vault instead of `ALTER DATABASE ... SET app.settings.*`
--      because hosted Supabase blocks that GUC with permission denied.
--
-- This migration is idempotent: it unschedules any prior job with the
-- same name before (re)scheduling.
--
-- Operational notes:
--   • Cadence: every 15 minutes. The NHL API isn't real-time; faster
--     cadences burn edge function invocations without adding freshness.
--   • Start gate: the CASE expression no-ops until 2026-04-18 18:00 UTC
--     (11:00 PDT), which is the 2026 playoffs Round 1 puck drop window.
--     Remove or advance the gate for future rounds/seasons.
--   • Timeout: 120_000 ms on pg_net because the function fans out to the
--     NHL API for every drafted player; pg_net defaults to 5 s and will
--     report a spurious timeout while the function still completes.

SELECT cron.unschedule('sync-nhl-stats')
WHERE EXISTS (SELECT 1 FROM cron.job WHERE jobname = 'sync-nhl-stats');

SELECT cron.schedule(
  'sync-nhl-stats',
  '*/15 * * * *',
  $cron$
  SELECT CASE
    WHEN now() >= '2026-04-18 18:00:00+00'::timestamptz THEN
      net.http_post(
        url := 'https://cytkjoftdrvzeirqmbui.supabase.co/functions/v1/sync-nhl-stats',
        headers := jsonb_build_object(
          'Content-Type', 'application/json',
          'Authorization', 'Bearer ' || (
            SELECT decrypted_secret
            FROM vault.decrypted_secrets
            WHERE name = 'service_role_key'
            LIMIT 1
          )
        ),
        body := jsonb_build_object(
          'season', '20252026',
          'playoff_round', 1
        ),
        timeout_milliseconds := 120000
      )
  END;
  $cron$
);
