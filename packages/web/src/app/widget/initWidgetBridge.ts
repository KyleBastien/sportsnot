import {
  WidgetBridge,
  isWidgetBridgeAvailable,
  type WidgetBridgePlugin,
} from '@sportsnot/widget-bridge';
import { WidgetApiClient } from '@sportsnot/widget-api';

export interface InitWidgetBridgeOptions {
  supabaseUrl: string;
  anonKey: string;
  bundleId: string;
  /** Dependency injection hooks for tests. */
  bridge?: Pick<WidgetBridgePlugin, 'addListener'>;
  client?: Pick<WidgetApiClient, 'registerLiveActivityToken'>;
  /** Override native-detection for tests. */
  isAvailable?: () => boolean;
  /** Called when the backend POST fails (tests use this to observe errors). */
  onError?: (error: unknown) => void;
}

export interface InitWidgetBridgeHandle {
  remove: () => Promise<void>;
}

/**
 * Subscribes to `activityTokenUpdated` events emitted by the native
 * Capacitor WidgetBridge plugin and forwards each APNs Live Activity
 * update token to the `register-live-activity-token` edge function.
 *
 * On non-iOS platforms (or when the native plugin isn't available) this
 * is a no-op and returns a handle whose `remove()` is idempotent.
 */
export async function initWidgetBridge(
  options: InitWidgetBridgeOptions
): Promise<InitWidgetBridgeHandle> {
  const available = (options.isAvailable ?? isWidgetBridgeAvailable)();
  if (!available) {
    return { remove: async () => undefined };
  }

  const bridge = options.bridge ?? WidgetBridge;
  const client =
    options.client ??
    new WidgetApiClient({
      supabaseUrl: options.supabaseUrl,
      anonKey: options.anonKey,
    });

  const subscription = await bridge.addListener(
    'activityTokenUpdated',
    (event) => {
      void (async () => {
        try {
          await client.registerLiveActivityToken({
            shareCode: event.shareCode,
            token: event.token,
            kind: 'activity',
            bundleId: options.bundleId,
          });
        } catch (error) {
          options.onError?.(error);
        }
      })();
    }
  );

  return { remove: () => subscription.remove() };
}
