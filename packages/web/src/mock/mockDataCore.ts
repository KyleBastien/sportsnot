import type {
  Draft,
  DraftPick,
  League,
  LeagueMember,
  NHLGame,
  NHLPlayerStats,
  RosterSlot,
} from '@sportsnot/types';
import {
  gamesCf,
  gamesR1,
  gamesR2,
  gamesScf,
  playerGameLogs,
} from '@sportsnot/mock-data';

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

export interface MockDraftState {
  draft: Draft;
  picks: DraftPick[];
  availablePlayerIds: number[];
}

export interface CompletedDraftRecord {
  id: string;
  round: number;
  status: 'completed';
  completed_at: string;
}

export interface MockState {
  leagues: (League & { members: LeagueMember[]; isMock: boolean })[];
  currentLeague: string | null;
  draftState: MockDraftState | null;
  completedDrafts: CompletedDraftRecord[];
  rosters: Record<string, RosterSlot[]>;
  rosterHistory: Record<string, Record<number, RosterSlot[]>>;
  simulationDate: string;
  currentRound: number;
  roundComplete: boolean;
  seasonComplete: boolean;
  playerStats: Record<
    number,
    { goals: number; assists: number; gamesPlayed: number }
  >;
  mockUser: MockUser;
}

const INITIAL_SIMULATION_DATE = '2025-04-18';

const ROUND_GAMES: Record<number, NHLGame[]> = {
  1: gamesR1 as unknown as NHLGame[],
  2: gamesR2 as unknown as NHLGame[],
  3: gamesCf as unknown as NHLGame[],
  4: gamesScf as unknown as NHLGame[],
};

export function getRoundDateBounds(
  round: number
): { firstDate: string; lastDate: string } | null {
  const games = ROUND_GAMES[round];
  if (!games || games.length === 0) {
    return null;
  }
  const dates = games.map((game) => game.gameDate).sort();
  return { firstDate: dates[0], lastDate: dates[dates.length - 1] };
}

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

