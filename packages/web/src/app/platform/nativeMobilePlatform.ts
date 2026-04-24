export type NativeMobilePlatform = 'ios' | 'android';

interface RuntimeCapacitor {
  getPlatform?: () => string;
  isNativePlatform?: () => boolean;
}

interface RuntimePlatformWindow {
  Capacitor?: RuntimeCapacitor;
  CapacitorCustomPlatform?: { name?: string } | null;
  androidBridge?: unknown;
  webkit?: {
    messageHandlers?: {
      bridge?: unknown;
    };
  };
}

function getRuntimeWindow(): RuntimePlatformWindow | undefined {
  if (typeof window === 'undefined') {
    return undefined;
  }

  return window as RuntimePlatformWindow;
}

function detectBridgePlatform(
  runtimeWindow: RuntimePlatformWindow
): NativeMobilePlatform | 'web' {
  if (runtimeWindow.androidBridge) {
    return 'android';
  }

  if (runtimeWindow.webkit?.messageHandlers?.bridge) {
    return 'ios';
  }

  return 'web';
}

export function getNativeMobilePlatform(
  runtimeWindow: RuntimePlatformWindow | undefined = getRuntimeWindow()
): NativeMobilePlatform | null {
  if (!runtimeWindow) {
    return null;
  }

  const customPlatform = runtimeWindow.CapacitorCustomPlatform?.name;
  const platform =
    customPlatform ??
    runtimeWindow.Capacitor?.getPlatform?.() ??
    detectBridgePlatform(runtimeWindow);

  const isNative =
    customPlatform != null
      ? true
      : (runtimeWindow.Capacitor?.isNativePlatform?.() ??
        detectBridgePlatform(runtimeWindow) !== 'web');

  if (!isNative) {
    return null;
  }

  return platform === 'ios' || platform === 'android' ? platform : null;
}

export function isNativeMobilePlatform(
  runtimeWindow: RuntimePlatformWindow | undefined = getRuntimeWindow()
): boolean {
  return getNativeMobilePlatform(runtimeWindow) !== null;
}

export function isNativeIOSPlatform(
  runtimeWindow: RuntimePlatformWindow | undefined = getRuntimeWindow()
): boolean {
  return getNativeMobilePlatform(runtimeWindow) === 'ios';
}
