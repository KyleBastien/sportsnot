import { registerPlugin, Capacitor } from '@capacitor/core';
import type { WidgetBridgePlugin } from './types';

const nativeBridge = registerPlugin<WidgetBridgePlugin>('WidgetBridge', {
  web: () => import('./widget-bridge.web').then((m) => new m.WidgetBridgeWeb()),
});

/**
 * Returns true when running inside a Capacitor native shell (iOS or Android).
 */
export const isWidgetBridgeAvailable = (): boolean =>
  Capacitor.isNativePlatform() &&
  (Capacitor.getPlatform() === 'ios' || Capacitor.getPlatform() === 'android');

export const WidgetBridge = nativeBridge;
