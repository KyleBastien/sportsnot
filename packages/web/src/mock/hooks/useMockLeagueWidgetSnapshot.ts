import {
  useMockData,
  getRoundDateBounds,
  type MockState,
} from '../MockDataProvider';
import {
  gamesCf,
  gamesR1,
  gamesR2,
  gamesScf,
  players,
  teams,
} from '@sportsnot/mock-data';
import type { NHLGame, NHLPlayer, NHLTeam, RosterSlot } from '@sportsnot/types';
import type {
  WidgetDraftedPlayer,
  WidgetGame,
  WidgetSnapshot,
} from '@sportsnot/widget-api';
import { SCORING } from '@sportsnot/types';
import { playerGameLogs } from '@sportsnot/mock-data';

const ALL_GAMES: NHLGame[] = [
  ...(gamesR1 as NHLGame[]),
  ...(gamesR2 as NHLGame[]),
  ...(gamesCf as NHLGame[]),
  ...(gamesScf as NHLGame[]),
];

const ALL_PLAYERS = players as Record<string, NHLPlayer[]>;
const ALL_TEAMS = teams as NHLTeam[];
const PLAYER_GAME_LOGS = playerGameLogs as Record<
  string,
  readonly {
    gameId: number;
    gameDate: string;
    goals: number;
    assists: number;
  }[]
>;

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

export function buildMockLeagueWidgetSnapshot(
  state: MockState,
  leagueId: string | undefined
): WidgetSnapshot | null {
  if (!leagueId) {
    return null;
  }

  const league = state.leagues.find((entry) => entry.id === leagueId);
  if (!league) {
    return null;
  }

  const todaysGames = ALL_GAMES.filter(
    (game) => game.gameDate === state.simulationDate
  );
  const gameByTeamId = new Map<number, NHLGame>();
  const gameByTeamAbbrev = new Map<string, NHLGame>();

  for (const game of todaysGames) {
    gameByTeamId.set(game.homeTeam.id, game);
    gameByTeamId.set(game.awayTeam.id, game);
    gameByTeamAbbrev.set(game.homeTeam.abbreviation, game);
    gameByTeamAbbrev.set(game.awayTeam.abbreviation, game);
  }

  const playersPayload = league.members.flatMap<WidgetDraftedPlayer>((member) =>
    (state.rosters[member.id] ?? [])
      .filter((slot) => slot.isActive && slot.round === league.currentRound)
      .map((slot) =>
        buildDraftedPlayerPayload(
          slot,
          member.teamName,
          state.simulationDate,
          gameByTeamId,
          gameByTeamAbbrev
        )
      )
      .filter((player): player is WidgetDraftedPlayer => player != null)
  );

  const gamesPayload = todaysGames.map<WidgetGame>((game) => ({
    id: game.id,
    startsAt: game.startTimeUTC,
    state: game.gameState,
    homeTeamId: game.homeTeam.id,
    homeTeamAbbrev: game.homeTeam.abbreviation,
    homeTeamName: game.homeTeam.name,
    homeScore: game.homeTeam.score ?? 0,
    awayTeamId: game.awayTeam.id,
    awayTeamAbbrev: game.awayTeam.abbreviation,
    awayTeamName: game.awayTeam.name,
    awayScore: game.awayTeam.score ?? 0,
    period: game.period ?? null,
    timeRemaining: game.periodTimeRemaining ?? null,
    hasDraftedPlayers: playersPayload.some(
      (player) => player.gameId === game.id
    ),
  }));

  return {
    league: {
      id: league.id,
      name: league.name,
      shareCode: league.id,
      currentRound: league.currentRound,
      status: league.status,
    },
    date: state.simulationDate,
    generatedAt: new Date().toISOString(),
    games: gamesPayload,
    players: playersPayload,
  };
}

export function useMockLeagueWidgetSnapshot(leagueId: string | undefined) {
  const { state } = useMockData();

  return makeMockQuery(buildMockLeagueWidgetSnapshot(state, leagueId));
}

