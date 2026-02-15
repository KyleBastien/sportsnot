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
} from '@sportsnot/types';

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
    case 'START_DRAFT':
      return state;
    case 'MAKE_PICK':
      return state;
    case 'ADVANCE_DAY':
      return state;
    case 'ADVANCE_ROUND':
      return state;
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
