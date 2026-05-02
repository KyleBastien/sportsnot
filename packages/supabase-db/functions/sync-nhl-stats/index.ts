// Supabase Edge Function: sync-nhl-stats
// Fetches latest playoff stats from NHL API and updates the cache tables
// Deploy: supabase functions deploy sync-nhl-stats
// Schedule via cron or invoke manually

/// <reference path="../deno.d.ts" />

import {
  derivePlayoffRoundsToSync,
  getEffectiveRoundEndDate,
  getPlayoffRoundWindow,
  incrementIsoDate,
  isPlayoffGameInRound,
} from '../_shared/playoff-rounds.ts';
import {
  jsonResponse,
  pgRpc,
  pgSelect,
  pgUpdate,
  pgUpsert,
  type PgConfig,
} from '../_shared/pg.ts';

const NHL_API_BASE = 'https://api-web.nhle.com/v1';
const DEFAULT_SEASON = '20252026';
const FINAL_GAME_STATES = new Set(['OFF', 'FINAL']);
const LIVE_GAME_STATES = new Set(['LIVE', 'CRIT']);

interface PlayerGameLog {
  gameId: number;
  goals: number;
  assists: number;
}

interface BoxscorePlayer {
  playerId: number;
  goals?: number;
  assists?: number;
}

interface BoxscoreTeamStats {
  forwards?: BoxscorePlayer[];
  defense?: BoxscorePlayer[];
  goalies?: BoxscorePlayer[];
}

interface SeriesStatus {
  round?: number;
}

interface NhlScoreGameLite {
  id: number;
  gameType: number;
  gameState: string;
  gameDate?: string;
  homeTeam?: { id?: number; abbrev?: string; score?: number };
  awayTeam?: { id?: number; abbrev?: string; score?: number };
  seriesStatus?: SeriesStatus | null;
}

interface ScoreboardResponse {
  games?: NhlScoreGameLite[];
}

interface BracketTeam {
  id: number;
  abbrev: string;
  name?: { default?: string };
}

interface BracketSeries {
  playoffRound: number;
  topSeedTeam?: BracketTeam;
  bottomSeedTeam?: BracketTeam;
}

interface BracketResponse {
  series?: BracketSeries[];
}

interface TeamRosterPlayer {
  id: number;
  firstName: { default: string };
  lastName: { default: string };
}

interface TeamRosterResponse {
  forwards?: TeamRosterPlayer[];
  defensemen?: TeamRosterPlayer[];
}

interface EligibleTeam {
  id: number;
  abbrev: string;
  name: string;
}

interface EligiblePlayer {
  id: number;
  playerName: string;
  position: 'F' | 'D';
  teamId: number;
  teamAbbrev: string;
}

interface LeagueRow {
  id: string;
  current_round: number | null;
  status: string;
}

interface RosterRow {
  league_member_id: string;
  player_id: number | null;
  team_id: number | null;
}

interface PlayerStatsRow {
  player_id: number;
  goals: number;
  assists: number;
}

interface TeamStatsRow {
  team_id: number;
  wins: number;
  shutouts: number;
}

interface LiveDelta {
  goals: number;
  assists: number;
  teamAbbrev: string | null;
}

function seasonToBracketYear(season: string): string {
  return season.length === 8 ? season.slice(4) : season;
}

