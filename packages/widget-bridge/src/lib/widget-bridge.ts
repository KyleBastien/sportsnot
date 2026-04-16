import { registerPlugin, Capacitor } from '@capacitor/core';
import type { WidgetBridgePlugin } from './types';

const nativeBridge = registerPlugin<WidgetBridgePlugin>('WidgetBridge', {
  web: () => import('./widget-bridge.web').then((m) => new m.WidgetBridgeWeb()),
});

/**
 * Returns true when running inside the Capacitor iOS shell (not a web browser).
 */
export const isWidgetBridgeAvailable = (): boolean =>
  Capacitor.isNativePlatform() && Capacitor.getPlatform() === 'ios';

export const WidgetBridge = nativeBridge;
