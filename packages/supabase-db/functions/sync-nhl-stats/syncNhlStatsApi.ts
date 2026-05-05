import {
  incrementIsoDate,
  isPlayoffGameInRound,
} from '../_shared/playoff-rounds.ts';
import {
  type BoxscorePlayer,
  type BoxscoreTeamStats,
  type BracketResponse,
  type EligiblePlayer,
  type EligibleTeam,
  FINAL_GAME_STATES,
  LIVE_GAME_STATES,
  type LiveDelta,
  NHL_API_BASE,
  type NhlScoreGameLite,
  type ScoreboardResponse,
  type TeamRosterPlayer,
  type TeamRosterResponse,
} from './syncNhlStatsTypes.ts';

function seasonToBracketYear(season: string): string {
  return season.length === 8 ? season.slice(4) : season;
}

async function fetchJson<T>(url: string): Promise<T | null> {
  try {
    const response = await fetch(url);
    if (!response.ok) {
      return null;
    }
    return (await response.json()) as T;
  } catch {
    return null;
  }
}

export function isCompletedGame(game: NhlScoreGameLite): boolean {
  return FINAL_GAME_STATES.has(game.gameState);
}

export function isLiveGame(game: NhlScoreGameLite): boolean {
  return LIVE_GAME_STATES.has(game.gameState);
}

function toEligibleTeam(team: {
  id: number;
  abbrev: string;
  name?: { default?: string };
}): EligibleTeam {
  return {
    id: team.id,
    abbrev: team.abbrev,
    name: team.name?.default ?? team.abbrev,
  };
}

function isEligibleBracketTeam(
  team: { id: number; abbrev: string } | undefined
): team is { id: number; abbrev: string; name?: { default?: string } } {
  return Boolean(team && team.id > 0 && team.abbrev && team.abbrev !== 'TBD');
}

function addEligibleBracketTeam(
  teamsById: Map<number, EligibleTeam>,
  team: { id: number; abbrev: string; name?: { default?: string } } | undefined
): void {
  if (!isEligibleBracketTeam(team) || teamsById.has(team.id)) {
    return;
  }

  teamsById.set(team.id, toEligibleTeam(team));
}

export async function fetchEligibleRoundTeams(
  season: string,
  playoffRound: number
): Promise<EligibleTeam[]> {
  const data = await fetchJson<BracketResponse>(
    `${NHL_API_BASE}/playoff-bracket/${seasonToBracketYear(season)}`
  );

  if (!data?.series) {
    return [];
  }

  const teamsById = new Map<number, EligibleTeam>();

  for (const series of data.series) {
    if (series.playoffRound !== playoffRound) {
      continue;
    }

    addEligibleBracketTeam(teamsById, series.topSeedTeam);
    addEligibleBracketTeam(teamsById, series.bottomSeedTeam);
  }

  return [...teamsById.values()];
}

function mapRosterPlayers(
  players: TeamRosterPlayer[] | undefined,
  position: 'F' | 'D',
  team: EligibleTeam
): EligiblePlayer[] {
  return (players ?? []).map((player) => ({
    id: player.id,
    playerName: `${player.firstName.default} ${player.lastName.default}`,
    position,
    teamId: team.id,
    teamAbbrev: team.abbrev,
  }));
}

export async function fetchEligibleRoundPlayers(
  season: string,
  teams: EligibleTeam[]
): Promise<EligiblePlayer[]> {
  const playersById = new Map<number, EligiblePlayer>();

  for (const team of teams) {
    const roster = await fetchJson<TeamRosterResponse>(
      `${NHL_API_BASE}/roster/${team.abbrev}/${season}`
    );

    if (!roster) {
      continue;
    }

    for (const player of [
      ...mapRosterPlayers(roster.forwards, 'F', team),
      ...mapRosterPlayers(roster.defensemen, 'D', team),
    ]) {
      playersById.set(player.id, player);
    }
  }

  return [...playersById.values()];
}

export async function fetchRoundGames(
  playoffRound: number,
  roundStartDate: string,
  roundEndDate: string
): Promise<NhlScoreGameLite[]> {
  const games: NhlScoreGameLite[] = [];
  let currentDate = roundStartDate;

  while (currentDate <= roundEndDate) {
    const data = await fetchJson<ScoreboardResponse>(
      `${NHL_API_BASE}/score/${currentDate}`
    );

    for (const game of data?.games ?? []) {
      if (isPlayoffGameInRound(game, playoffRound)) {
        games.push(game);
      }
    }

    currentDate = incrementIsoDate(currentDate);
  }

  return games;
}

function getSidePlayers(stats?: BoxscoreTeamStats): BoxscorePlayer[] {
  return [
    ...(stats?.forwards ?? []),
    ...(stats?.defense ?? []),
    ...(stats?.goalies ?? []),
  ];
}

function applyPlayerDeltas(
  deltas: Map<number, LiveDelta>,
  players: BoxscorePlayer[],
  teamAbbrev: string | undefined
): void {
  for (const player of players) {
    if (!player.playerId) {
      continue;
    }

    const existing = deltas.get(player.playerId) ?? {
      goals: 0,
      assists: 0,
      teamAbbrev: teamAbbrev ?? null,
    };

    existing.goals += player.goals ?? 0;
    existing.assists += player.assists ?? 0;

    if (!existing.teamAbbrev && teamAbbrev) {
      existing.teamAbbrev = teamAbbrev;
    }

    deltas.set(player.playerId, existing);
  }
}

async function applyLiveGameDeltas(
  deltas: Map<number, LiveDelta>,
  game: NhlScoreGameLite
): Promise<void> {
  const boxscore = await fetchJson<{
    playerByGameStats?: {
      homeTeam?: BoxscoreTeamStats;
      awayTeam?: BoxscoreTeamStats;
    };
  }>(`${NHL_API_BASE}/gamecenter/${game.id}/boxscore`);

  if (!boxscore) {
    return;
  }

  applyPlayerDeltas(
    deltas,
    getSidePlayers(boxscore.playerByGameStats?.homeTeam),
    game.homeTeam?.abbrev
  );
  applyPlayerDeltas(
    deltas,
    getSidePlayers(boxscore.playerByGameStats?.awayTeam),
    game.awayTeam?.abbrev
  );
}

export async function fetchLivePlayerDeltas(
  playoffRound: number
): Promise<Map<number, LiveDelta>> {
  const deltas = new Map<number, LiveDelta>();
  const data = await fetchJson<ScoreboardResponse>(`${NHL_API_BASE}/score/now`);

  if (!data?.games) {
    return deltas;
  }

  const liveGames = data.games.filter(
    (game) => isPlayoffGameInRound(game, playoffRound) && isLiveGame(game)
  );

  for (const game of liveGames) {
    await applyLiveGameDeltas(deltas, game);
  }

  return deltas;
}
