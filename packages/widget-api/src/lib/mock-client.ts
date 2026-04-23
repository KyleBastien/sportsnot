// Mock widget-api client backed by @sportsnot/mock-data.
// Used when the Capacitor iOS host app runs with VITE_MOCK_MODE=true so the
// widget-api surface works end-to-end offline. The real Swift widget always
// uses the HTTP client; this module is for the JS side only.

import type { WidgetApiClient } from './client';
import type {
  RegisterLiveActivityTokenRequest,
  WidgetGame,
  WidgetSnapshot,
} from './types';

type MockDataModule = typeof import('@sportsnot/mock-data');

let cachedModule: MockDataModule | null = null;

function widgetDateString(): string {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/New_York',
  }).format(new Date());
}

async function loadMockData(): Promise<MockDataModule> {
  if (cachedModule) return cachedModule;
  cachedModule = (await import('@sportsnot/mock-data')) as MockDataModule;
  return cachedModule;
}

function pickTodayGames(mod: MockDataModule, date: string): WidgetGame[] {
  const allRounds = [
    mod.gamesR1,
    mod.gamesR2,
    mod.gamesCf,
    mod.gamesScf,
  ].flat() as Array<{
    id: number;
    gameDate?: string;
    startTimeUTC?: string;
    gameState?: string;
    homeTeam: { id: number; abbrev?: string; name?: string; score?: number };
    awayTeam: { id: number; abbrev?: string; name?: string; score?: number };
    period?: number;
    periodTimeRemaining?: string;
  }>;

  return allRounds
    .filter((g) => (g.gameDate ?? '').startsWith(date))
    .map<WidgetGame>((g) => ({
      id: g.id,
      startsAt: g.startTimeUTC ?? `${date}T00:00:00Z`,
      state: (g.gameState as WidgetGame['state']) ?? 'FUT',
      homeTeamId: g.homeTeam.id,
      homeTeamAbbrev: g.homeTeam.abbrev ?? '',
      homeTeamName: g.homeTeam.name ?? '',
      homeScore: g.homeTeam.score ?? 0,
      awayTeamId: g.awayTeam.id,
      awayTeamAbbrev: g.awayTeam.abbrev ?? '',
      awayTeamName: g.awayTeam.name ?? '',
      awayScore: g.awayTeam.score ?? 0,
      period: g.period ?? null,
      timeRemaining: g.periodTimeRemaining ?? null,
      hasDraftedPlayers: false,
    }));
}

export function createMockWidgetApiClient(): Pick<
  WidgetApiClient,
  'getSnapshot' | 'registerLiveActivityToken'
> {
  return {
    async getSnapshot(
      shareCode: string,
      date?: string
    ): Promise<WidgetSnapshot> {
      const mod = await loadMockData();
      const today = date ?? widgetDateString();
      const games = pickTodayGames(mod, today);
      return {
        league: {
          id: 'mock-league-id',
          name: 'Mock League',
          shareCode,
          currentRound: 1,
          status: 'active',
        },
        date: today,
        generatedAt: new Date().toISOString(),
        games,
        players: [],
      };
    },
    async registerLiveActivityToken(
      _req: RegisterLiveActivityTokenRequest
    ): Promise<void> {
      return;
    },
  };
}
