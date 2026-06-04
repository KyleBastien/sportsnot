// Supabase Edge Function: widget-league-snapshot
// Returns the widget payload (today's games + drafted players + server-
// computed fantasy points) for a league keyed by public share_code.
// Auth: verify_jwt = false (public read-only).
// Deploy: supabase functions deploy widget-league-snapshot --no-verify-jwt

/// <reference path="../deno.d.ts" />

import { calculatePlayerPoints } from '../_shared/scoring.ts';
import {
  buildDailyFantasyPointMaps,
  type WidgetDailyFantasyBoxscore,
  type WidgetDailyFantasyGame,
} from '../_shared/widget-daily-fantasy.ts';
import { jsonResponse, pgSelect } from '../_shared/pg.ts';

const NHL_API_BASE = 'https://api-web.nhle.com/v1';

interface LeagueRow {
  id: string;
  name: string;
  share_code: string;
  current_round: number;
  status: string;
}

interface MemberRow {
  id: string;
  team_name: string;
}

interface RosterRow {
  league_member_id: string;
  player_id: number | null;
  team_id: number | null;
  position: string;
  is_active: boolean;
  points_earned: number;
}

interface PlayerStatsRow {
  player_id: number;
  player_name: string | null;
  team_abbreviation: string | null;
  goals: number;
  assists: number;
}

interface TeamStatsRow {
  team_id: number;
  team_name: string | null;
  team_abbreviation: string | null;
  wins: number;
  shutouts: number;
  is_eliminated?: boolean | null;
}

interface NhlScoreGame {
  id: number;
  gameType: number;
  gameDate?: string;
  startTimeUTC: string;
  gameState: string;
  period?: number;
  periodDescriptor?: { number?: number };
  clock?: { timeRemaining?: string };
  homeTeam: {
    id: number;
    abbrev?: string;
    commonName?: { default?: string };
    placeName?: { default?: string };
    score?: number;
  };
  awayTeam: {
    id: number;
    abbrev?: string;
    commonName?: { default?: string };
    placeName?: { default?: string };
    score?: number;
  };
}

/** Pull the set of NHL playoff games (gameType=3) for a given date. */
async function fetchGamesForDate(date: string): Promise<NhlScoreGame[]> {
  try {
    const resp = await fetch(`${NHL_API_BASE}/score/${date}`);
    if (!resp.ok) return [];
    const data = await resp.json();
    const games = (data.games ?? []) as NhlScoreGame[];
    return games.filter((g) => g.gameType === 3);
  } catch {
    return [];
  }
}

