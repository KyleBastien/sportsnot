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
import { mockHooksRegistry, type MockHooksRegistry } from './mockHooksRegistry';

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

// ── Completed draft record ─────────────────────────────────────────────
export interface CompletedDraftRecord {
  id: string;
  round: number;
  status: 'completed';
  completed_at: string;
}

// ── State shape ────────────────────────────────────────────────────────
export interface MockState {
  leagues: (League & { members: LeagueMember[]; isMock: boolean })[];
  currentLeague: string | null;
  draftState: MockDraftState | null;
  completedDrafts: CompletedDraftRecord[]; // history of completed drafts
  rosters: Record<string, RosterSlot[]>; // keyed by leagueMemberId (current round)
  rosterHistory: Record<string, Record<number, RosterSlot[]>>; // memberId → round → slots
  simulationDate: string; // ISO date string
  currentRound: number; // 1-4
  roundComplete: boolean;
  seasonComplete: boolean;
  playerStats: Record<
    number,
    { goals: number; assists: number; gamesPlayed: number }
  >;
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
export function getRoundDateBounds(
  round: number
): { firstDate: string; lastDate: string } | null {
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
  throughDate: string
): Record<number, { goals: number; assists: number; gamesPlayed: number }> {
  const result: Record<
    number,
    { goals: number; assists: number; gamesPlayed: number }
  > = {};
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

export function getInitialState(): MockState {
  return {
    leagues: [],
    currentLeague: null,
    draftState: null,
    completedDrafts: [],
    rosters: {},
    rosterHistory: {},
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
  | {
      type: 'DEACTIVATE_IR';
      payload: { leagueMemberId: string; slotId: string };
    }
  | {
      type: 'START_NEXT_DRAFT';
      payload: { leagueId: string };
    }
  | {
      type: 'SKIP_TO_ROUND4';
      payload: { leagueId: string };
    }
  | {
      type: 'START_RE_DRAFT';
      payload: { leagueId: string; draftState: MockDraftState };
    }
  | { type: 'UPDATE_PROFILE'; payload: { displayName: string } }
  | { type: 'RESET_ALL' };

// ── Reducer ────────────────────────────────────────────────────────────
export function mockReducer(state: MockState, action: MockAction): MockState {
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
          : l
      );
      return { ...state, leagues: updated };
    }
    case 'START_DRAFT': {
      const leagueId = action.payload.draftState.draft.leagueId;
      const draftRound = action.payload.draftState.draft.round;
      const updatedLeagues = state.leagues.map((l) =>
        l.id === leagueId
          ? {
              ...l,
              status: 'drafting' as const,
              currentRound: draftRound,
            }
          : l
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
        completedAt: isComplete
          ? new Date().toISOString()
          : ds.draft.completedAt,
      };

      // If draft is complete, update league status to 'active' and populate rosters
      let leaguesAfterPick = state.leagues;
      let rostersAfterPick = state.rosters;
      let historyAfterPick = state.rosterHistory;
      if (isComplete) {
        leaguesAfterPick = state.leagues.map((l) =>
          l.id === ds.draft.leagueId ? { ...l, status: 'active' as const } : l
        );

        // Build rosters from all draft picks, grouped by league member
        const league = state.leagues.find((l) => l.id === ds.draft.leagueId);
        if (league) {
          const allPicks = newPicks;
          const memberIds = league.members.map((m) => m.id);
          rostersAfterPick = { ...state.rosters };
          for (const memberId of memberIds) {
            const memberPicks = allPicks.filter(
              (p) => p.leagueMemberId === memberId
            );
            const slots: RosterSlot[] = memberPicks.map((p, idx) => ({
              id: `mock-roster-${memberId}-${idx}`,
              leagueMemberId: memberId,
              round: ds.draft.round,
              playerId: p.playerId,
              teamId: p.teamId,
              position: p.position,
              isActive: !p.position.startsWith('IR'),
              pointsEarned: 0,
              activatedFromIr: false,
            }));
            rostersAfterPick[memberId] = slots;
          }

          // R3 draft covers both Conference Finals and Stanley Cup Final:
          // pre-create R4 roster slots so scoring works immediately.
          if (ds.draft.round === 3) {
            historyAfterPick = { ...state.rosterHistory };
            for (const memberId of memberIds) {
              const r3Slots = rostersAfterPick[memberId] ?? [];
              const r4Slots: RosterSlot[] = r3Slots.map((s, idx) => ({
                ...s,
                id: `mock-roster-r4-${memberId}-${idx}`,
                round: 4,
                pointsEarned: 0,
              }));
              historyAfterPick[memberId] = {
                ...historyAfterPick[memberId],
                [4]: r4Slots,
              };
            }
          }
        }
      }

      // Track completed draft
      let newCompletedDrafts = state.completedDrafts;
      if (isComplete) {
        newCompletedDrafts = [
          ...state.completedDrafts,
          {
            id: newDraft.id,
            round: newDraft.round,
            status: 'completed' as const,
            completed_at: newDraft.completedAt!,
          },
        ];
      }

      return {
        ...state,
        draftState: {
          draft: newDraft,
          picks: newPicks,
          availablePlayerIds: newAvailable,
        },
        rosters: rostersAfterPick,
        rosterHistory: historyAfterPick,
        leagues: leaguesAfterPick,
        completedDrafts: newCompletedDrafts,
      };
    }
    case 'ADVANCE_DAY': {
      if (state.seasonComplete) return state;
      if (state.roundComplete) return state;

      const newDate = addOneDay(state.simulationDate);
      const newStats = accumulatePlayerStats(
        playerGameLogs as unknown as Record<number, NHLPlayerStats[]>,
        newDate
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
        dayBeforeNext
      );

      // Archive current rosters to rosterHistory keyed by round
      // Skip if already archived (e.g., by START_RE_DRAFT)
      const updatedHistory = { ...state.rosterHistory };
      for (const [memberId, slots] of Object.entries(state.rosters)) {
        if (!updatedHistory[memberId]) {
          updatedHistory[memberId] = {};
        }
        if (!updatedHistory[memberId][state.currentRound]) {
          updatedHistory[memberId] = {
            ...updatedHistory[memberId],
            [state.currentRound]: slots,
          };
        }
      }

      // Preserve rosters if a re-draft already populated them for the next round
      const existingRosterRound = Object.values(state.rosters)[0]?.[0]?.round;
      let newRosters: Record<string, RosterSlot[]> =
        existingRosterRound === nextRound ? { ...state.rosters } : {};

      // Round 3→4: use pre-created R4 rosters from history (created at R3 draft
      // completion) or fall back to copying R3 rosters.
      if (nextRound === 4 && existingRosterRound !== 4) {
        const preCreatedR4 = Object.entries(updatedHistory).some(
          ([, h]) => h[4]?.length > 0
        );
        if (preCreatedR4) {
          for (const [memberId, history] of Object.entries(updatedHistory)) {
            if (history[4]) {
              newRosters[memberId] = history[4];
            }
          }
        } else {
          for (const [memberId, slots] of Object.entries(state.rosters)) {
            newRosters[memberId] = slots.map((s) => ({
              ...s,
              round: 4,
              pointsEarned: 0,
            }));
          }
        }
      }

      return {
        ...state,
        currentRound: nextRound,
        simulationDate: dayBeforeNext,
        roundComplete: false,
        playerStats: newStats,
        rosterHistory: updatedHistory,
        rosters: newRosters,
      };
    }
    case 'START_NEXT_DRAFT': {
      const { leagueId } = action.payload;
      const updatedLeagues = state.leagues.map((l) =>
        l.id === leagueId ? { ...l, status: 'drafting' as const } : l
      );
      return { ...state, leagues: updatedLeagues };
    }
    case 'SKIP_TO_ROUND4': {
      const { leagueId } = action.payload;
      const updatedLeagues = state.leagues.map((l) =>
        l.id === leagueId
          ? { ...l, status: 'active' as const, currentRound: 4 }
          : l
      );

      // Idempotent: check if R4 rosters already exist (ADVANCE_ROUND already ran)
      const hasR4Rosters = Object.values(state.rosters).some((slots) =>
        slots.some((s) => s.round === 4)
      );
      if (hasR4Rosters) {
        return { ...state, leagues: updatedLeagues };
      }

      // Archive current R3 rosters to rosterHistory
      const updatedHistory = { ...state.rosterHistory };
      for (const [memberId, slots] of Object.entries(state.rosters)) {
        if (!updatedHistory[memberId]) {
          updatedHistory[memberId] = {};
        }
        updatedHistory[memberId] = {
          ...updatedHistory[memberId],
          [3]: slots,
        };
      }

      // Copy R3 rosters into R4 with reset points
      const newRosters: Record<string, RosterSlot[]> = {};
      for (const [memberId, slots] of Object.entries(state.rosters)) {
        newRosters[memberId] = slots.map((s) => ({
          ...s,
          round: 4,
          pointsEarned: 0,
        }));
      }

      return {
        ...state,
        leagues: updatedLeagues,
        rosterHistory: updatedHistory,
        rosters: newRosters,
      };
    }
    case 'START_RE_DRAFT': {
      const { leagueId, draftState } = action.payload;
      const updatedLeagues = state.leagues.map((l) =>
        l.id === leagueId
          ? {
              ...l,
              status: 'drafting' as const,
              currentRound: draftState.draft.round,
            }
          : l
      );

      // Archive current rosters before the re-draft can overwrite them
      const updatedHistory = { ...state.rosterHistory };
      if (state.currentRound < draftState.draft.round) {
        for (const [memberId, slots] of Object.entries(state.rosters)) {
          if (!updatedHistory[memberId]) {
            updatedHistory[memberId] = {};
          }
          updatedHistory[memberId] = {
            ...updatedHistory[memberId],
            [state.currentRound]: slots,
          };
        }
      }

      return {
        ...state,
        draftState,
        leagues: updatedLeagues,
        rosterHistory: updatedHistory,
      };
    }
    case 'UPDATE_PROFILE': {
      return {
        ...state,
        mockUser: {
          ...state.mockUser,
          displayName: action.payload.displayName,
        },
      };
    }
    case 'ACTIVATE_IR': {
      const { leagueMemberId, slotId } = action.payload;
      const memberSlots = state.rosters[leagueMemberId];
      if (!memberSlots) return state;

      const irSlot = memberSlots.find((s) => s.id === slotId);
      if (!irSlot) return state;

      // Find matching position for the IR slot (IR_F -> F, IR_D -> D)
      const matchingPos = irSlot.position === 'IR_F' ? 'F' : 'D';

      // Find an active player at the matching position to deactivate (the injured one)
      const injuredSlot = memberSlots.find(
        (s) => s.position === matchingPos && s.isActive && s.id !== slotId
      );

      const updatedSlots = memberSlots.map((s) => {
        if (s.id === slotId) {
          return { ...s, isActive: true, activatedFromIr: true };
        }
        if (injuredSlot && s.id === injuredSlot.id) {
          return { ...s, isActive: false };
        }
        return s;
      });

      return {
        ...state,
        rosters: { ...state.rosters, [leagueMemberId]: updatedSlots },
      };
    }
    case 'DEACTIVATE_IR': {
      const { leagueMemberId: memberId, slotId: deactivateSlotId } =
        action.payload;
      const slots = state.rosters[memberId];
      if (!slots) return state;

      const updatedIrSlots = slots.map((s) => {
        if (s.id === deactivateSlotId) {
          return { ...s, isActive: false, activatedFromIr: false };
        }
        return s;
      });

      return {
        ...state,
        rosters: { ...state.rosters, [memberId]: updatedIrSlots },
      };
    }
    default:
      return state;
  }
}

// ── Context ────────────────────────────────────────────────────────────
interface MockDataContextValue {
  state: MockState;
  dispatch: Dispatch<MockAction>;
  hooks: MockHooksRegistry;
}

const MockDataContext = createContext<MockDataContextValue | null>(null);

// ── Provider ───────────────────────────────────────────────────────────
export function MockDataProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(mockReducer, undefined, getInitialState);

  return (
    <MockDataContext.Provider
      value={{ state, dispatch, hooks: mockHooksRegistry }}
    >
      <BotAutoPickRunner />
      {children}
    </MockDataContext.Provider>
  );
}

// Safe empty state for when MockDataProvider is not mounted (non-mock mode).
// This allows mock hooks to be called unconditionally without violating
// react-hooks/rules-of-hooks, while returning harmless empty data.
const EMPTY_MOCK_STATE: MockState = {
  leagues: [],
  currentLeague: null,
  draftState: null,
  completedDrafts: [],
  rosters: {},
  rosterHistory: {},
  simulationDate: '',
  currentRound: 1,
  roundComplete: false,
  seasonComplete: false,
  playerStats: {},
  mockUser: { id: '', email: '', displayName: '', avatarUrl: '' },
};

const EMPTY_CONTEXT: MockDataContextValue = {
  state: EMPTY_MOCK_STATE,
  dispatch: () => {},
  hooks: mockHooksRegistry,
};

// ── Hook ───────────────────────────────────────────────────────────────
export function useMockData(): MockDataContextValue {
  const ctx = useContext(MockDataContext);
  return ctx ?? EMPTY_CONTEXT;
}
