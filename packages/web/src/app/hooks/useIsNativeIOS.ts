import { Capacitor } from '@capacitor/core';

/**
 * Returns true when running inside the Capacitor iOS native shell.
 * Always false on web / mobile-web browsers.
 */
export function useIsNativeIOS(): boolean {
  return Capacitor.isNativePlatform() && Capacitor.getPlatform() === 'ios';
}
