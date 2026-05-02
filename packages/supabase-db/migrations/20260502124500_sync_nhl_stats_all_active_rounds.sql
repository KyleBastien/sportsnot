-- Schedule sync-nhl-stats to discover active/drafting league rounds itself.
--
-- Why:
-- - Round 1 and Round 2 can overlap on the calendar.
-- - A single hard-coded playoff_round in cron cannot safely support leagues
--   that are still active in Round 1 while other leagues are already drafting
--   or active in Round 2.
-- - The edge function now detects all active/drafting league rounds and syncs
--   each round independently using seriesStatus.round from the NHL scoreboard.

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
          'season', '20252026'
        ),
        timeout_milliseconds := 120000
      )
  END;
  $cron$
);