Deno.serve(async (req: Request) => {
  if (req.method === 'OPTIONS') {
    return jsonResponse({}, 204);
  }

  try {
    const supabaseUrl = Deno.env.get('SUPABASE_URL');
    // The widget is public: prefer anon key so RLS policies apply.
    // Fall back to service role if anon isn't set (dev environments).
    const apiKey =
      Deno.env.get('SUPABASE_ANON_KEY') ??
      Deno.env.get('SUPABASE_SERVICE_ROLE_KEY');

    if (!supabaseUrl || !apiKey) {
      return jsonResponse(
        { error: 'Missing SUPABASE_URL or SUPABASE_ANON_KEY' },
        500
      );
    }

    const url = new URL(req.url);
    const shareCode = url.searchParams.get('shareCode');
    if (!shareCode) {
      return jsonResponse({ error: 'shareCode is required' }, 400);
    }
    // Use Eastern Time (America/New_York) for "today" since NHL games are
    // scheduled in ET. Using UTC would roll to the next date as early as
    // ~8 pm ET in summer (midnight UTC), showing tomorrow's slate too soon.
    const date =
      url.searchParams.get('date') ??
      new Intl.DateTimeFormat('en-CA', { timeZone: 'America/New_York' }).format(
        new Date()
      );

    const cfg = { url: supabaseUrl, key: apiKey };

    // ── Load league ──────────────────────────────────────────
    const leagues = await pgSelect<LeagueRow>(
      cfg,
      'leagues',
      `select=id,name,share_code,current_round,status&share_code=eq.${encodeURIComponent(shareCode)}&limit=1`
    );
    if (leagues.length === 0) {
      return jsonResponse({ error: 'League not found' }, 404);
    }
    const league = leagues[0];

    // ── Load members + current-round rosters ─────────────────
    const members = await pgSelect<MemberRow>(
      cfg,
      'league_members',
      `select=id,team_name&league_id=eq.${league.id}`
    );
    const memberById = new Map(members.map((m) => [m.id, m]));

    const rosters =
      members.length === 0
        ? []
        : await pgSelect<RosterRow>(
            cfg,
            'rosters',
            `select=league_member_id,player_id,team_id,position,is_active,points_earned&round=eq.${league.current_round}&is_active=eq.true&league_member_id=in.(${members.map((m) => m.id).join(',')})`
          );

    const playerIds = [
      ...new Set(
        rosters
          .filter((r) => r.player_id != null)
          .map((r) => r.player_id as number)
      ),
    ];
    // ── Player stats ────────────────────────────────────────
    const playerStats =
      playerIds.length === 0
        ? []
        : await pgSelect<PlayerStatsRow>(
            cfg,
            'player_stats_cache',
            `select=player_id,player_name,team_abbreviation,goals,assists&player_id=in.(${playerIds.join(',')})&playoff_round=eq.${league.current_round}`
          );
    const playerStatsById = new Map(playerStats.map((p) => [p.player_id, p]));

    // Fallback: for players not yet in the playoff-round cache, or whose
    // cached entry is missing team_abbreviation or player_name (e.g. when
    // sync-nhl-stats ran but did not write those columns), look them up in
    // the regular-season cache so the widget can show the correct name and
    // correlate the player to today's game.
    const missingTeamInfoIds = playerIds.filter((pid) => {
      const stats = playerStatsById.get(pid);
      return !stats || !stats.team_abbreviation || !stats.player_name;
    });
    const regularSeasonStats =
      missingTeamInfoIds.length === 0
        ? []
        : await pgSelect<{
            player_id: number;
            player_name: string | null;
            team_abbreviation: string | null;
          }>(
            cfg,
            'regular_season_stats_cache',
            `select=player_id,player_name,team_abbreviation&player_id=in.(${missingTeamInfoIds.join(',')})`
          );
    const regularSeasonStatsById = new Map(
      regularSeasonStats.map((p) => [p.player_id, p])
    );

    const currentRoundTeamStats = await pgSelect<TeamStatsRow>(
      cfg,
      'team_stats_cache',
      `select=team_id,team_name,team_abbreviation,wins,shutouts,is_eliminated&playoff_round=eq.${league.current_round}`
    );
    const nextRoundTeamStats =
      league.current_round >= 4
        ? []
        : await pgSelect<TeamStatsRow>(
            cfg,
            'team_stats_cache',
            `select=team_id,team_name,team_abbreviation,wins,shutouts,is_eliminated&playoff_round=eq.${league.current_round + 1}`
          );
    const mappingRound =
      league.current_round > 1 ? league.current_round - 1 : 1;
    const mappingRoundTeamStats =
      mappingRound === league.current_round
        ? currentRoundTeamStats
        : await pgSelect<TeamStatsRow>(
            cfg,
            'team_stats_cache',
            `select=team_id,team_name,team_abbreviation,wins,shutouts,is_eliminated&playoff_round=eq.${mappingRound}`
          );
    const teamStatsById = new Map(
      currentRoundTeamStats.map((t) => [t.team_id, t])
    );

    const eliminationMaps = buildEliminationMaps({
      round: league.current_round,
      currentRoundTeamStats,
      nextRoundTeamStats,
      mappingRoundTeamStats,
      playerStatsById,
      regularSeasonStatsById,
    });
    const filteredRosters = filterEliminatedRosters(rosters, eliminationMaps);

    // ── Today's NHL playoff games ───────────────────────────
    const games = await fetchGamesForDate(date);
    const gameByTeamId = new Map<number, NhlScoreGame>();
    for (const g of games) {
      gameByTeamId.set(g.homeTeam.id, g);
      gameByTeamId.set(g.awayTeam.id, g);
    }
    const boxscoresByGameId = await fetchBoxscoresForGames(games);
    const { playerDailyPointsById, teamDailyPointsById } =
      buildDailyFantasyPointMaps(
        games.map<WidgetDailyFantasyGame>((g) => ({
          id: g.id,
          state: g.gameState,
          homeTeam: {
            id: g.homeTeam.id,
            score: g.homeTeam.score ?? 0,
          },
          awayTeam: {
            id: g.awayTeam.id,
            score: g.awayTeam.score ?? 0,
          },
        })),
        boxscoresByGameId
      );

    // ── Build players payload ───────────────────────────────
    const playersPayload = [] as Array<{
      playerId: number | null;
      teamId: number | null;
      name: string;
      teamAbbrev: string;
      position: string;
      gameId: number | null;
      fantasyPoints: number;
      dailyFantasyPoints: number;
      ownedByTeamName: string;
    }>;
    for (const r of filteredRosters) {
      const teamName = memberById.get(r.league_member_id)?.team_name ?? '';
      if (r.player_id != null) {
        const stats = playerStatsById.get(r.player_id);
        const regStats = regularSeasonStatsById.get(r.player_id);
        const fantasyPoints = stats
          ? calculatePlayerPoints({
              goals: stats.goals ?? 0,
              assists: stats.assists ?? 0,
            })
          : (r.points_earned ?? 0);
        const teamAbbrev =
          stats?.team_abbreviation ?? regStats?.team_abbreviation ?? '';
        playersPayload.push({
          playerId: r.player_id,
          teamId: null,
          name:
            stats?.player_name ??
            regStats?.player_name ??
            `Player ${r.player_id}`,
          teamAbbrev,
          position: r.position,
          gameId: correlatePlayerGame(teamAbbrev, games),
          fantasyPoints,
          dailyFantasyPoints: playerDailyPointsById.get(r.player_id) ?? 0,
          ownedByTeamName: teamName,
        });
        continue;
      }
      if (r.team_id != null) {
        const stats = teamStatsById.get(r.team_id);
        const game = gameByTeamId.get(r.team_id);
        playersPayload.push({
          playerId: null,
          teamId: r.team_id,
          name:
            stats?.team_name ?? stats?.team_abbreviation ?? `Team ${r.team_id}`,
          teamAbbrev: stats?.team_abbreviation ?? '',
          position: r.position,
          gameId: game ? game.id : null,
          // Goalie totals are server-maintained via sync-nhl-stats; surface
          // the currently-persisted points_earned rather than recomputing
          // mid-game to avoid double-counting finals.
          fantasyPoints: r.points_earned ?? 0,
          dailyFantasyPoints: teamDailyPointsById.get(r.team_id) ?? 0,
          ownedByTeamName: teamName,
        });
      }
    }

    // ── Build games payload (full slate) ────────────────────
    const gamesPayload = games.map((g) => ({
      id: g.id,
      startsAt: g.startTimeUTC,
      state: g.gameState,
      homeTeamId: g.homeTeam.id,
      homeTeamAbbrev: g.homeTeam.abbrev ?? '',
      homeTeamName:
        `${g.homeTeam.placeName?.default ?? ''} ${g.homeTeam.commonName?.default ?? ''}`.trim(),
      homeScore: g.homeTeam.score ?? 0,
      awayTeamId: g.awayTeam.id,
      awayTeamAbbrev: g.awayTeam.abbrev ?? '',
      awayTeamName:
        `${g.awayTeam.placeName?.default ?? ''} ${g.awayTeam.commonName?.default ?? ''}`.trim(),
      awayScore: g.awayTeam.score ?? 0,
      period: g.period ?? g.periodDescriptor?.number ?? null,
      timeRemaining: g.clock?.timeRemaining ?? null,
      hasDraftedPlayers: playersPayload.some((p) => p.gameId === g.id),
    }));

    return jsonResponse({
      league: {
        id: league.id,
        name: league.name,
        shareCode: league.share_code,
        currentRound: league.current_round,
        status: league.status,
      },
      date,
      generatedAt: new Date().toISOString(),
      games: gamesPayload,
      players: playersPayload,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return jsonResponse({ error: message }, 500);
  }
});

/** Find the game id a player is playing in today, by team abbreviation. */
function correlatePlayerGame(
  teamAbbrev: string | null | undefined,
  games: NhlScoreGame[]
): number | null {
  if (!teamAbbrev) return null;
  const g = games.find(
    (gg) =>
      gg.homeTeam.abbrev === teamAbbrev || gg.awayTeam.abbrev === teamAbbrev
  );
  return g ? g.id : null;
}

async function fetchBoxscoresForGames(
  games: NhlScoreGame[]
): Promise<Map<number, WidgetDailyFantasyBoxscore>> {
  const boxscoreEntries = await Promise.all(
    games
      .filter((game) => game.gameState !== 'FUT' && game.gameState !== 'PRE')
      .map(async (game) => {
        try {
          const resp = await fetch(
            `${NHL_API_BASE}/gamecenter/${game.id}/boxscore`
          );
          if (!resp.ok) return null;
          const boxscore = (await resp.json()) as WidgetDailyFantasyBoxscore;
          return [game.id, boxscore] as const;
        } catch {
          return null;
        }
      })
  );

  return new Map(
    boxscoreEntries.filter(
      (entry): entry is readonly [number, WidgetDailyFantasyBoxscore] =>
        entry != null
    )
  );
}

interface EliminationMaps {
  aliveTeamIds: Set<number>;
  playerTeamIdByPlayerId: Map<number, number>;
  hasEliminationData: boolean;
}

function buildEliminationMaps(params: {
  round: number;
  currentRoundTeamStats: TeamStatsRow[];
  nextRoundTeamStats: TeamStatsRow[];
  mappingRoundTeamStats: TeamStatsRow[];
  playerStatsById: Map<number, PlayerStatsRow>;
  regularSeasonStatsById: Map<
    number,
    {
      player_id: number;
      player_name: string | null;
      team_abbreviation: string | null;
    }
  >;
}): EliminationMaps {
  const { aliveTeamIds, hasEliminationData } = computeAliveTeamIds({
    round: params.round,
    currentRoundTeamStats: params.currentRoundTeamStats,
    nextRoundTeamStats: params.nextRoundTeamStats,
  });
  const teamIdByAbbreviation = buildTeamIdByAbbreviationMap(
    params.mappingRoundTeamStats,
    params.currentRoundTeamStats,
    params.nextRoundTeamStats
  );
  const playerTeamIdByPlayerId = buildPlayerTeamIdMap({
    playerStatsById: params.playerStatsById,
    regularSeasonStatsById: params.regularSeasonStatsById,
    teamIdByAbbreviation,
  });
  return { aliveTeamIds, playerTeamIdByPlayerId, hasEliminationData };
}

function filterEliminatedRosters(
  rosters: RosterRow[],
  maps: EliminationMaps
): RosterRow[] {
  if (!maps.hasEliminationData) {
    return rosters;
  }

  return rosters.filter((slot) => {
    const teamId = resolveSlotTeamId(slot, maps.playerTeamIdByPlayerId);
    if (teamId == null) {
      return true;
    }
    return maps.aliveTeamIds.has(teamId);
  });
}

function buildPlayerTeamIdMap(params: {
  playerStatsById: Map<number, PlayerStatsRow>;
  regularSeasonStatsById: Map<
    number,
    {
      player_id: number;
      player_name: string | null;
      team_abbreviation: string | null;
    }
  >;
  teamIdByAbbreviation: Map<string, number>;
}): Map<number, number> {
  const playerTeamIdByPlayerId = new Map<number, number>();

  for (const [playerId, stats] of params.playerStatsById.entries()) {
    const teamAbbrev =
      stats.team_abbreviation ??
      params.regularSeasonStatsById.get(playerId)?.team_abbreviation ??
      null;
    if (!teamAbbrev) {
      continue;
    }
    const teamId = params.teamIdByAbbreviation.get(teamAbbrev);
    if (teamId != null) {
      playerTeamIdByPlayerId.set(playerId, teamId);
    }
  }

  for (const [playerId, regStats] of params.regularSeasonStatsById.entries()) {
    if (playerTeamIdByPlayerId.has(playerId)) {
      continue;
    }
    const teamAbbrev = regStats.team_abbreviation;
    if (!teamAbbrev) {
      continue;
    }
    const teamId = params.teamIdByAbbreviation.get(teamAbbrev);
    if (teamId != null) {
      playerTeamIdByPlayerId.set(playerId, teamId);
    }
  }

  return playerTeamIdByPlayerId;
}

function buildTeamIdByAbbreviationMap(
  ...sources: TeamStatsRow[][]
): Map<string, number> {
  const teamIdByAbbreviation = new Map<string, number>();
  for (const teamStats of sources) {
    for (const team of teamStats) {
      if (team.team_abbreviation) {
        teamIdByAbbreviation.set(team.team_abbreviation, team.team_id);
      }
    }
  }
  return teamIdByAbbreviation;
}

function computeAliveTeamIds(params: {
  round: number;
  currentRoundTeamStats: TeamStatsRow[];
  nextRoundTeamStats: TeamStatsRow[];
}): {
  aliveTeamIds: Set<number>;
  hasEliminationData: boolean;
} {
  const useNextRound = params.round < 4 && params.nextRoundTeamStats.length > 0;
  const aliveTeamStats = useNextRound
    ? params.nextRoundTeamStats
    : params.currentRoundTeamStats;
  if (aliveTeamStats.length === 0) {
    return { aliveTeamIds: new Set<number>(), hasEliminationData: false };
  }

  const aliveTeamIds = new Set<number>();
  for (const team of aliveTeamStats) {
    if (!team.is_eliminated) {
      aliveTeamIds.add(team.team_id);
    }
  }

  return { aliveTeamIds, hasEliminationData: true };
}

function resolveSlotTeamId(
  slot: RosterRow,
  playerTeamIdByPlayerId: Map<number, number>
): number | null {
  if (slot.player_id != null) {
    return playerTeamIdByPlayerId.get(slot.player_id) ?? null;
  }
  return slot.team_id ?? null;
}
