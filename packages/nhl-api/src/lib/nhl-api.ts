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

// Raw API types for response mapping
interface RawBracketTeam {
  id: number;
  abbrev: string;
  name: { default: string; fr?: string };
  commonName: { default: string };
  logo?: string;
}

interface RawBracketSeries {
  seriesLetter: string;
  playoffRound: number;
  topSeedTeam?: RawBracketTeam;
  bottomSeedTeam?: RawBracketTeam;
  topSeedWins: number;
  bottomSeedWins: number;
  winningTeamId?: number;
  losingTeamId?: number;
}

interface RawRosterPlayer {
  id: number;
  headshot?: string;
  firstName: { default: string };
  lastName: { default: string };
  sweaterNumber?: number;
  positionCode: string;
  shootsCatches: 'L' | 'R';
  heightInInches?: number;
  weightInPounds?: number;
  birthDate: string;
  birthCity?: { default: string };
  birthCountry?: string;
}

interface RawGameTeam {
  id: number;
  commonName?: { default: string };
  placeName?: { default: string };
  abbrev: string;
  score?: number;
  logo?: string;
}

interface RawGame {
  id: number;
  season: number;
  gameType: number;
  gameDate?: string;
  startTimeUTC: string;
  gameState: string;
  awayTeam: RawGameTeam;
  homeTeam: RawGameTeam;
  periodDescriptor?: { number: number; periodType: string };
}

const POSITION_MAP: Record<string, { code: string; name: string; type: string; abbreviation: string }> = {
  C: { code: 'C', name: 'Center', type: 'Forward', abbreviation: 'C' },
  L: { code: 'L', name: 'Left Wing', type: 'Forward', abbreviation: 'LW' },
  R: { code: 'R', name: 'Right Wing', type: 'Forward', abbreviation: 'RW' },
  D: { code: 'D', name: 'Defenseman', type: 'Defenseman', abbreviation: 'D' },
  G: { code: 'G', name: 'Goalie', type: 'Goalie', abbreviation: 'G' },
};

function inchesToHeight(inches?: number): string {
  if (!inches) return '';
  const ft = Math.floor(inches / 12);
  const remaining = inches % 12;
  return `${ft}' ${remaining}"`;
}

function computeAge(birthDate: string): number {
  const birth = new Date(birthDate);
  const now = new Date();
  let age = now.getFullYear() - birth.getFullYear();
  const monthDiff = now.getMonth() - birth.getMonth();
  if (monthDiff < 0 || (monthDiff === 0 && now.getDate() < birth.getDate())) {
    age--;
  }
  return age;
}

/** Convert season like '20242025' to bracket format '2025'. */
function seasonToBracketYear(season: string): string {
  return season.length === 8 ? season.slice(4) : season;
}

function mapRawSeries(raw: RawBracketSeries): NHLPlayoffSeries {
  const mapTeam = (t?: RawBracketTeam) =>
    t ? { id: t.id, name: t.name.default, abbreviation: t.abbrev } : undefined;
  const top = mapTeam(raw.topSeedTeam);
  const bottom = mapTeam(raw.bottomSeedTeam);
  const isComplete = raw.topSeedWins === 4 || raw.bottomSeedWins === 4;
  let seriesWinner: { id: number; name: string } | undefined;
  if (raw.winningTeamId && (raw.topSeedTeam || raw.bottomSeedTeam)) {
    const winner =
      raw.topSeedTeam?.id === raw.winningTeamId
        ? raw.topSeedTeam
        : raw.bottomSeedTeam;
    if (winner) seriesWinner = { id: winner.id, name: winner.name.default };
  }
  return {
    seriesCode: raw.seriesLetter,
    round: raw.playoffRound,
    topSeedTeam: top,
    bottomSeedTeam: bottom,
    topSeedWins: raw.topSeedWins,
    bottomSeedWins: raw.bottomSeedWins,
    matchupTeams: top && bottom
      ? {
          topSeed: {
            team: { id: top.id, name: top.name },
            seriesRecord: { wins: raw.topSeedWins, losses: raw.bottomSeedWins },
          },
          bottomSeed: {
            team: { id: bottom.id, name: bottom.name },
            seriesRecord: { wins: raw.bottomSeedWins, losses: raw.topSeedWins },
          },
        }
      : undefined,
    isComplete,
    seriesWinner,
  };
}

