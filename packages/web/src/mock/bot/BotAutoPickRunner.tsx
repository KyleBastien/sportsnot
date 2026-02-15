import { useBotAutoPick } from './useBotAutoPick';

/**
 * Invisible component that activates the bot auto-pick hook.
 * Renders nothing — just runs the useEffect that monitors draft state
 * and dispatches MAKE_PICK for bots after a 1-2 second delay.
 *
 * Mount this inside MockDataProvider when a draft may be active.
 */
export function BotAutoPickRunner(): null {
  useBotAutoPick();
  return null;
}
