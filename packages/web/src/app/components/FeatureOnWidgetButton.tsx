import { useState } from 'react';
import { Button, Tooltip } from '@mantine/core';
import { IconDeviceMobile } from '@tabler/icons-react';
import {
  WidgetBridge,
  isWidgetBridgeAvailable,
} from '@sportsnot/widget-bridge';

interface FeatureOnWidgetButtonProps {
  leagueId: string;
  leagueName: string;
  shareCode: string | null | undefined;
}

/**
 * Renders a button that, when running inside the Capacitor iOS shell,
 * writes the league's share code into the App Group so the native
 * widget starts following this league. On the web this is a no-op that
 * still exercises the localStorage fallback so QA can preview behavior.
 */
export function FeatureOnWidgetButton({
  leagueId,
  leagueName,
  shareCode,
}: FeatureOnWidgetButtonProps) {
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  if (!shareCode) return null;

  const native = isWidgetBridgeAvailable();

  const handleClick = async () => {
    setSaving(true);
    setSaved(false);
    try {
      await WidgetBridge.setFeaturedLeague({ shareCode });
      if (native) {
        const supported = await WidgetBridge.isLiveActivitySupported();
        if (supported.supported) {
          await WidgetBridge.startLiveActivity({
            shareCode,
            leagueId,
            leagueName,
          });
        }
      }
      setSaved(true);
      window.setTimeout(() => setSaved(false), 2500);
    } finally {
      setSaving(false);
    }
  };

  const label = saved
    ? 'Widget updated'
    : native
      ? 'Feature on iOS widget'
      : 'Preview on widget';

  return (
    <Tooltip
      label={
        native
          ? 'Sets this league as the featured one in your Home Screen widget and starts a Live Activity.'
          : 'iOS Home Screen widget feature — tap to preview (actual widget only appears in the iOS app).'
      }
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
