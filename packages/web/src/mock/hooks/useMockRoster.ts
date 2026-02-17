import { useMockData, getRoundDateBounds } from '../MockDataProvider';
import { getEliminatedAbbreviations } from './useMockNhlApi';
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
// matching the inline useMyRoster in RosterPage.tsx
export function useMockRoster(leagueId: string | undefined) {
  const { state } = useMockData();

  if (!leagueId) {
    return makeMockQuery(null);
  }

  const league = state.leagues.find((l) => l.id === leagueId);
  if (!league) {
    return makeMockQuery(null);
  }

  // Find the mock user's member entry
  const member = league.members.find((m) => m.userId === state.mockUser.id);
  if (!member) {
    return makeMockQuery(null);
  }

  const memberSlots = state.rosters[member.id] ?? [];

  // For Round 4, determine which slots are eliminated
  const eliminatedAbbrs =
    state.currentRound === 4
      ? getEliminatedAbbreviations(4)
      : new Set<string>();

  // Map to Supabase snake_case and compute points_earned through simulationDate
  const slots = memberSlots.map((slot) => {
    const eliminated =
      state.currentRound === 4 && isSlotEliminated(slot, eliminatedAbbrs);

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
    };
  });

  const pts = calculateMemberPoints(state, member.id);

  return makeMockQuery({
    memberId: member.id,
    round: state.currentRound,
    slots,
    totalPoints: pts.totalPoints,
  });
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

  const eliminatedAbbrs =
    state.currentRound === 4
      ? getEliminatedAbbreviations(4)
      : new Set<string>();

  const allRosters = league.members.flatMap((member) => {
    const memberSlots = state.rosters[member.id] ?? [];
    return memberSlots.map((slot) => {
      const eliminated =
        state.currentRound === 4 && isSlotEliminated(slot, eliminatedAbbrs);

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