function mapRawPlayer(
  raw: RawRosterPlayer,
  teamAbbrev: string,
  teamId: number,
  teamName: string,
  season: string
): NHLPlayer {
  return {
    id: raw.id,
    fullName: `${raw.firstName.default} ${raw.lastName.default}`,
    firstName: raw.firstName.default,
    lastName: raw.lastName.default,
    primaryNumber: raw.sweaterNumber != null ? String(raw.sweaterNumber) : undefined,
    birthDate: raw.birthDate,
    currentAge: computeAge(raw.birthDate),
    nationality: raw.birthCountry ?? '',
    height: inchesToHeight(raw.heightInInches),
    weight: raw.weightInPounds ?? 0,
    shootsCatches: raw.shootsCatches,
    primaryPosition: POSITION_MAP[raw.positionCode] ?? POSITION_MAP['C'],
    currentTeam: { id: teamId, name: teamName, abbreviation: teamAbbrev },
    headshot: raw.headshot,
  };
}

function mapRawGame(raw: RawGame): NHLGame {
  const gameDate =
    raw.gameDate ?? raw.startTimeUTC.split('T')[0];
  return {
    id: raw.id,
    gameType: String(raw.gameType),
    season: String(raw.season),
    gameDate,
    startTimeUTC: raw.startTimeUTC,
    homeTeam: {
      id: raw.homeTeam.id,
      name: raw.homeTeam.commonName?.default ?? '',
      abbreviation: raw.homeTeam.abbrev,
      score: raw.homeTeam.score,
    },
    awayTeam: {
      id: raw.awayTeam.id,
      name: raw.awayTeam.commonName?.default ?? '',
      abbreviation: raw.awayTeam.abbrev,
      score: raw.awayTeam.score,
    },
    gameState: raw.gameState as NHLGame['gameState'],
    period: raw.periodDescriptor?.number,
  };
}

/**
 * Get current playoff bracket/series information.
 * The bracket API uses a 4-digit year (e.g. "2025") rather than the 8-digit
 * season format used by other endpoints.
 */
export async function getPlayoffBracket(
  season: string
): Promise<NHLPlayoffSeries[]> {
  const year = seasonToBracketYear(season);
  const url = `${NHL_API_BASE}/playoff-bracket/${year}`;
  const data = await fetchJson<{ series: RawBracketSeries[] }>(url);
  return data.series.map(mapRawSeries);
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
    forwards: RawRosterPlayer[];
    defensemen: RawRosterPlayer[];
    goalies: RawRosterPlayer[];
  }>(url);

  // We need team info for the player mapping. Derive from bracket or use abbreviation.
  const allRaw = [...data.forwards, ...data.defensemen, ...data.goalies];
  return allRaw.map((p) =>
    mapRawPlayer(p, teamAbbreviation, 0, '', season)
  );
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
  const data = await fetchJson<{
    standings: Array<{
      teamAbbrev: { default: string };
      teamName: { default: string };
      teamLogo: string;
      teamCommonName: { default: string };
    }>;
  }>(url);
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
  const data = await fetchJson<{ gameWeek: Array<{ games: RawGame[] }> }>(url);
  return data.gameWeek.flatMap((week) => week.games).map(mapRawGame);
}

/**
 * Get playoff schedule for a season by collecting games from team club schedules.
 * The NHL API has no single playoff schedule endpoint, so we iterate through
 * each team's monthly schedule during the playoff window (April–July).
 */
export async function getPlayoffSchedule(
  season: string,
  teamAbbreviations?: string[]
): Promise<NHLGame[]> {
  const abbrevs = teamAbbreviations ?? [];
  if (abbrevs.length === 0) return [];

  const year = seasonToBracketYear(season);
  const months = [`${year}-04`, `${year}-05`, `${year}-06`, `${year}-07`];

  const seen = new Set<number>();
  const games: NHLGame[] = [];

  for (const abbrev of abbrevs) {
    for (const month of months) {
      try {
        const url = `${NHL_API_BASE}/club-schedule/${abbrev}/month/${month}`;
        const data = await fetchJson<{ games: RawGame[] }>(url);
        for (const raw of data.games) {
          if (raw.gameType === 3 && !seen.has(raw.id)) {
            seen.add(raw.id);
            games.push(mapRawGame(raw));
          }
        }
      } catch {
        // Team may not have games in this month
      }
    }
  }

  games.sort((a, b) => a.gameDate.localeCompare(b.gameDate));
  return games;
}

/**
 * Get live game boxscore
 */
export async function getGameBoxscore(
  gameId: number
): Promise<Record<string, unknown>> {
  const url = `${NHL_API_BASE}/gamecenter/${gameId}/boxscore`;
  return fetchJson<Record<string, unknown>>(url);
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
