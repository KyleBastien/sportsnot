import { useMockData, type MockState } from '../MockDataProvider';
import type { LeagueMember, User } from '@sportsnot/types';
import { players } from '@sportsnot/mock-data';

// ── Bot name pool ──────────────────────────────────────────────────────
// Use real NHL player names from fixture data for realistic bot names.
const BOT_NAMES: string[] = Object.values(players)
  .flat()
  .map((p) => p.fullName);

function makeBotUser(id: string, name: string): User {
  const now = new Date().toISOString();
  return {
    id,
    email: `${id}@bot.sportsnot.dev`,
    displayName: name,
    avatarUrl: '',
    createdAt: now,
    updatedAt: now,
  };
}

function generateBotMembers(
  leagueId: string,
  botCount: number,
): LeagueMember[] {
  return Array.from({ length: botCount }, (_, i) => {
    const botId = `bot-user-${String(i + 1).padStart(3, '0')}`;
    const botName = BOT_NAMES[i % BOT_NAMES.length];
    return {
      id: `bot-member-${leagueId}-${i}`,
      leagueId,
      userId: botId,
      teamName: `${botName}'s Team`,
      totalPoints: 0,
      joinedAt: new Date().toISOString(),
      user: makeBotUser(botId, botName),
    };
  });
}

function generateInviteCode(): string {
  return `MOCK-${Math.random().toString(36).substring(2, 8).toUpperCase()}`;
}

// ── Mock TanStack Query helper ─────────────────────────────────────────
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

// ── Mock mutation helper ───────────────────────────────────────────────
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

// ── useLeagues ─────────────────────────────────────────────────────────
// Returns all mock leagues the mock user belongs to, matching the shape
// returned by the real useLeagues() (league_members rows with nested league).
// eslint-disable-next-line no-unused-vars
export function useMockLeagues(_userId: string | undefined) {
  const { state } = useMockData();

  const data = state.leagues.map((league) => {
    const myMember = league.members.find(
      (m) => m.userId === state.mockUser.id,
    );
    return {
      id: myMember?.id ?? league.id,
      team_name: myMember?.teamName ?? 'My Team',
      total_points: myMember?.totalPoints ?? 0,
      leagues: {
        id: league.id,
        name: league.name,
        status: league.status,
        current_round: league.currentRound,
        max_participants: league.maxParticipants,
        commissioner_id: league.commissionerId,
        invite_code: league.inviteCode,
      },
    };
  });

  return makeMockQuery(data);
}

// ── useLeague ──────────────────────────────────────────────────────────
// Returns a single league by ID with its members, matching the shape
// returned by the real useLeague().
export function useMockLeague(leagueId: string | undefined) {
  const { state } = useMockData();

  const league = leagueId
    ? state.leagues.find((l) => l.id === leagueId) ?? null
    : null;

  const data = league
    ? {
        id: league.id,
        name: league.name,
        commissioner_id: league.commissionerId,
        invite_code: league.inviteCode,
        max_participants: league.maxParticipants,
        current_round: league.currentRound,
        status: league.status,
        created_at: league.createdAt,
        updated_at: league.updatedAt,
        isMock: league.isMock,
        league_members: league.members.map((m) => ({
          id: m.id,
          user_id: m.userId,
          team_name: m.teamName,
          total_points: m.totalPoints,
          users: m.user
            ? {
                display_name: m.user.displayName,
                avatar_url: m.user.avatarUrl ?? '',
              }
            : null,
        })),
      }
    : null;

  return makeMockQuery(data);
}

// ── useCreateLeague ────────────────────────────────────────────────────
// Creates a mock league with bot members and dispatches CREATE_LEAGUE.
export function useMockCreateLeague() {
  const { state, dispatch } = useMockData();

  return makeMockMutation(
    (params: {
      name: string;
      maxParticipants: number;
      teamName?: string;
      botCount?: number;
    }) => {
      const leagueId = `mock-league-${Date.now()}`;
      const now = new Date().toISOString();
      const totalBots = Math.min(
        (params.botCount ?? params.maxParticipants - 1),
        params.maxParticipants - 1,
      );

      // Commissioner member (mock user)
      const commissionerMember: LeagueMember = {
        id: `member-${leagueId}-commissioner`,
        leagueId,
        userId: state.mockUser.id,
        teamName: params.teamName ?? `Team ${params.name}`,
        totalPoints: 0,
        joinedAt: now,
        user: {
          id: state.mockUser.id,
          email: state.mockUser.email,
          displayName: state.mockUser.displayName,
          avatarUrl: state.mockUser.avatarUrl,
          createdAt: now,
          updatedAt: now,
        },
      };

      const botMembers = generateBotMembers(leagueId, totalBots);

      const league: MockState['leagues'][number] = {
        id: leagueId,
        name: params.name,
        commissionerId: state.mockUser.id,
        inviteCode: generateInviteCode(),
        maxParticipants: params.maxParticipants,
        currentRound: 1,
        status: 'setup',
        createdAt: now,
        updatedAt: now,
        members: [commissionerMember, ...botMembers],
        isMock: true,
      };

      dispatch({ type: 'CREATE_LEAGUE', payload: { league } });

      return {
        id: league.id,
        name: league.name,
        invite_code: league.inviteCode,
        max_participants: league.maxParticipants,
        commissioner_id: league.commissionerId,
        status: league.status,
      };
    },
  );
}

// ── useJoinLeague ──────────────────────────────────────────────────────
// Mock join league — adds mock user to an existing mock league.
export function useMockJoinLeague() {
  const { state, dispatch } = useMockData();

  return makeMockMutation(
    (params: { inviteCode: string; userId: string; teamName: string }) => {
      const league = state.leagues.find(
        (l) => l.inviteCode === params.inviteCode,
      );
      if (!league) throw new Error('Invalid invite code');
      if (league.members.length >= league.maxParticipants)
        throw new Error('League is full');
      if (league.members.some((m) => m.userId === params.userId))
        throw new Error('You already belong to this league');

      const member: LeagueMember = {
        id: `member-${league.id}-${Date.now()}`,
        leagueId: league.id,
        userId: params.userId,
        teamName: params.teamName,
        totalPoints: 0,
        joinedAt: new Date().toISOString(),
      };

      dispatch({
        type: 'JOIN_LEAGUE',
        payload: { leagueId: league.id, member },
      });

      return league;
    },
  );
}