function parseRequestedRound(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === 'string' && value.trim().length > 0) {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  return null;
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

function isCompletedGame(game: NhlScoreGameLite): boolean {
  return FINAL_GAME_STATES.has(game.gameState);
}

function isLiveGame(game: NhlScoreGameLite): boolean {
  return LIVE_GAME_STATES.has(game.gameState);
}

async function fetchEligibleRoundTeams(
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

    for (const team of [series.topSeedTeam, series.bottomSeedTeam]) {
      if (!team || team.id <= 0 || !team.abbrev || team.abbrev === 'TBD') {
        continue;
      }

      if (!teamsById.has(team.id)) {
        teamsById.set(team.id, {
          id: team.id,
          abbrev: team.abbrev,
          name: team.name?.default ?? team.abbrev,
        });
      }
    }
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

async function fetchEligibleRoundPlayers(
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

    const teamPlayers = [
      ...mapRosterPlayers(roster.forwards, 'F', team),
      ...mapRosterPlayers(roster.defensemen, 'D', team),
    ];

    for (const player of teamPlayers) {
      playersById.set(player.id, player);
    }
  }

  return [...playersById.values()];
}

async function fetchRoundGames(
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

async function fetchLivePlayerDeltas(
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
    const boxscore = await fetchJson<{
      playerByGameStats?: {
        homeTeam?: BoxscoreTeamStats;
        awayTeam?: BoxscoreTeamStats;
      };
    }>(`${NHL_API_BASE}/gamecenter/${game.id}/boxscore`);

    if (!boxscore) {
      continue;
    }

    const sides: Array<{
      stats?: BoxscoreTeamStats;
      abbrev?: string;
    }> = [
      {
        stats: boxscore.playerByGameStats?.homeTeam,
        abbrev: game.homeTeam?.abbrev,
      },
      {
        stats: boxscore.playerByGameStats?.awayTeam,
        abbrev: game.awayTeam?.abbrev,
      },
    ];

    for (const side of sides) {
      const players = [
        ...(side.stats?.forwards ?? []),
        ...(side.stats?.defense ?? []),
        ...(side.stats?.goalies ?? []),
      ];

      for (const player of players) {
        if (!player.playerId) {
          continue;
        }

        const existing = deltas.get(player.playerId) ?? {
          goals: 0,
          assists: 0,
          teamAbbrev: side.abbrev ?? null,
        };

        existing.goals += player.goals ?? 0;
        existing.assists += player.assists ?? 0;

        if (!existing.teamAbbrev && side.abbrev) {
          existing.teamAbbrev = side.abbrev;
        }

        deltas.set(player.playerId, existing);
      }
    }
  }

  return deltas;
}

async function syncRoundPlayerStats(
  cfg: PgConfig,
  season: string,
  playoffRound: number,
  players: EligiblePlayer[],
  finalizedGameIds: Set<number>,
  liveDeltas: Map<number, LiveDelta>
): Promise<number> {
  let playerUpdates = 0;

  for (const player of players) {
    const data = await fetchJson<{ gameLog?: PlayerGameLog[] }>(
      `${NHL_API_BASE}/player/${player.id}/game-log/${season}/3`
    );

    const finalizedGames = (data?.gameLog ?? []).filter((game) =>
      finalizedGameIds.has(game.gameId)
    );

    const finalizedGoals = finalizedGames.reduce(
      (sum, game) => sum + (game.goals ?? 0),
      0
    );
    const finalizedAssists = finalizedGames.reduce(
      (sum, game) => sum + (game.assists ?? 0),
      0
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
        goals: finalizedGoals + (live?.goals ?? 0),
        assists: finalizedAssists + (live?.assists ?? 0),
        games_played: finalizedGames.length + (live ? 1 : 0),
        is_injured: false,
        last_updated: new Date().toISOString(),
      }
    );

    if (ok) {
      playerUpdates++;
    }
  }

  return playerUpdates;
}

async function syncRoundTeamStats(
  cfg: PgConfig,
  season: string,
  playoffRound: number,
  teams: EligibleTeam[],
  finalGames: NhlScoreGameLite[]
): Promise<number> {
  let teamUpdates = 0;

  for (const team of teams) {
    let wins = 0;
    let shutouts = 0;

    for (const game of finalGames) {
      const isHome = game.homeTeam?.id === team.id;
      const isAway = game.awayTeam?.id === team.id;

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
        wins++;
        if (opponentScore === 0) {
          shutouts++;
        }
      }
    }

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
        wins,
        shutouts,
        is_eliminated: false,
        last_updated: new Date().toISOString(),
      }
    );

    if (ok) {
      teamUpdates++;
    }
  }

  return teamUpdates;
}

