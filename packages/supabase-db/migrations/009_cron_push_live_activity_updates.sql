-- Schedule push-live-activity-updates to fan out APNs Live Activity updates
-- to all registered tokens. Staggered 5 minutes after sync-nhl-stats so the
-- push goes out after fresh stats have landed.
--
-- sync-nhl-stats runs at  0,15,30,45 (every :00,:15,:30,:45)
-- push runs at           5,20,35,50 (every :05,:20,:35,:50)
--
-- Gated to only fire after playoffs start (2026-04-18 18:00 UTC) to match
-- the pattern used by sync-nhl-stats.

SELECT cron.schedule(
  'push-live-activity-updates',
  '5,20,35,50 * * * *',
  $$
  SELECT CASE
    WHEN now() >= '2026-04-18 18:00:00+00'::timestamptz THEN
      net.http_post(
        url := 'https://cytkjoftdrvzeirqmbui.supabase.co/functions/v1/push-live-activity-updates',
        headers := jsonb_build_object(
          'Content-Type', 'application/json',
          'Authorization', 'Bearer ' || (SELECT decrypted_secret FROM vault.decrypted_secrets WHERE name = 'service_role_key' LIMIT 1)
        ),
        body := '{}'::jsonb,
        timeout_milliseconds := 60000
      )
  END;
  $$
);
