import { isNativeIOSPlatform } from '../platform/nativeMobilePlatform';

/**
 * Returns true when running inside the Capacitor iOS native shell.
 * Always false on web / mobile-web browsers.
 */
export function useIsNativeIOS(): boolean {
  return isNativeIOSPlatform();
}
