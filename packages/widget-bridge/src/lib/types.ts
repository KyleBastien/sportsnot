export interface SetFeaturedLeagueOptions {
  shareCode: string;
}

export interface SetFeaturedLeagueResult {
  shareCode: string;
}

export interface GetFeaturedLeagueResult {
  shareCode: string | null;
  allShareCodes: string[];
}

export interface StartLiveActivityOptions {
  shareCode: string;
  leagueId: string;
  leagueName: string;
}

export interface StartLiveActivityResult {
  activityId: string;
}

export interface IsLiveActivitySupportedResult {
  supported: boolean;
}

/**
 * Contract mirrored by the native Swift `WidgetBridgePlugin` and the
 * JavaScript no-op implementation used on web.
 */
export interface WidgetBridgePlugin {
  setFeaturedLeague(
    options: SetFeaturedLeagueOptions
  ): Promise<SetFeaturedLeagueResult>;
  getFeaturedLeague(): Promise<GetFeaturedLeagueResult>;
  isLiveActivitySupported(): Promise<IsLiveActivitySupportedResult>;
  startLiveActivity(
    options: StartLiveActivityOptions
  ): Promise<StartLiveActivityResult>;
  endLiveActivity(): Promise<void>;
  addListener(
    eventName: 'activityTokenUpdated',
    listenerFunc: (event: {
      activityId: string;
      token: string;
      shareCode: string;
    }) => void
  ): Promise<{ remove: () => Promise<void> }>;
}
