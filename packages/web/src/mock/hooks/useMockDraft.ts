import { useMockData, type MockDraftState } from '../MockDataProvider';
import type { DraftPick, Position } from '@sportsnot/types';
import { players } from '@sportsnot/mock-data';

// ── Mock TanStack helpers (same pattern as useMockLeagues) ──────────────
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

/* eslint-disable no-unused-vars */
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
/* eslint-enable no-unused-vars */

function makeMockMutation<TData, TVariables>(
  // eslint-disable-next-line no-unused-vars
  fn: (v: TVariables) => TData,
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

// ── All draftable player IDs from fixture data ─────────────────────────
const ALL_PLAYER_IDS: number[] = Object.values(players)
  .flat()
  .map((p) => p.id);

// ── Snake draft order generator ────────────────────────────────────────
// For N members and T total picks, generates a snake order:
// Round 1: 1,2,3,...N  Round 2: N,...,3,2,1  Round 3: 1,2,3,...N  etc.
export function generateSnakeDraftOrder(
  memberUserIds: string[],
  totalRounds: number,
): string[] {
  const order: string[] = [];
  for (let round = 0; round < totalRounds; round++) {
    const roundOrder =
      round % 2 === 0 ? [...memberUserIds] : [...memberUserIds].reverse();
    order.push(...roundOrder);
  }
  return order;
}

// ── useDraft ───────────────────────────────────────────────────────────
// Returns current draft state in the same shape as the Supabase useDraft
// query: { id, league_id, round, status, current_pick, draft_order, draft_picks[] }
export function useMockDraft(leagueId: string | undefined) {
  const { state } = useMockData();

  if (!leagueId || !state.draftState) {
    return makeMockQuery(null);
  }

  const ds = state.draftState;
  const league = state.leagues.find((l) => l.id === leagueId);

  // Map picks to Supabase snake_case shape with nested league_members
  const draftPicks = ds.picks.map((pick) => {
    const member = league?.members.find((m) => m.id === pick.leagueMemberId);
    return {
      id: pick.id,
      draft_id: pick.draftId,
      league_member_id: pick.leagueMemberId,
      pick_number: pick.pickNumber,
      player_id: pick.playerId ?? null,
      team_id: pick.teamId ?? null,
      position: pick.position,
      picked_at: pick.pickedAt,
      league_members: member
        ? { team_name: member.teamName, user_id: member.userId }
        : null,
    };
  });

  const data = {
    id: ds.draft.id,
    league_id: ds.draft.leagueId,
    round: ds.draft.round,
    status: ds.draft.status,
    current_pick: ds.draft.currentPick,
    draft_order: ds.draft.draftOrder,
    started_at: ds.draft.startedAt ?? null,
    completed_at: ds.draft.completedAt ?? null,
    draft_picks: draftPicks,
  };

  return makeMockQuery(data);
}

// ── useStartDraft ──────────────────────────────────────────────────────
export function useMockStartDraft() {
  const { state, dispatch } = useMockData();

  return makeMockMutation(
    (params: { leagueId: string; round: number; draftOrder?: string[] }) => {
      const league = state.leagues.find((l) => l.id === params.leagueId);
      if (!league) throw new Error('League not found');

      const memberUserIds = league.members.map((m) => m.userId);

      // Default: 10 rounds of snake draft (5F + 3D + 2G = 10 roster slots)
      const totalDraftRounds = 10;
      const draftOrder =
        params.draftOrder ??
        generateSnakeDraftOrder(memberUserIds, totalDraftRounds);

      const draftId = `mock-draft-${params.leagueId}-${Date.now()}`;

      const draftState: MockDraftState = {
        draft: {
          id: draftId,
          leagueId: params.leagueId,
          round: params.round,
          status: 'active',
          currentPick: 1,
          draftOrder,
          startedAt: new Date().toISOString(),
        },
        picks: [],
        availablePlayerIds: [...ALL_PLAYER_IDS],
      };

      dispatch({ type: 'START_DRAFT', payload: { draftState } });

      return {
        id: draftId,
        league_id: params.leagueId,
        round: params.round,
        status: 'active' as const,
        current_pick: 1,
        draft_order: draftOrder,
      };
    },
  );
}

// ── useMakePick ────────────────────────────────────────────────────────
export function useMockMakePick() {
  const { dispatch } = useMockData();

  return makeMockMutation(
    (params: {
      draftId: string;
      leagueMemberId: string;
      pickNumber: number;
      playerId: number | null;
      teamId: number | null;
      position: string;
    }) => {
      const pick: DraftPick = {
        id: `mock-pick-${params.draftId}-${params.pickNumber}`,
        draftId: params.draftId,
        leagueMemberId: params.leagueMemberId,
        pickNumber: params.pickNumber,
        playerId: params.playerId ?? undefined,
        teamId: params.teamId ?? undefined,
        position: params.position as Position,
        pickedAt: new Date().toISOString(),
      };

      dispatch({ type: 'MAKE_PICK', payload: { pick } });
    },
  );
}

// ── useLeagueMembers (mock) ────────────────────────────────────────────
// Returns league members in the Supabase snake_case shape consumed by DraftPage
export function useMockLeagueMembers(leagueId: string | undefined) {
  const { state } = useMockData();

  const league = leagueId
    ? state.leagues.find((l) => l.id === leagueId)
    : null;

  const data = league
    ? league.members.map((m) => ({
        id: m.id,
        user_id: m.userId,
        team_name: m.teamName,
        total_points: m.totalPoints,
        users: m.user
          ? { display_name: m.user.displayName }
          : null,
      }))
    : [];

  return makeMockQuery(data);
}
