import { useState, useEffect, useCallback } from 'react';
import {
  requestNotificationPermission,
  getNotificationPermission,
  isPushSupported,
  subscribeToPush,
  unsubscribeFromPush,
  getCurrentSubscription,
} from '../utils/pushNotifications';

const PREFS_STORAGE_KEY = 'sportsnot_push_prefs';

export interface PushPreferences {
  draftTurn: boolean;
  scoringMilestones: boolean;
}

const DEFAULT_PREFS: PushPreferences = {
  draftTurn: true,
  scoringMilestones: true,
};

function loadPreferences(): PushPreferences {
  try {
    const stored = localStorage.getItem(PREFS_STORAGE_KEY);
    if (stored) {
      return { ...DEFAULT_PREFS, ...JSON.parse(stored) };
    }
  } catch {
    // ignore
  }
  return DEFAULT_PREFS;
}

function savePreferences(prefs: PushPreferences): void {
  try {
    localStorage.setItem(PREFS_STORAGE_KEY, JSON.stringify(prefs));
  } catch {
    // ignore
  }
}

export function usePushNotifications() {
  const [supported] = useState(() => isPushSupported());
  const [permission, setPermission] = useState<NotificationPermission>(() =>
    getNotificationPermission()
  );
  const [subscribed, setSubscribed] = useState(false);
  const [loading, setLoading] = useState(false);
  const [preferences, setPreferencesState] =
    useState<PushPreferences>(loadPreferences);

  // Check current subscription on mount
  useEffect(() => {
    if (!supported) return;
    getCurrentSubscription().then((sub) => {
      setSubscribed(!!sub);
    });
  }, [supported]);

  const subscribe = useCallback(async () => {
    if (!supported) return false;
    setLoading(true);
    try {
      const perm = await requestNotificationPermission();
      setPermission(perm);
      if (perm !== 'granted') {
        setLoading(false);
        return false;
      }
      const sub = await subscribeToPush();
      setSubscribed(!!sub);
      setLoading(false);
      return !!sub;
    } catch {
      setLoading(false);
      return false;
    }
  }, [supported]);

  const unsubscribe = useCallback(async () => {
    if (!supported) return false;
    setLoading(true);
    try {
      const result = await unsubscribeFromPush();
      if (result) {
        setSubscribed(false);
      }
      setLoading(false);
      return result;
    } catch {
      setLoading(false);
      return false;
    }
  }, [supported]);

  const setPreferences = useCallback((prefs: Partial<PushPreferences>) => {
    setPreferencesState((prev) => {
      const updated = { ...prev, ...prefs };
      savePreferences(updated);
      return updated;
    });
  }, []);

  return {
    supported,
    permission,
    subscribed,
    loading,
    preferences,
    subscribe,
    unsubscribe,
    setPreferences,
  };
}
