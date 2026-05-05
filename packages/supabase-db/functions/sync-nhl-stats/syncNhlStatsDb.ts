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

function sumGoals(games: PlayerGameLog[]): number {
  return games.reduce((sum, game) => sum + (game.goals ?? 0), 0);
}

function sumAssists(games: PlayerGameLog[]): number {
  return games.reduce((sum, game) => sum + (game.assists ?? 0), 0);
}

function countTeamWinsAndShutouts(
  teamId: number,
  finalGames: NhlScoreGameLite[]
): { wins: number; shutouts: number } {
  let wins = 0;
  let shutouts = 0;

  for (const game of finalGames) {
    const isHome = game.homeTeam?.id === teamId;
    const isAway = game.awayTeam?.id === teamId;

    if (!isHome && !isAway) {
      continue;
    }

    const teamScore = isHome
      ? (game.homeTeam?.score ?? 0)
      : (game.awayTeam?.score ?? 0);
    const opponentScore = isHome
      ? (game.awayTeam?.score ?? 0)
      : (game.homeTeam?.score ?? 0);

    if (teamScore > opponentScore) {
      wins += 1;
      if (opponentScore === 0) {
        shutouts += 1;
      }
    }
  }

  return { wins, shutouts };
}

export async function syncRoundPlayerStats(
  cfg: PgConfig,
  season: string,
  playoffRound: number,
  players: EligiblePlayer[],
  finalizedGameIds: Set<number>,
  liveDeltas: Map<number, LiveDelta>,
  fetchJson: <T>(url: string) => Promise<T | null>,
  nhlApiBase: string
): Promise<number> {
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

export async function syncRoundTeamStats(
  cfg: PgConfig,
  season: string,
  playoffRound: number,
  teams: EligibleTeam[],
  finalGames: NhlScoreGameLite[]
): Promise<number> {
  let teamUpdates = 0;

  for (const team of teams) {
    const record = countTeamWinsAndShutouts(team.id, finalGames);
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

async function updatePlayerRosterPoints(
  cfg: PgConfig,
  season: string,
  playoffRound: number,
  playerIds: number[]
): Promise<void> {
  if (playerIds.length === 0) {
    return;
  }

  const playerStats = await pgSelect<PlayerStatsRow>(
    cfg,
    'player_stats_cache',
    `select=player_id,goals,assists&player_id=in.(${playerIds.join(',')})&nhl_season=eq.${season}&playoff_round=eq.${playoffRound}`
  );
  const statsByPlayerId = new Map(
    playerStats.map((row) => [row.player_id, row])
  );

  for (const playerId of playerIds) {
    const stats = statsByPlayerId.get(playerId);
    if (!stats) {
      continue;
    }

    await pgUpdate(
      cfg,
      'rosters',
      `player_id=eq.${playerId}&round=eq.${playoffRound}&is_active=eq.true`,
      {
        points_earned: (stats.goals ?? 0) + (stats.assists ?? 0),
      }
    );
  }
}

async function updateTeamRosterPoints(
  cfg: PgConfig,
  season: string,
  playoffRound: number,
  teamIds: number[]
): Promise<void> {
  if (teamIds.length === 0) {
    return;
  }

  const teamStats = await pgSelect<TeamStatsRow>(
    cfg,
    'team_stats_cache',
    `select=team_id,wins,shutouts&team_id=in.(${teamIds.join(',')})&nhl_season=eq.${season}&playoff_round=eq.${playoffRound}`
  );
  const statsByTeamId = new Map(teamStats.map((row) => [row.team_id, row]));

  for (const teamId of teamIds) {
    const stats = statsByTeamId.get(teamId);
    if (!stats) {
      continue;
    }

    const regularWins = (stats.wins ?? 0) - (stats.shutouts ?? 0);
    await pgUpdate(
      cfg,
      'rosters',
      `team_id=eq.${teamId}&round=eq.${playoffRound}&is_active=eq.true`,
      {
        points_earned: regularWins * 2 + (stats.shutouts ?? 0) * 4,
      }
    );
  }
}

export async function updateRoundRosterPoints(
  cfg: PgConfig,
  season: string,
  playoffRound: number
): Promise<void> {
  const rosters = await pgSelect<RosterRow>(
    cfg,
    'rosters',
    `select=league_member_id,player_id,team_id&round=eq.${playoffRound}&is_active=eq.true`
  );

  await updatePlayerRosterPoints(
    cfg,
    season,
    playoffRound,
    uniquePlayerIds(rosters)
  );
  await updateTeamRosterPoints(
    cfg,
    season,
    playoffRound,
    uniqueTeamIds(rosters)
  );
}

export async function refreshActiveLeagueStandings(
  cfg: PgConfig,
  activeLeagues: LeagueRow[],
  playoffRound: number
): Promise<void> {
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
