/**
 * No-op stubs for all mock hooks, providers, and utilities.
 * Used in production builds (VITE_MOCK_MODE !== 'true') to replace
 * real mock modules via NormalModuleReplacementPlugin, ensuring
 * zero mock code ships in the production bundle.
 *
 * Every exported function is a no-op that returns a minimal
 * compatible shape. In production the return values are never
 * consumed because call-sites are guarded by IS_MOCK ternaries.
 */

const noopQuery = () => ({
  data: undefined,
  isLoading: false,
  isError: false,
  error: null,
});

const noopMutation = () => ({
  mutate: () => {},
  mutateAsync: () => Promise.resolve(),
  isPending: false,
  isLoading: false,
});

// mock/hooks/useMockLeagues
export const useMockMyLeagues = noopQuery;
export const useMockLeague = noopQuery;
export const useMockCreateLeague = noopMutation;
export const useMockLiveGamesTeamStats = noopQuery;

// mock/hooks/useMockDraft
export const useMockDraft = noopQuery;
export const useMockStartDraft = noopMutation;
export const useMockMakePick = noopMutation;
export const useMockLeagueMembers = noopQuery;
export const useMockCompletedDrafts = noopQuery;
export const useMockStartReDraft = noopMutation;

// mock/hooks/useMockNhlApi
export const useMockPlayoffPlayers = noopQuery;
export const useMockPlayoffTeams = noopQuery;
export const useMockRegularSeasonPlayers = noopQuery;

// mock/hooks/useMockRoster
export const useMockRoster = noopQuery;
export const useMockActivateIR = noopMutation;

// mock/hooks/useMockStandings
export const useMockStandings = noopQuery;

// mock/hooks/useMockScoringHistory
export const useMockScoringHistory = noopQuery;

// mock/hooks/useMockAuth
export const useMockAuth = () => ({
  user: null,
  session: null,
  loading: false,
  signInWithMagicLink: async () => ({ error: null }),
  signInWithOtp: async () => ({ error: null }),
  verifyOtp: async () => ({ data: null, error: null }),
  signOut: async () => ({ error: null }),
});

// mock/hooks/useMockUpdateProfile
export const useMockUpdateProfile = () => ({
  createMockProfileClient: () => ({
    updateUsersTable: async () => ({ error: null }),
    updateAuthMetadata: async () => ({ error: null }),
  }),
});

// mock/hooks/useMockLiveGames (re-export for direct imports)
export { useMockLiveGamesTeamStats as useMockLiveGames };

// mock/MockDataProvider
export const useMockData = () => ({
  state: {},
  dispatch: () => {},
  hooks: {},
});

// mock/utils
export const sortMembersForReDraft = () => [];