function buildDraftedPlayerPayload(
  slot: RosterSlot,
  ownedByTeamName: string,
  simulationDate: string,
  gameByTeamId: Map<number, NHLGame>,
  gameByTeamAbbrev: Map<string, NHLGame>
): WidgetDraftedPlayer | null {
  const fantasyPoints = calculateSlotPoints(slot, simulationDate);
  const dailyFantasyPoints = calculateSlotDailyPoints(slot, simulationDate);

  if (slot.playerId != null) {
    const playerInfo = getPlayerInfo(slot.playerId);
    if (!playerInfo) {
      return null;
    }

    return {
      playerId: slot.playerId,
      teamId: null,
      name: playerInfo.name,
      teamAbbrev: playerInfo.teamAbbrev,
      position: slot.position,
      gameId: gameByTeamAbbrev.get(playerInfo.teamAbbrev)?.id ?? null,
      fantasyPoints,
      dailyFantasyPoints,
      ownedByTeamName,
    };
  }

  if (slot.teamId != null) {
    const teamInfo = getTeamInfo(slot.teamId);
    if (!teamInfo) {
      return null;
    }

    return {
      playerId: null,
      teamId: slot.teamId,
      name: teamInfo.name,
      teamAbbrev: teamInfo.abbreviation,
      position: slot.position,
      gameId: gameByTeamId.get(slot.teamId)?.id ?? null,
      fantasyPoints,
      dailyFantasyPoints,
      ownedByTeamName,
    };
  }

  return null;
}

function calculateSlotPoints(slot: RosterSlot, date: string): number {
  const bounds = getRoundDateBounds(slot.round);
  if (!bounds || date < bounds.firstDate) {
    return 0;
  }

  const throughDate = date < bounds.lastDate ? date : bounds.lastDate;
  return calculatePointsForRange(slot, bounds.firstDate, throughDate);
}

function calculateSlotDailyPoints(slot: RosterSlot, date: string): number {
  const bounds = getRoundDateBounds(slot.round);
  if (!bounds || date < bounds.firstDate || date > bounds.lastDate) {
    return 0;
  }

  return calculatePointsForRange(slot, date, date);
}

function calculatePointsForRange(
  slot: RosterSlot,
  fromDate: string,
  throughDate: string
): number {
  if (slot.playerId != null) {
    const entries = PLAYER_GAME_LOGS[String(slot.playerId)] ?? [];
    return entries.reduce((total, entry) => {
      if (entry.gameDate < fromDate || entry.gameDate > throughDate) {
        return total;
      }

      return (
        total + entry.goals * SCORING.goal + entry.assists * SCORING.assist
      );
    }, 0);
  }

  if (slot.teamId != null) {
    return ALL_GAMES.reduce((total, game) => {
      if (game.gameDate < fromDate || game.gameDate > throughDate) {
        return total;
      }

      const isHome = game.homeTeam.id === slot.teamId;
      const isAway = game.awayTeam.id === slot.teamId;
      if (!isHome && !isAway) {
        return total;
      }

      const teamScore = isHome
        ? (game.homeTeam.score ?? 0)
        : (game.awayTeam.score ?? 0);
      const oppScore = isHome
        ? (game.awayTeam.score ?? 0)
        : (game.homeTeam.score ?? 0);

      if (teamScore <= oppScore) {
        return total;
      }

      return total + (oppScore === 0 ? SCORING.shutout : SCORING.win);
    }, 0);
  }

  return 0;
}

function getPlayerInfo(
  playerId: number
): { name: string; teamAbbrev: string } | null {
  for (const [teamAbbrev, roster] of Object.entries(ALL_PLAYERS)) {
    const player = roster.find((entry) => entry.id === playerId);
    if (player) {
      return {
        name: player.fullName,
        teamAbbrev,
      };
    }
  }

  return null;
}

function getTeamInfo(teamId: number): NHLTeam | null {
  return ALL_TEAMS.find((team) => team.id === teamId) ?? null;
}
