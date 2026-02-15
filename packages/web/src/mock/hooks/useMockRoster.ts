import { useMockData } from '../MockDataProvider';
import { SCORING } from '@sportsnot/types';
import { playerGameLogs } from '@sportsnot/mock-data';
import type { NHLPlayerStats } from '@sportsnot/types';

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

// ── Points calculation helper ──────────────────────────────────────────
function calculatePlayerPoints(playerId: number, throughDate: string): number {
  const logs = (playerGameLogs as unknown as Record<number, NHLPlayerStats[]>)[
    playerId
  ];
  if (!logs) return 0;

  let points = 0;
  for (const entry of logs) {
    if (entry.gameDate <= throughDate) {
      points += entry.goals * SCORING.goal;
      points += entry.assists * SCORING.assist;
    }
  }
  return points;
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

  // Map to Supabase snake_case and compute points_earned through simulationDate
  const slots = memberSlots.map((slot) => ({
    id: slot.id,
    league_member_id: slot.leagueMemberId,
    round: slot.round,
    player_id: slot.playerId ?? null,
    team_id: slot.teamId ?? null,
    position: slot.position,
    is_active: slot.isActive,
    points_earned: slot.playerId
      ? calculatePlayerPoints(slot.playerId, state.simulationDate)
      : 0,
    activated_from_ir: slot.activatedFromIr,
  }));

  return makeMockQuery({
    memberId: member.id,
    round: state.currentRound,
    slots,
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

  const allRosters = league.members.flatMap((member) => {
    const memberSlots = state.rosters[member.id] ?? [];
    return memberSlots.map((slot) => ({
      id: slot.id,
      league_member_id: slot.leagueMemberId,
      round: slot.round,
      player_id: slot.playerId ?? null,
      team_id: slot.teamId ?? null,
      position: slot.position,
      is_active: slot.isActive,
      points_earned: slot.playerId
        ? calculatePlayerPoints(slot.playerId, state.simulationDate)
        : 0,
      activated_from_ir: slot.activatedFromIr,
      league_members: {
        id: member.id,
        user_id: member.userId,
        team_name: member.teamName,
        league_id: leagueId,
      },
    }));
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
