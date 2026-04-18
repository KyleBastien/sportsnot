export interface SetFeaturedLeagueOptions {
  shareCode: string;
  /**
   * The current user's `team_name` within this league. Stored per-share-code
   * in the App Group so the iOS widget can compute "your team's points" for
   * a league that's otherwise rendered league-wide.
   */
  myTeamName?: string;
}

export interface SetFeaturedLeagueResult {
  shareCode: string;
  myTeamName?: string | null;
}

export interface GetFeaturedLeagueResult {
  shareCode: string | null;
  allShareCodes: string[];
  /** Team name of the current user inside the currently-featured league. */
  myTeamName?: string | null;
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
