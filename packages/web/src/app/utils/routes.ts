export const routes = {
  leagues: {
    dashboard: (leagueId: string) => `/leagues/${leagueId}`,
    settings: (leagueId: string) => `/leagues/${leagueId}/settings`,
    create: () => '/leagues/create',
    join: () => '/leagues/join',
  },
  draft: {
    lobby: (draftId: string) => `/draft/${draftId}/lobby`,
    board: (draftId: string) => `/draft/${draftId}`,
  },
} as const;
