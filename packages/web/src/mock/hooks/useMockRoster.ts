import { useMockData, getRoundDateBounds } from '../MockDataProvider';
import { getEliminatedAbbreviations } from './useMockNhlApi';
import { clampRoundSelection } from '../../app/utils/roundUtils';
import {
  isSlotEliminated,
  calculateRoundMemberPoints,
  calculateMemberPoints,
} from '../utils';

// ── Mock TanStack helpers (same pattern as useMockDraft) ────────────────
interface MockQueryResult<T> {
  data: T;
  isLoading: false;
  isError: false;
  error: null;
  isFetching: false;
  isSuccess: true;
  status: 'success';
  refetch: () => Promise<MockQueryResult<T>>;
}

function makeMockQuery<T>(data: T): MockQueryResult<T> {
  const result: MockQueryResult<T> = {
    data,
    isLoading: false,
    isError: false,
    error: null,
    isFetching: false,
    isSuccess: true,
    status: 'success',
    refetch: () => Promise.resolve(result),
  };
  return result;
}

interface MockMutationResult<TData, TVariables> {
  mutateAsync: (v: TVariables) => Promise<TData>;
  mutate: (v: TVariables) => void;
  isLoading: false;
  isPending: false;
  isError: false;
  error: null;
  isSuccess: false;
  data: undefined;
  status: 'idle';
}

function makeMockMutation<TData, TVariables>(
  fn: (v: TVariables) => TData
): MockMutationResult<TData, TVariables> {
  return {
    mutateAsync: (v) => Promise.resolve(fn(v)),
    mutate: (v) => {
      fn(v);
    },
    isLoading: false,
    isPending: false,
    isError: false,
    error: null,
    isSuccess: false,
    data: undefined,
    status: 'idle',
  };
}

// ── Per-slot points using round-specific date bounds ───────────────────
export function calculateSlotPoints(
  slot: { round: number; playerId?: number | null; teamId?: number | null },
  simulationDate: string
): number {
  const bounds = getRoundDateBounds(slot.round);
  if (!bounds) return 0;
  if (simulationDate < bounds.firstDate) return 0;

  const throughDate =
    simulationDate < bounds.lastDate ? simulationDate : bounds.lastDate;

  const playerIds = slot.playerId ? [slot.playerId] : [];
  const goalieTeamIds = !slot.playerId && slot.teamId ? [slot.teamId] : [];

  const pts = calculateRoundMemberPoints(
    playerIds,
    goalieTeamIds,
    bounds.firstDate,
    throughDate
  );
  return pts.playerPts + pts.goaliePts;
}

// ── useRoster (mock) ───────────────────────────────────────────────────
// Returns roster for a specific league member in Supabase snake_case shape
// matching the inline useMemberRoster in RosterPage.tsx.
// When leagueMemberId is provided, returns that member's roster;
// otherwise falls back to the mock user's roster.
export function useMockRoster(
  leagueId: string | undefined,
  leagueMemberId?: string,
  requestedRound?: number
) {
  const { state } = useMockData();

  if (!leagueId) {
    return makeMockQuery(null);
  }

  const league = state.leagues.find((l) => l.id === leagueId);
  if (!league) {
    return makeMockQuery(null);
  }

  const member = findMockRosterMember(
    league.members,
    leagueMemberId,
    state.mockUser.id
  );
  if (!member) {
    return makeMockQuery(null);
  }

  const selectedRound = getSelectedMockRound(
    requestedRound,
    state.currentRound
  );
  const slots = buildMockRosterSlots(state, member.id, selectedRound);

  const pts = calculateMemberPoints(state, member.id, selectedRound);

  return makeMockQuery({
    memberId: member.id,
    currentRound: state.currentRound,
    round: selectedRound,
    slots,
    totalPoints: pts.totalPoints,
    isHistorical: selectedRound !== state.currentRound,
  });
}

function findMockRosterMember(
  members: Array<{ id: string; userId: string }>,
  leagueMemberId: string | undefined,
  mockUserId: string
) {
  if (leagueMemberId) {
    return members.find((member) => member.id === leagueMemberId);
  }

  return members.find((member) => member.userId === mockUserId);
}

