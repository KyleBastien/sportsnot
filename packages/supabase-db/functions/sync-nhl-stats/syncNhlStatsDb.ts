import {
  pgRpc,
  pgSelect,
  pgUpdate,
  pgUpsert,
  type PgConfig,
} from '../_shared/pg.ts';
import type {
  EligiblePlayer,
  EligibleTeam,
  LeagueRow,
  LiveDelta,
  NhlScoreGameLite,
  PlayerGameLog,
  PlayerStatsRow,
  RosterRow,
  TeamStatsRow,
} from './syncNhlStatsTypes.ts';

interface SyncRoundContext {
  cfg: PgConfig;
  season: string;
  playoffRound: number;
}

interface TeamGameScore {
  team: number;
  opponent: number;
}

function sumGoals(games: PlayerGameLog[]): number {
  return games.reduce((sum, game) => sum + (game.goals ?? 0), 0);
}

function sumAssists(games: PlayerGameLog[]): number {
  return games.reduce((sum, game) => sum + (game.assists ?? 0), 0);
}

function countTeamWinsAndShutouts(params: {
  teamId: number;
  finalGames: NhlScoreGameLite[];
}): { wins: number; shutouts: number } {
  const { teamId, finalGames } = params;
  let wins = 0;
  let shutouts = 0;

  for (const game of finalGames) {
    const score = getTeamGameScore(teamId, game);
    if (!score || !isWinningScore(score)) {
      continue;
    }

    wins += 1;
    shutouts += Number(isShutoutScore(score));
  }

  return { wins, shutouts };
}

function getTeamGameScore(
  teamId: number,
  game: NhlScoreGameLite
): TeamGameScore | null {
  return (
    getTeamSideScore(
      teamId,
      game.homeTeam?.id,
      game.homeTeam?.score,
      game.awayTeam?.score
    ) ??
    getTeamSideScore(
      teamId,
      game.awayTeam?.id,
      game.awayTeam?.score,
      game.homeTeam?.score
    )
  );
}

function getTeamSideScore(
  teamId: number,
  gameTeamId: number | undefined,
  teamScore: number | undefined,
  opponentScore: number | undefined
): TeamGameScore | null {
  if (gameTeamId !== teamId) {
    return null;
  }

  return {
    team: teamScore ?? 0,
    opponent: opponentScore ?? 0,
  };
}

function isWinningScore(score: TeamGameScore) {
  return score.team > score.opponent;
}

function isShutoutScore(score: TeamGameScore) {
  return score.opponent === 0;
}

export async function syncRoundPlayerStats(
  context: SyncRoundContext,
  players: EligiblePlayer[],
  finalizedGameIds: Set<number>,
  liveDeltas: Map<number, LiveDelta>,
  fetchJson: <T>(url: string) => Promise<T | null>,
  nhlApiBase: string
): Promise<number> {
  const { cfg, season, playoffRound } = context;
  let playerUpdates = 0;

  for (const player of players) {
    const data = await fetchJson<{ gameLog?: PlayerGameLog[] }>(
      `${nhlApiBase}/player/${player.id}/game-log/${season}/3`
    );
    const finalizedGames = (data?.gameLog ?? []).filter((game) =>
      finalizedGameIds.has(game.gameId)
    );
    const live = liveDeltas.get(player.id);

    const ok = await pgUpsert(
      cfg,
      'player_stats_cache',
      'player_id,nhl_season,playoff_round',
      {
        player_id: player.id,
        nhl_season: season,
        playoff_round: playoffRound,
        player_name: player.playerName,
        team_abbreviation: live?.teamAbbrev ?? player.teamAbbrev,
        position: player.position,
        goals: sumGoals(finalizedGames) + (live?.goals ?? 0),
        assists: sumAssists(finalizedGames) + (live?.assists ?? 0),
        games_played: finalizedGames.length + (live ? 1 : 0),
        is_injured: false,
        last_updated: new Date().toISOString(),
      }
    );

    if (ok) {
      playerUpdates += 1;
    }
  }

  return playerUpdates;
}