async function updateRoundRosterPoints(
  cfg: PgConfig,
  season: string,
  playoffRound: number
): Promise<void> {
  const rosters = await pgSelect<RosterRow>(
    cfg,
    'rosters',
    `select=league_member_id,player_id,team_id&round=eq.${playoffRound}&is_active=eq.true`
  );

  const playerIds = [
    ...new Set(
      rosters
        .filter((roster) => roster.player_id != null)
        .map((roster) => roster.player_id as number)
    ),
  ];
  const teamIds = [
    ...new Set(
      rosters
        .filter((roster) => roster.team_id != null)
        .map((roster) => roster.team_id as number)
    ),
  ];

  if (playerIds.length > 0) {
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

  if (teamIds.length > 0) {
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
}

async function refreshActiveLeagueStandings(
  cfg: PgConfig,
  activeLeagues: LeagueRow[],
  playoffRound: number
): Promise<void> {
  const leagueIds = activeLeagues
    .filter(
      (league) =>
        league.status === 'active' && league.current_round === playoffRound
    )
    .map((league) => league.id);

  for (const leagueId of leagueIds) {
    await pgRpc(cfg, 'refresh_league_standings', {
      p_league_id: leagueId,
      p_round: playoffRound,
    });
  }
}

Deno.serve(async (req: Request) => {
  try {
    const supabaseUrl = Deno.env.get('SUPABASE_URL');
    const supabaseKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY');

    if (!supabaseUrl || !supabaseKey) {
      return jsonResponse(
        {
          error: 'Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY',
        },
        500
      );
    }

    const cfg: PgConfig = {
      url: supabaseUrl,
      key: supabaseKey,
    };

    const body = await req.json().catch(() => ({}));
    const season: string = body.season || DEFAULT_SEASON;
    const requestedRound = parseRequestedRound(body.playoff_round);
    const overrideStartDate =
      typeof body.round_start_date === 'string'
        ? body.round_start_date
        : undefined;
    const overrideEndDate =
      typeof body.round_end_date === 'string' ? body.round_end_date : undefined;

    const activeLeagues = await pgSelect<LeagueRow>(
      cfg,
      'leagues',
      'select=id,current_round,status&status=in.(active,drafting)&current_round=gte.1'
    );

    const roundsToSync =
      requestedRound != null
        ? [requestedRound]
        : derivePlayoffRoundsToSync(activeLeagues);

    if (roundsToSync.length === 0) {
      return jsonResponse({
        message: 'No active or drafting league rounds to sync',
        syncedRounds: [],
        playerUpdates: 0,
        teamUpdates: 0,
      });
    }

    let playerUpdates = 0;
    let teamUpdates = 0;
    const syncedRounds: number[] = [];

    for (const playoffRound of roundsToSync) {
      const roundWindow = getPlayoffRoundWindow(
        season,
        playoffRound,
        requestedRound === playoffRound ? overrideStartDate : undefined,
        requestedRound === playoffRound ? overrideEndDate : undefined
      );

      if (!roundWindow) {
        if (requestedRound === playoffRound) {
          return jsonResponse(
            {
              error: `No configured round window for season ${season} round ${playoffRound}`,
            },
            400
          );
        }
        continue;
      }

      const eligibleTeams = await fetchEligibleRoundTeams(season, playoffRound);
      if (eligibleTeams.length === 0) {
        continue;
      }

      const eligiblePlayers = await fetchEligibleRoundPlayers(
        season,
        eligibleTeams
      );
      const liveDeltas = await fetchLivePlayerDeltas(playoffRound);
      const effectiveRoundEndDate = getEffectiveRoundEndDate(roundWindow);
      const roundGames = await fetchRoundGames(
        playoffRound,
        roundWindow.startDate,
        effectiveRoundEndDate
      );
      const finalGames = roundGames.filter(isCompletedGame);
      const finalizedGameIds = new Set(finalGames.map((game) => game.id));

      playerUpdates += await syncRoundPlayerStats(
        cfg,
        season,
        playoffRound,
        eligiblePlayers,
        finalizedGameIds,
        liveDeltas
      );
      teamUpdates += await syncRoundTeamStats(
        cfg,
        season,
        playoffRound,
        eligibleTeams,
        finalGames
      );
      await updateRoundRosterPoints(cfg, season, playoffRound);
      await refreshActiveLeagueStandings(cfg, activeLeagues, playoffRound);

      syncedRounds.push(playoffRound);
    }

    return jsonResponse({
      message: 'Stats synced and standings updated',
      syncedRounds,
      playerUpdates,
      teamUpdates,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return jsonResponse({ error: message }, 500);
  }
});