function getSelectedMockRound(
  requestedRound: number | undefined,
  currentRound: number
) {
  return clampRoundSelection(requestedRound ?? currentRound, currentRound);
}

function resolveMockRoundSlots(
  state: ReturnType<typeof useMockData>['state'],
  memberId: string,
  selectedRound: number
) {
  const memberSlots = state.rosters[memberId] ?? [];
  const rosterMatchesRound =
    memberSlots.length === 0 || memberSlots[0].round === selectedRound;

  if (selectedRound === state.currentRound && rosterMatchesRound) {
    return memberSlots;
  }

  return state.rosterHistory[memberId]?.[selectedRound] ?? [];
}

function buildMockRosterSlots(
  state: ReturnType<typeof useMockData>['state'],
  memberId: string,
  selectedRound: number
) {
  const eliminatedAbbrs = getEliminatedAbbreviations(selectedRound + 1);
  const selectedSlots = resolveMockRoundSlots(state, memberId, selectedRound);

  return selectedSlots.map((slot) =>
    buildMockRosterSlot(slot, eliminatedAbbrs, state.simulationDate)
  );
}

function buildMockRosterSlot(
  slot: {
    id: string;
    leagueMemberId: string;
    round: number;
    playerId?: number | null;
    teamId?: number | null;
    position: string;
    isActive: boolean;
    activatedFromIr: boolean;
  },
  eliminatedAbbrs: Set<string>,
  simulationDate: string
) {
  const eliminated = isSlotEliminated(
    {
      playerId: slot.playerId ?? undefined,
      teamId: slot.teamId ?? undefined,
    },
    eliminatedAbbrs
  );

  return {
    id: slot.id,
    league_member_id: slot.leagueMemberId,
    round: slot.round,
    player_id: slot.playerId ?? null,
    team_id: slot.teamId ?? null,
    position: slot.position,
    is_active: slot.isActive,
    points_earned: eliminated ? 0 : calculateSlotPoints(slot, simulationDate),
    activated_from_ir: slot.activatedFromIr,
    is_eliminated: eliminated,
  };
}

// ── useLeagueRosters (mock) ────────────────────────────────────────────
// Returns all rosters for all members in a league
export function useMockLeagueRosters(leagueId: string | undefined) {
  const { state } = useMockData();

  if (!leagueId) {
    return makeMockQuery([]);
  }

  const league = state.leagues.find((l) => l.id === leagueId);
  if (!league) {
    return makeMockQuery([]);
  }

  const eliminatedAbbrs = getEliminatedAbbreviations(state.currentRound + 1);

  const allRosters = league.members.flatMap((member) => {
    const memberSlots = state.rosters[member.id] ?? [];
    return memberSlots.map((slot) => {
      const eliminated = isSlotEliminated(slot, eliminatedAbbrs);

      return {
        id: slot.id,
        league_member_id: slot.leagueMemberId,
        round: slot.round,
        player_id: slot.playerId ?? null,
        team_id: slot.teamId ?? null,
        position: slot.position,
        is_active: slot.isActive,
        points_earned: eliminated
          ? 0
          : calculateSlotPoints(slot, state.simulationDate),
        activated_from_ir: slot.activatedFromIr,
        is_eliminated: eliminated,
        league_members: {
          id: member.id,
          user_id: member.userId,
          team_name: member.teamName,
          league_id: leagueId,
        },
      };
    });
  });

  return makeMockQuery(allRosters);
}

// ── useActivateIR (mock) ───────────────────────────────────────────────
export function useMockActivateIR() {
  const { dispatch } = useMockData();

  return makeMockMutation(
    (params: { leagueMemberId: string; slotId: string }) => {
      dispatch({
        type: 'ACTIVATE_IR',
        payload: {
          leagueMemberId: params.leagueMemberId,
          slotId: params.slotId,
        },
      });
    }
  );
}

// ── useDeactivateIR (mock) ─────────────────────────────────────────────
export function useMockDeactivateIR() {
  const { dispatch } = useMockData();

  return makeMockMutation(
    (params: { leagueMemberId: string; slotId: string }) => {
      dispatch({
        type: 'DEACTIVATE_IR',
        payload: {
          leagueMemberId: params.leagueMemberId,
          slotId: params.slotId,
        },
      });
    }
  );
}
