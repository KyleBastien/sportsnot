import {
  createContext,
  useContext,
  useReducer,
  type Dispatch,
  type ReactNode,
} from 'react';
import type {
  League,
  LeagueMember,
  Draft,
  DraftPick,
  RosterSlot,
  NHLPlayerStats,
  NHLGame,
} from '@sportsnot/types';
import {
  gamesR1,
  gamesR2,
  gamesCf,
  gamesScf,
  playerGameLogs,
} from '@sportsnot/mock-data';
import { BotAutoPickRunner } from './bot/BotAutoPickRunner';

// ── Mock user ──────────────────────────────────────────────────────────
export interface MockUser {
  id: string;
  email: string;
  displayName: string;
  avatarUrl: string;
}

const MOCK_USER: MockUser = {
  id: 'mock-user-001',
  email: 'mock@sportsnot.dev',
  displayName: 'Mock User',
  avatarUrl: '',
};

// ── Draft state ────────────────────────────────────────────────────────
export interface MockDraftState {
  draft: Draft;
  picks: DraftPick[];
  availablePlayerIds: number[];
}

// ── State shape ────────────────────────────────────────────────────────
export interface MockState {
  leagues: (League & { members: LeagueMember[]; isMock: boolean })[];
  currentLeague: string | null;
  draftState: MockDraftState | null;
  rosters: Record<string, RosterSlot[]>; // keyed by leagueMemberId
  simulationDate: string; // ISO date string
  currentRound: number; // 1-4
  roundComplete: boolean;
  seasonComplete: boolean;
  playerStats: Record<number, { goals: number; assists: number; gamesPlayed: number }>;
  mockUser: MockUser;
}

// Initial simulation date: day before first R1 game (2025-04-18)
const INITIAL_SIMULATION_DATE = '2025-04-18';

// ── Round game fixtures ────────────────────────────────────────────────
const ROUND_GAMES: Record<number, NHLGame[]> = {
  1: gamesR1 as unknown as NHLGame[],
  2: gamesR2 as unknown as NHLGame[],
  3: gamesCf as unknown as NHLGame[],
  4: gamesScf as unknown as NHLGame[],
};

/** Get the first and last game dates for a given round */
export function getRoundDateBounds(round: number): { firstDate: string; lastDate: string } | null {
  const games = ROUND_GAMES[round];
  if (!games || games.length === 0) return null;
  const dates = games.map((g) => g.gameDate).sort();
  return { firstDate: dates[0], lastDate: dates[dates.length - 1] };
}

/**
 * Pure function: accumulate player stats from fixture data through a given date.
 * Returns cumulative stats keyed by player ID.
 */
export function accumulatePlayerStats(
  logs: Record<number, NHLPlayerStats[]>,
  throughDate: string,
): Record<number, { goals: number; assists: number; gamesPlayed: number }> {
  const result: Record<number, { goals: number; assists: number; gamesPlayed: number }> = {};
  for (const [playerIdStr, entries] of Object.entries(logs)) {
    const playerId = Number(playerIdStr);
    let goals = 0;
    let assists = 0;
    let gamesPlayed = 0;
    for (const entry of entries) {
      if (entry.gameDate <= throughDate) {
        goals += entry.goals;
        assists += entry.assists;
        gamesPlayed += 1;
      }
    }
    if (gamesPlayed > 0) {
      result[playerId] = { goals, assists, gamesPlayed };
    }
  }
  return result;
}

/** Advance an ISO date string by one calendar day */
function addOneDay(dateStr: string): string {
  const d = new Date(dateStr + 'T12:00:00Z'); // noon to avoid DST issues
  d.setUTCDate(d.getUTCDate() + 1);
  return d.toISOString().slice(0, 10);
}

function getInitialState(): MockState {
  return {
    leagues: [],
    currentLeague: null,
    draftState: null,
    rosters: {},
    simulationDate: INITIAL_SIMULATION_DATE,
    currentRound: 1,
    roundComplete: false,
    seasonComplete: false,
    playerStats: {},
    mockUser: MOCK_USER,
  };
}

// ── Actions ────────────────────────────────────────────────────────────
export type MockAction =
  | { type: 'CREATE_LEAGUE'; payload: { league: MockState['leagues'][number] } }
  | { type: 'JOIN_LEAGUE'; payload: { leagueId: string; member: LeagueMember } }
  | { type: 'START_DRAFT'; payload: { draftState: MockDraftState } }
  | { type: 'MAKE_PICK'; payload: { pick: DraftPick } }
  | { type: 'ADVANCE_DAY' }
  | { type: 'ADVANCE_ROUND' }
  | { type: 'ACTIVATE_IR'; payload: { leagueMemberId: string; slotId: string } }
  | { type: 'DEACTIVATE_IR'; payload: { leagueMemberId: string; slotId: string } }
  | { type: 'RESET_ALL' };

