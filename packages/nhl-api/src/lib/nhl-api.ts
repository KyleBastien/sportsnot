import type {
  NHLPlayer,
  NHLTeam,
  NHLGame,
  NHLPlayoffSeries,
  NHLPlayerStats,
} from '@sportsnot/types';

const NHL_API_BASE = 'https://api-web.nhle.com/v1';

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`NHL API error: ${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

/**
 * Get current playoff bracket/series information
 */
export async function getPlayoffBracket(
  season: string
): Promise<NHLPlayoffSeries[]> {
  const url = `${NHL_API_BASE}/playoff-bracket/${season}`;
  const data = await fetchJson<{ rounds: Array<{ series: NHLPlayoffSeries[] }> }>(url);
  return data.rounds.flatMap((round) => round.series);
}

/**
 * Get team roster
 */
export async function getTeamRoster(
  teamAbbreviation: string,
  season: string
): Promise<NHLPlayer[]> {
  const url = `${NHL_API_BASE}/roster/${teamAbbreviation}/${season}`;
  const data = await fetchJson<{
    forwards: NHLPlayer[];
    defensemen: NHLPlayer[];
    goalies: NHLPlayer[];
  }>(url);
  return [...data.forwards, ...data.defensemen, ...data.goalies];
}

/**
 * Get player info by ID
 */
export async function getPlayer(playerId: number): Promise<NHLPlayer> {
  const url = `${NHL_API_BASE}/player/${playerId}/landing`;
  return fetchJson<NHLPlayer>(url);
}

/**
 * Get player game log (playoff stats)
 */
export async function getPlayerGameLog(
  playerId: number,
  season: string,
  gameType: 3 // 3 = playoffs
): Promise<NHLPlayerStats[]> {
  const url = `${NHL_API_BASE}/player/${playerId}/game-log/${season}/${gameType}`;
  const data = await fetchJson<{ gameLog: NHLPlayerStats[] }>(url);
  return data.gameLog ?? [];
}

/**
 * Get all teams from current standings
 */
export async function getTeams(): Promise<NHLTeam[]> {
  const url = `${NHL_API_BASE}/standings/now`;
  const data = await fetchJson<{ standings: Array<{ teamAbbrev: { default: string }; teamName: { default: string }; teamLogo: string; teamCommonName: { default: string } }> }>(url);
  return data.standings.map((team) => ({
    id: 0,
    name: team.teamName.default,
    abbreviation: team.teamAbbrev.default,
    teamName: team.teamCommonName.default,
    locationName: '',
    division: { id: 0, name: '' },
    conference: { id: 0, name: '' },
    logo: team.teamLogo,
  }));
}

/**
 * Get schedule for a specific date
 */
export async function getSchedule(date: string): Promise<NHLGame[]> {
  const url = `${NHL_API_BASE}/schedule/${date}`;
  const data = await fetchJson<{ gameWeek: Array<{ games: NHLGame[] }> }>(url);
  return data.gameWeek.flatMap((week) => week.games);
}

/**
 * Get playoff schedule for a season
 */
export async function getPlayoffSchedule(season: string): Promise<NHLGame[]> {
  const url = `${NHL_API_BASE}/schedule/playoff/${season}`;
  return fetchJson<NHLGame[]>(url);
}

/**
 * Get live game boxscore
 */
export async function getGameBoxscore(gameId: number): Promise<any> {
  const url = `${NHL_API_BASE}/gamecenter/${gameId}/boxscore`;
  return fetchJson<any>(url);
}

/**
 * Get today's scores / live games
 */
export async function getScoresNow(): Promise<NHLGame[]> {
  const url = `${NHL_API_BASE}/score/now`;
  const data = await fetchJson<{ games: NHLGame[] }>(url);
  return data.games ?? [];
}

/**
 * Get all playoff-eligible players for given teams
 */
export async function getPlayoffRosters(
  teamAbbreviations: string[],
  season: string
): Promise<Map<string, NHLPlayer[]>> {
  const rosters = new Map<string, NHLPlayer[]>();

  const results = await Promise.allSettled(
    teamAbbreviations.map(async (abbr) => {
      const players = await getTeamRoster(abbr, season);
      return { abbr, players };
    })
  );

  for (const result of results) {
    if (result.status === 'fulfilled') {
      rosters.set(result.value.abbr, result.value.players);
    }
  }

  return rosters;
}

/**
 * Determine eliminated teams from playoff bracket
 */
export function getEliminatedTeams(series: NHLPlayoffSeries[]): Set<number> {
  const eliminated = new Set<number>();

  for (const s of series) {
    if (!s.topSeedTeam || !s.bottomSeedTeam) continue;

    const topWins = s.topSeedWins ?? 0;
    const bottomWins = s.bottomSeedWins ?? 0;

    if (topWins === 4) {
      eliminated.add(s.bottomSeedTeam.id);
    } else if (bottomWins === 4) {
      eliminated.add(s.topSeedTeam.id);
    }
  }

  return eliminated;
}

export const nhlApi = {
  getPlayoffBracket,
  getTeamRoster,
  getPlayer,
  getPlayerGameLog,
  getTeams,
  getSchedule,
  getPlayoffSchedule,
  getGameBoxscore,
  getScoresNow,
  getPlayoffRosters,
  getEliminatedTeams,
};