export async function syncRoundTeamStats(params: {
  context: SyncRoundContext;
  teams: EligibleTeam[];
  finalGames: NhlScoreGameLite[];
}): Promise<number> {
  let teamUpdates = 0;
  const {
    context: { cfg, season, playoffRound },
    teams,
    finalGames,
  } = params;

  for (const team of teams) {
    const record = countTeamWinsAndShutouts({ teamId: team.id, finalGames });
    const ok = await pgUpsert(
      cfg,
      'team_stats_cache',
      'team_id,nhl_season,playoff_round',
      {
        team_id: team.id,
        nhl_season: season,
        playoff_round: playoffRound,
        team_name: team.name,
        team_abbreviation: team.abbrev,
        wins: record.wins,
        shutouts: record.shutouts,
        is_eliminated: false,
        last_updated: new Date().toISOString(),
      }
    );

    if (ok) {
      teamUpdates += 1;
    }
  }

  return teamUpdates;
}

function uniquePlayerIds(rosters: RosterRow[]): number[] {
  return [
    ...new Set(
      rosters
        .filter((roster) => roster.player_id != null)
        .map((roster) => roster.player_id as number)
    ),
  ];
}

function uniqueTeamIds(rosters: RosterRow[]): number[] {
  return [
    ...new Set(
      rosters
        .filter((roster) => roster.team_id != null)
        .map((roster) => roster.team_id as number)
    ),
  ];
}

async function updateRosterPoints<
  Row extends { [key: string]: number | null },
>(params: {
  cfg: PgConfig;
  season: string;
  playoffRound: number;
  ids: number[];
  cacheTable: 'player_stats_cache' | 'team_stats_cache';
  idColumn: 'player_id' | 'team_id';
  selectColumns: string;
  toPoints: (row: Row) => number;
}): Promise<void> {
  const {
    cfg,
    season,
    playoffRound,
    ids,
    cacheTable,
    idColumn,
    selectColumns,
    toPoints,
  } = params;

  if (ids.length === 0) {
    return;
  }

  const rows = await pgSelect<Row>(
    cfg,
    cacheTable,
    `select=${selectColumns}&${idColumn}=in.(${ids.join(',')})&nhl_season=eq.${season}&playoff_round=eq.${playoffRound}`
  );
  const rowsById = new Map(rows.map((row) => [row[idColumn] as number, row]));

  for (const id of ids) {
    const row = rowsById.get(id);
    if (!row) {
      continue;
    }

    await pgUpdate(
      cfg,
      'rosters',
      `${idColumn}=eq.${id}&round=eq.${playoffRound}&is_active=eq.true`,
      {
        points_earned: toPoints(row),
      }
    );
  }
}

async function updatePlayerRosterPoints(
  context: SyncRoundContext,
  playerIds: number[]
): Promise<void> {
  await updateRosterPoints<PlayerStatsRow>({
    ...context,
    ids: playerIds,
    cacheTable: 'player_stats_cache',
    idColumn: 'player_id',
    selectColumns: 'player_id,goals,assists',
    toPoints: (row) => (row.goals ?? 0) + (row.assists ?? 0),
  });
}

async function updateTeamRosterPoints(
  context: SyncRoundContext,
  teamIds: number[]
): Promise<void> {
  await updateRosterPoints<TeamStatsRow>({
    ...context,
    ids: teamIds,
    cacheTable: 'team_stats_cache',
    idColumn: 'team_id',
    selectColumns: 'team_id,wins,shutouts',
    toPoints: (row) => {
      const regularWins = (row.wins ?? 0) - (row.shutouts ?? 0);
      return regularWins * 2 + (row.shutouts ?? 0) * 4;
    },
  });
}

export async function updateRoundRosterPoints(
  context: SyncRoundContext
): Promise<void> {
  const { cfg, playoffRound } = context;
  const rosters = await pgSelect<RosterRow>(
    cfg,
    'rosters',
    `select=league_member_id,player_id,team_id&round=eq.${playoffRound}&is_active=eq.true`
  );

  await updatePlayerRosterPoints(context, uniquePlayerIds(rosters));
  await updateTeamRosterPoints(context, uniqueTeamIds(rosters));
}

export async function refreshActiveLeagueStandings(
  context: SyncRoundContext,
  activeLeagues: LeagueRow[]
): Promise<void> {
  const { cfg, playoffRound } = context;
  for (const league of activeLeagues) {
    if (league.status !== 'active' || league.current_round !== playoffRound) {
      continue;
    }

    await pgRpc(cfg, 'refresh_league_standings', {
      p_league_id: league.id,
      p_round: playoffRound,
    });
  }
}
