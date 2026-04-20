import { useState } from 'react';
import { Button, Tooltip } from '@mantine/core';
import { IconDeviceMobile } from '@tabler/icons-react';
import {
  WidgetBridge,
  isWidgetBridgeAvailable,
} from '@sportsnot/widget-bridge';
import { WidgetApiClient } from '@sportsnot/widget-api';

interface FeatureOnWidgetButtonProps {
  leagueId: string;
  leagueName: string;
  shareCode: string | null | undefined;
  /**
   * The current user's `team_name` within this league. Persisted alongside
   * the share code in device storage so the native widget can compute the
   * user's own fantasy total against the league-wide snapshot.
   */
  myTeamName?: string | null;
}

/**
 * Renders a button that, when running inside the Capacitor native shell
 * (iOS or Android), writes the league's share code into device storage
 * so the native widget starts following this league. On the web this is
 * a no-op that still exercises the localStorage fallback for QA.
 */
export function FeatureOnWidgetButton({
  leagueId,
  leagueName,
  shareCode,
  myTeamName,
}: FeatureOnWidgetButtonProps) {
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  if (!shareCode) return null;
  if (!isWidgetBridgeAvailable()) return null;

  const handleClick = async () => {
    setSaving(true);
    setSaved(false);
    try {
      await WidgetBridge.setFeaturedLeague({
        shareCode,
        myTeamName: myTeamName ?? undefined,
      });
      const supported = await WidgetBridge.isLiveActivitySupported();
      if (supported.supported) {
        const hasGamesToday = await leagueHasGamesToday(shareCode);
        if (hasGamesToday) {
          await WidgetBridge.startLiveActivity({
            shareCode,
            leagueId,
            leagueName,
          });
        } else {
          await WidgetBridge.endLiveActivity();
        }
      }
      setSaved(true);
      window.setTimeout(() => setSaved(false), 2500);
    } finally {
      setSaving(false);
    }
  };

  const label = saved ? 'Widget updated' : 'Feature on widget';

  return (
    <Tooltip
      label="Sets this league as the featured one in your Home Screen widget. If a game is on today, starts a Live Activity too."
      multiline
      w={260}
    >
      <Button
        variant="light"
        color="grape"
        leftSection={<IconDeviceMobile size={16} />}
        onClick={handleClick}
        loading={saving}
      >
        {label}
      </Button>
    </Tooltip>
  );
}

async function leagueHasGamesToday(shareCode: string): Promise<boolean> {
  const supabaseUrl = import.meta.env.VITE_SUPABASE_URL as string | undefined;
  const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined;
  if (!supabaseUrl || !anonKey) return false;
  try {
    const client = new WidgetApiClient({ supabaseUrl, anonKey });
    const snapshot = await client.getSnapshot(shareCode);
    return snapshot.games.length > 0;
  } catch {
    return false;
  }
}
