-- Add platform column to live_activity_tokens for dual-platform push (iOS APNs + Android FCM)
ALTER TABLE live_activity_tokens
  ADD COLUMN IF NOT EXISTS platform TEXT NOT NULL DEFAULT 'ios';

-- Backfill existing rows as iOS (they were all iOS before Android support)
UPDATE live_activity_tokens SET platform = 'ios' WHERE platform IS NULL;

-- Index for efficient per-platform queries in push-live-activity-updates
CREATE INDEX IF NOT EXISTS idx_live_activity_tokens_platform_league
  ON live_activity_tokens (platform, league_id);