// ── Reducer ────────────────────────────────────────────────────────────
function mockReducer(state: MockState, action: MockAction): MockState {
  switch (action.type) {
    case 'RESET_ALL':
      return getInitialState();

    case 'CREATE_LEAGUE':
      return {
        ...state,
        leagues: [...state.leagues, action.payload.league],
        currentLeague: action.payload.league.id,
      };
    case 'JOIN_LEAGUE': {
      const updated = state.leagues.map((l) =>
        l.id === action.payload.leagueId
          ? { ...l, members: [...l.members, action.payload.member] }
          : l,
      );
      return { ...state, leagues: updated };
    }
    case 'START_DRAFT': {
      // Also update the league status to 'drafting'
      const leagueId = action.payload.draftState.draft.leagueId;
      const updatedLeagues = state.leagues.map((l) =>
        l.id === leagueId ? { ...l, status: 'drafting' as const } : l,
      );
      return {
        ...state,
        draftState: action.payload.draftState,
        leagues: updatedLeagues,
      };
    }
    case 'MAKE_PICK': {
      if (!state.draftState) return state;

      const { pick } = action.payload;
      const ds = state.draftState;
      const newPicks = [...ds.picks, pick];

      // Remove picked player/team from available pool
      const pickedId = pick.playerId ?? pick.teamId;
      const newAvailable = pickedId
        ? ds.availablePlayerIds.filter((id) => id !== pickedId)
        : ds.availablePlayerIds;

      const nextPick = ds.draft.currentPick + 1;
      const totalPicks = ds.draft.draftOrder.length;
      const isComplete = nextPick > totalPicks;

      const newDraft = {
        ...ds.draft,
        currentPick: nextPick,
        status: isComplete ? ('completed' as const) : ds.draft.status,
        completedAt: isComplete ? new Date().toISOString() : ds.draft.completedAt,
      };

      // If draft is complete, update league status to 'active'
      let leaguesAfterPick = state.leagues;
      if (isComplete) {
        leaguesAfterPick = state.leagues.map((l) =>
          l.id === ds.draft.leagueId
            ? { ...l, status: 'active' as const }
            : l,
        );
      }

      return {
        ...state,
        draftState: {
          draft: newDraft,
          picks: newPicks,
          availablePlayerIds: newAvailable,
        },
        leagues: leaguesAfterPick,
      };
    }
    case 'ADVANCE_DAY': {
      if (state.seasonComplete) return state;
      if (state.roundComplete) return state;

      const newDate = addOneDay(state.simulationDate);
      const newStats = accumulatePlayerStats(
        playerGameLogs as unknown as Record<number, NHLPlayerStats[]>,
        newDate,
      );

      // Check if current round is complete (simulationDate >= lastDate of round)
      const bounds = getRoundDateBounds(state.currentRound);
      const isRoundComplete = bounds ? newDate >= bounds.lastDate : false;

      // If this is round 4 and it's complete, season is done
      const isSeasonComplete = isRoundComplete && state.currentRound === 4;

      return {
        ...state,
        simulationDate: newDate,
        playerStats: newStats,
        roundComplete: isRoundComplete,
        seasonComplete: isSeasonComplete,
      };
    }
    case 'ADVANCE_ROUND': {
      if (!state.roundComplete) return state;
      if (state.seasonComplete) return state;
      if (state.currentRound >= 4) return state;

      const nextRound = state.currentRound + 1;
      const nextBounds = getRoundDateBounds(nextRound);
      // Set simulationDate to the day before the next round's first game
      const dayBeforeNext = nextBounds
        ? (() => {
            const d = new Date(nextBounds.firstDate + 'T12:00:00Z');
            d.setUTCDate(d.getUTCDate() - 1);
            return d.toISOString().slice(0, 10);
          })()
        : state.simulationDate;

      const newStats = accumulatePlayerStats(
        playerGameLogs as unknown as Record<number, NHLPlayerStats[]>,
        dayBeforeNext,
      );

      return {
        ...state,
        currentRound: nextRound,
        simulationDate: dayBeforeNext,
        roundComplete: false,
        playerStats: newStats,
      };
    }
    case 'ACTIVATE_IR':
      return state;
    case 'DEACTIVATE_IR':
      return state;
    default:
      return state;
  }
}

// ── Context ────────────────────────────────────────────────────────────
interface MockDataContextValue {
  state: MockState;
  dispatch: Dispatch<MockAction>;
}

const MockDataContext = createContext<MockDataContextValue | null>(null);

// ── Provider ───────────────────────────────────────────────────────────
export function MockDataProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(mockReducer, undefined, getInitialState);

  return (
    <MockDataContext.Provider value={{ state, dispatch }}>
      <BotAutoPickRunner />
      {children}
    </MockDataContext.Provider>
  );
}

// ── Hook ───────────────────────────────────────────────────────────────
export function useMockData(): MockDataContextValue {
  const ctx = useContext(MockDataContext);
  if (!ctx) {
    throw new Error('useMockData must be used within a MockDataProvider');
  }
  return ctx;
}