function addOneDay(dateStr: string): string {
  const date = new Date(dateStr + 'T12:00:00Z');
  date.setUTCDate(date.getUTCDate() + 1);
  return date.toISOString().slice(0, 10);
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
  | {
      type: 'UPDATE_LEAGUE_SETTINGS';
      payload: { leagueId: string; allowIrSlots: boolean };
    }
  | { type: 'RESET_ALL' };

function handleCreateLeague(
  state: MockState,
  action: Extract<MockAction, { type: 'CREATE_LEAGUE' }>
): MockState {
  return {
    ...state,
    leagues: [...state.leagues, action.payload.league],
    currentLeague: action.payload.league.id,
  };
}

function updateLeagues(
  state: MockState,
  updater: (
    league: MockState['leagues'][number]
  ) => MockState['leagues'][number]
): MockState['leagues'] {
  return state.leagues.map(updater);
}

function updateLeagueById(
  state: MockState,
  leagueId: string,
  updater: (
    league: MockState['leagues'][number]
  ) => MockState['leagues'][number]
): MockState['leagues'] {
  return updateLeagues(state, (league) =>
    league.id === leagueId ? updater(league) : league
  );
}

function withUpdatedLeague(
  state: MockState,
  leagueId: string,
  updater: (
    league: MockState['leagues'][number]
  ) => MockState['leagues'][number]
): MockState {
  return {
    ...state,
    leagues: updateLeagueById(state, leagueId, updater),
  };
}

function handleUpdateLeagueSettings(
  state: MockState,
  action: Extract<MockAction, { type: 'UPDATE_LEAGUE_SETTINGS' }>
): MockState {
  return withUpdatedLeague(state, action.payload.leagueId, (league) => ({
    ...league,
    allowIrSlots: action.payload.allowIrSlots,
  }));
}

function handleJoinLeague(
  state: MockState,
  action: Extract<MockAction, { type: 'JOIN_LEAGUE' }>
): MockState {
  return withUpdatedLeague(state, action.payload.leagueId, (league) => ({
    ...league,
    members: [...league.members, action.payload.member],
  }));
}

function handleStartDraft(
  state: MockState,
  action: Extract<MockAction, { type: 'START_DRAFT' }>
): MockState {
  const leagueId = action.payload.draftState.draft.leagueId;
  const draftRound = action.payload.draftState.draft.round;

  return {
    ...state,
    draftState: action.payload.draftState,
    leagues: updateLeagues(state, (league) =>
      league.id === leagueId
        ? { ...league, status: 'drafting' as const, currentRound: draftRound }
        : league
    ),
  };
}

function buildCompletedDraftRosters(
  state: MockState,
  draftState: MockDraftState,
  picks: DraftPick[]
): {
  leagues: MockState['leagues'];
  rosters: MockState['rosters'];
  rosterHistory: MockState['rosterHistory'];
} {
  const updatedLeagues = state.leagues.map((league) =>
    league.id === draftState.draft.leagueId
      ? { ...league, status: 'active' as const }
      : league
  );
  const league = state.leagues.find(
    (entry) => entry.id === draftState.draft.leagueId
  );

  if (!league) {
    return {
      leagues: updatedLeagues,
      rosters: state.rosters,
      rosterHistory: state.rosterHistory,
    };
  }

  const rosters = { ...state.rosters };
  let rosterHistory = state.rosterHistory;

  for (const memberId of league.members.map((member) => member.id)) {
    const memberPicks = picks.filter(
      (pick) => pick.leagueMemberId === memberId
    );
    rosters[memberId] = memberPicks.map((pick, index) => ({
      id: `mock-roster-${memberId}-${index}`,
      leagueMemberId: memberId,
      round: draftState.draft.round,
      playerId: pick.playerId,
      teamId: pick.teamId,
      position: pick.position,
      isActive: !pick.position.startsWith('IR'),
      pointsEarned: 0,
      activatedFromIr: false,
    }));
  }

  if (draftState.draft.round === 3) {
    rosterHistory = { ...state.rosterHistory };
    for (const memberId of league.members.map((member) => member.id)) {
      const roundThreeSlots = rosters[memberId] ?? [];
      rosterHistory[memberId] = {
        ...rosterHistory[memberId],
        4: roundThreeSlots.map((slot, index) => ({
          ...slot,
          id: `mock-roster-r4-${memberId}-${index}`,
          round: 4,
          pointsEarned: 0,
        })),
      };
    }
  }

  return { leagues: updatedLeagues, rosters, rosterHistory };
}

function handleMakePick(
  state: MockState,
  action: Extract<MockAction, { type: 'MAKE_PICK' }>
): MockState {
  if (!state.draftState) {
    return state;
  }

  const picks = [...state.draftState.picks, action.payload.pick];
  const pickedId = action.payload.pick.playerId ?? action.payload.pick.teamId;
  const availablePlayerIds = pickedId
    ? state.draftState.availablePlayerIds.filter((id) => id !== pickedId)
    : state.draftState.availablePlayerIds;
  const nextPick = state.draftState.draft.currentPick + 1;
  const isComplete = nextPick > state.draftState.draft.draftOrder.length;
  const draft = {
    ...state.draftState.draft,
    currentPick: nextPick,
    status: isComplete ? ('completed' as const) : state.draftState.draft.status,
    completedAt: isComplete
      ? new Date().toISOString()
      : state.draftState.draft.completedAt,
  };

  let leagues = state.leagues;
  let rosters = state.rosters;
  let rosterHistory = state.rosterHistory;

  if (isComplete) {
    const completedState = buildCompletedDraftRosters(
      state,
      { ...state.draftState, draft },
      picks
    );
    leagues = completedState.leagues;
    rosters = completedState.rosters;
    rosterHistory = completedState.rosterHistory;
  }

  return {
    ...state,
    draftState: {
      draft,
      picks,
      availablePlayerIds,
    },
    rosters,
    rosterHistory,
    leagues,
    completedDrafts: isComplete
      ? [
          ...state.completedDrafts,
          {
            id: draft.id,
            round: draft.round,
            status: 'completed' as const,
            completed_at: draft.completedAt!,
          },
        ]
      : state.completedDrafts,
  };
}

function handleAdvanceDay(state: MockState): MockState {
  if (state.seasonComplete || state.roundComplete) {
    return state;
  }

  const simulationDate = addOneDay(state.simulationDate);
  const playerStats = accumulatePlayerStats(
    playerGameLogs as unknown as Record<number, NHLPlayerStats[]>,
    simulationDate
  );
  const bounds = getRoundDateBounds(state.currentRound);
  const roundComplete = bounds ? simulationDate >= bounds.lastDate : false;
  const seasonComplete = roundComplete && state.currentRound === 4;

  return {
    ...state,
    simulationDate,
    playerStats,
    roundComplete,
    seasonComplete,
  };
}

function archiveCurrentRosters(state: MockState): MockState['rosterHistory'] {
  const rosterHistory = { ...state.rosterHistory };

  for (const [memberId, slots] of Object.entries(state.rosters)) {
    if (!rosterHistory[memberId]) {
      rosterHistory[memberId] = {};
    }
    if (!rosterHistory[memberId][state.currentRound]) {
      rosterHistory[memberId] = {
        ...rosterHistory[memberId],
        [state.currentRound]: slots,
      };
    }
  }

  return rosterHistory;
}

function getDayBeforeNextRound(nextRound: number, currentDate: string): string {
  const nextBounds = getRoundDateBounds(nextRound);
  if (!nextBounds) {
    return currentDate;
  }

  const date = new Date(nextBounds.firstDate + 'T12:00:00Z');
  date.setUTCDate(date.getUTCDate() - 1);
  return date.toISOString().slice(0, 10);
}

function buildRoundAdvanceRosters(
  state: MockState,
  nextRound: number,
  rosterHistory: MockState['rosterHistory']
): MockState['rosters'] {
  const existingRosterRound = Object.values(state.rosters)[0]?.[0]?.round;
  const rosters = existingRosterRound === nextRound ? { ...state.rosters } : {};

  if (nextRound !== 4 || existingRosterRound === 4) {
    return rosters;
  }

  const hasRoundFourRosters = hasSavedRoundFourRosters(rosterHistory);

  if (hasRoundFourRosters) {
    for (const [memberId, history] of Object.entries(rosterHistory)) {
      if (history[4]) {
        rosters[memberId] = history[4];
      }
    }
    return rosters;
  }

  for (const [memberId, slots] of Object.entries(state.rosters)) {
    rosters[memberId] = slots.map((slot) => ({
      ...slot,
      round: 4,
      pointsEarned: 0,
    }));
  }

  return rosters;
}

function hasSavedRoundFourRosters(
  rosterHistory: MockState['rosterHistory']
): boolean {
  return Object.values(rosterHistory).some((history) => history[4]?.length > 0);
}

function canAdvanceRound(state: MockState): boolean {
  return state.roundComplete && !state.seasonComplete && state.currentRound < 4;
}

function handleAdvanceRound(state: MockState): MockState {
  if (!canAdvanceRound(state)) {
    return state;
  }

  const currentRound = state.currentRound + 1;
  const simulationDate = getDayBeforeNextRound(
    currentRound,
    state.simulationDate
  );
  const playerStats = accumulatePlayerStats(
    playerGameLogs as unknown as Record<number, NHLPlayerStats[]>,
    simulationDate
  );
  const rosterHistory = archiveCurrentRosters(state);

  return {
    ...state,
    currentRound,
    simulationDate,
    roundComplete: false,
    playerStats,
    rosterHistory,
    rosters: buildRoundAdvanceRosters(state, currentRound, rosterHistory),
  };
}

function handleStartNextDraft(
  state: MockState,
  action: Extract<MockAction, { type: 'START_NEXT_DRAFT' }>
): MockState {
  return withUpdatedLeague(state, action.payload.leagueId, (league) => ({
    ...league,
    status: 'drafting' as const,
  }));
}

function handleSkipToRoundFour(
  state: MockState,
  action: Extract<MockAction, { type: 'SKIP_TO_ROUND4' }>
): MockState {
  const leagues = state.leagues.map((league) =>
    league.id === action.payload.leagueId
      ? { ...league, status: 'active' as const, currentRound: 4 }
      : league
  );

  if (
    Object.values(state.rosters).some((slots) =>
      slots.some((slot) => slot.round === 4)
    )
  ) {
    return { ...state, leagues };
  }

  const rosterHistory = { ...state.rosterHistory };
  for (const [memberId, slots] of Object.entries(state.rosters)) {
    rosterHistory[memberId] = {
      ...rosterHistory[memberId],
      3: slots,
    };
  }

  const rosters: Record<string, RosterSlot[]> = {};
  for (const [memberId, slots] of Object.entries(state.rosters)) {
    rosters[memberId] = slots.map((slot) => ({
      ...slot,
      round: 4,
      pointsEarned: 0,
    }));
  }

  return {
    ...state,
    leagues,
    rosterHistory,
    rosters,
  };
}

function handleStartRedraft(
  state: MockState,
  action: Extract<MockAction, { type: 'START_RE_DRAFT' }>
): MockState {
  const rosterHistory = { ...state.rosterHistory };

  if (state.currentRound < action.payload.draftState.draft.round) {
    for (const [memberId, slots] of Object.entries(state.rosters)) {
      rosterHistory[memberId] = {
        ...rosterHistory[memberId],
        [state.currentRound]: slots,
      };
    }
  }

  return {
    ...state,
    draftState: action.payload.draftState,
    leagues: updateLeagues(state, (league) =>
      league.id === action.payload.leagueId
        ? {
            ...league,
            status: 'drafting' as const,
            currentRound: action.payload.draftState.draft.round,
          }
        : league
    ),
    rosterHistory,
  };
}

function handleUpdateProfile(
  state: MockState,
  action: Extract<MockAction, { type: 'UPDATE_PROFILE' }>
): MockState {
  return {
    ...state,
    mockUser: {
      ...state.mockUser,
      displayName: action.payload.displayName,
    },
  };
}

function findIrReplacementSlot(
  memberSlots: RosterSlot[],
  irSlot: RosterSlot,
  slotId: string
): RosterSlot | undefined {
  const matchingPosition = irSlot.position === 'IR_F' ? 'F' : 'D';
  return memberSlots.find(
    (slot) =>
      slot.position === matchingPosition && slot.isActive && slot.id !== slotId
  );
}

function handleActivateIr(
  state: MockState,
  action: Extract<MockAction, { type: 'ACTIVATE_IR' }>
): MockState {
  const memberSlots = state.rosters[action.payload.leagueMemberId];
  if (!memberSlots) {
    return state;
  }

  const irSlot = memberSlots.find((slot) => slot.id === action.payload.slotId);
  if (!irSlot) {
    return state;
  }

  const injuredSlot = findIrReplacementSlot(
    memberSlots,
    irSlot,
    action.payload.slotId
  );

  return {
    ...state,
    rosters: {
      ...state.rosters,
      [action.payload.leagueMemberId]: memberSlots.map((slot) => {
        if (slot.id === action.payload.slotId) {
          return { ...slot, isActive: true, activatedFromIr: true };
        }
        if (injuredSlot && slot.id === injuredSlot.id) {
          return { ...slot, isActive: false };
        }
        return slot;
      }),
    },
  };
}

function handleDeactivateIr(
  state: MockState,
  action: Extract<MockAction, { type: 'DEACTIVATE_IR' }>
): MockState {
  const memberSlots = state.rosters[action.payload.leagueMemberId];
  if (!memberSlots) {
    return state;
  }

  return {
    ...state,
    rosters: {
      ...state.rosters,
      [action.payload.leagueMemberId]: memberSlots.map((slot) =>
        slot.id === action.payload.slotId
          ? { ...slot, isActive: false, activatedFromIr: false }
          : slot
      ),
    },
  };
}

export function mockReducer(state: MockState, action: MockAction): MockState {
  const handlers: Record<MockAction['type'], () => MockState> = {
    RESET_ALL: () => getInitialState(),
    CREATE_LEAGUE: () =>
      handleCreateLeague(
        state,
        action as Extract<MockAction, { type: 'CREATE_LEAGUE' }>
      ),
    UPDATE_LEAGUE_SETTINGS: () =>
      handleUpdateLeagueSettings(
        state,
        action as Extract<MockAction, { type: 'UPDATE_LEAGUE_SETTINGS' }>
      ),
    JOIN_LEAGUE: () =>
      handleJoinLeague(
        state,
        action as Extract<MockAction, { type: 'JOIN_LEAGUE' }>
      ),
    START_DRAFT: () =>
      handleStartDraft(
        state,
        action as Extract<MockAction, { type: 'START_DRAFT' }>
      ),
    MAKE_PICK: () =>
      handleMakePick(
        state,
        action as Extract<MockAction, { type: 'MAKE_PICK' }>
      ),
    ADVANCE_DAY: () => handleAdvanceDay(state),
    ADVANCE_ROUND: () => handleAdvanceRound(state),
    ACTIVATE_IR: () =>
      handleActivateIr(
        state,
        action as Extract<MockAction, { type: 'ACTIVATE_IR' }>
      ),
    DEACTIVATE_IR: () =>
      handleDeactivateIr(
        state,
        action as Extract<MockAction, { type: 'DEACTIVATE_IR' }>
      ),
    START_NEXT_DRAFT: () =>
      handleStartNextDraft(
        state,
        action as Extract<MockAction, { type: 'START_NEXT_DRAFT' }>
      ),
    SKIP_TO_ROUND4: () =>
      handleSkipToRoundFour(
        state,
        action as Extract<MockAction, { type: 'SKIP_TO_ROUND4' }>
      ),
    START_RE_DRAFT: () =>
      handleStartRedraft(
        state,
        action as Extract<MockAction, { type: 'START_RE_DRAFT' }>
      ),
    UPDATE_PROFILE: () =>
      handleUpdateProfile(
        state,
        action as Extract<MockAction, { type: 'UPDATE_PROFILE' }>
      ),
  };

  return handlers[action.type]();
}
