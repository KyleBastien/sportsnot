import { WebPlugin } from '@capacitor/core';
import type {
  GetFeaturedLeagueResult,
  IsLiveActivitySupportedResult,
  SetFeaturedLeagueOptions,
  SetFeaturedLeagueResult,
  StartLiveActivityOptions,
  StartLiveActivityResult,
  WidgetBridgePlugin,
} from './types';

const STORAGE_KEY = 'sportsnot.widget.featuredShareCode';
const ALL_KEY = 'sportsnot.widget.shareCodes';
const MY_TEAM_NAMES_KEY = 'sportsnot.widget.myTeamNamesByShareCode';

/**
 * No-op browser fallback. Persists the selected share code in
 * localStorage so we can exercise the same UI on the web.
 */
export class WidgetBridgeWeb extends WebPlugin implements WidgetBridgePlugin {
  async setFeaturedLeague(
    options: SetFeaturedLeagueOptions
  ): Promise<SetFeaturedLeagueResult> {
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(STORAGE_KEY, options.shareCode);
      const all = this.readAll();
      if (!all.includes(options.shareCode)) {
        all.push(options.shareCode);
        window.localStorage.setItem(ALL_KEY, JSON.stringify(all));
      }
      if (options.myTeamName) {
        const map = this.readTeamNames();
        map[options.shareCode] = options.myTeamName;
        window.localStorage.setItem(MY_TEAM_NAMES_KEY, JSON.stringify(map));
      }
    }
    return {
      shareCode: options.shareCode,
      myTeamName: options.myTeamName ?? null,
    };
  }

  async getFeaturedLeague(): Promise<GetFeaturedLeagueResult> {
    if (typeof window === 'undefined') {
      return { shareCode: null, allShareCodes: [], myTeamName: null };
    }
    const code = window.localStorage.getItem(STORAGE_KEY);
    return {
      shareCode: code,
      allShareCodes: this.readAll(),
      myTeamName: code ? (this.readTeamNames()[code] ?? null) : null,
    };
  }

  async isLiveActivitySupported(): Promise<IsLiveActivitySupportedResult> {
    return { supported: false };
  }

  async startLiveActivity(
    _options: StartLiveActivityOptions
  ): Promise<StartLiveActivityResult> {
    throw this.unimplemented('Live Activities are only available on iOS 16.2+');
  }

  async endLiveActivity(): Promise<void> {
    return;
  }

  private readAll(): string[] {
    if (typeof window === 'undefined') return [];
    try {
      const raw = window.localStorage.getItem(ALL_KEY);
      if (!raw) return [];
      const parsed: unknown = JSON.parse(raw);
      return Array.isArray(parsed)
        ? parsed.filter((v): v is string => typeof v === 'string')
        : [];
    } catch {
      return [];
    }
  }

  private readTeamNames(): Record<string, string> {
    if (typeof window === 'undefined') return {};
    try {
      const raw = window.localStorage.getItem(MY_TEAM_NAMES_KEY);
      if (!raw) return {};
      const parsed: unknown = JSON.parse(raw);
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
        return {};
      }
      const out: Record<string, string> = {};
      for (const [k, v] of Object.entries(parsed as Record<string, unknown>)) {
        if (typeof v === 'string') out[k] = v;
      }
      return out;
    } catch {
      return {};
    }
  }
}
