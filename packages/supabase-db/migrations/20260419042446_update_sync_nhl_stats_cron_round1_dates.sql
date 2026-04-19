-- Update the sync-nhl-stats cron job to include round date boundaries.
--
-- The original schedule (007_schedule_sync_nhl_stats_cron.sql) only passed
-- `season` and `playoff_round` in the request body. Without `round_start_date`
-- the edge function falls back to fetching only today's games from /score/now,
-- which resets cumulative wins/shutouts to zero on every run.
--
-- By adding `round_start_date` the function iterates every calendar date from
-- round start through today, producing correct cumulative totals on each sync.
-- `round_end_date` is intentionally omitted so the window stays open and
-- automatically caps at today until the round is complete.
--
-- To advance to round 2, create a new migration that unschedules this job and
-- reschedules with `playoff_round: 2` and the appropriate `round_start_date`.

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
          'playoff_round', 1,
          'round_start_date', '2026-04-18'
        ),
        timeout_milliseconds := 120000
      )
  END;
  $cron$
);
