// Supabase Edge Function: sync-nhl-stats
// Fetches latest playoff stats from NHL API and updates the cache tables
// Deploy: supabase functions deploy sync-nhl-stats
// Schedule via cron or invoke manually

/// <reference path="../deno.d.ts" />

const NHL_API_BASE = 'https://api-web.nhle.com/v1';

interface PlayerGameLog {
  gameId: number;
  gameDate: string;
  teamAbbrev?: string;
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

interface NhlScoreGameLite {
  id: number;
  gameType: number;
  gameState: string;
  gameDate?: string;
  homeTeam?: { id?: number; abbrev?: string };
  awayTeam?: { id?: number; abbrev?: string };
}

interface LiveDelta {
  goals: number;
  assists: number;
  teamAbbrev: string | null;
}

/**
 * Fetch live/in-progress playoff games and aggregate per-player goal/assist
 * deltas from each game's boxscore. Returns a Map keyed by playerId.
 *
 * Live games are NOT yet present in the per-player game-log endpoint, so
 * adding these deltas on top of the finalized game-log totals gives a
 * "season-to-date including in-progress" total without double-counting.
 */
async function fetchLivePlayerDeltas(
  roundStartDate?: string,
  roundEndDate?: string
): Promise<Map<number, LiveDelta>> {
  const deltas = new Map<number, LiveDelta>();
  try {
    const resp = await fetch(`${NHL_API_BASE}/score/now`);
    if (!resp.ok) return deltas;
    const data = await resp.json();
    const games = (data.games ?? []) as NhlScoreGameLite[];
    const liveGames = games.filter((g) => {
      if (g.gameType !== 3) return false;
      if (g.gameState !== 'LIVE' && g.gameState !== 'CRIT') return false;
      if (roundStartDate && roundEndDate && g.gameDate) {
        if (g.gameDate < roundStartDate || g.gameDate > roundEndDate)
          return false;
      }
      return true;
    });

    for (const game of liveGames) {
      try {
        const bxResp = await fetch(
          `${NHL_API_BASE}/gamecenter/${game.id}/boxscore`
        );
        if (!bxResp.ok) continue;
        const bx = await bxResp.json();
        const sides: Array<{
          stats?: BoxscoreTeamStats;
          abbrev?: string;
        }> = [
          {
            stats: bx?.playerByGameStats?.homeTeam,
            abbrev: game.homeTeam?.abbrev,
          },
          {
            stats: bx?.playerByGameStats?.awayTeam,
            abbrev: game.awayTeam?.abbrev,
          },
        ];

        for (const side of sides) {
          const players = [
            ...(side.stats?.forwards ?? []),
            ...(side.stats?.defense ?? []),
            ...(side.stats?.goalies ?? []),
          ];
          for (const p of players) {
            if (!p?.playerId) continue;
            const existing = deltas.get(p.playerId) ?? {
              goals: 0,
              assists: 0,
              teamAbbrev: side.abbrev ?? null,
            };
            existing.goals += p.goals ?? 0;
            existing.assists += p.assists ?? 0;
            if (!existing.teamAbbrev && side.abbrev) {
              existing.teamAbbrev = side.abbrev;
            }
            deltas.set(p.playerId, existing);
          }
        }
      } catch {
        // Continue on individual game failures
      }
    }
  } catch {
    // Network/parse failures: return whatever deltas we collected.
  }
  return deltas;
}

interface RosterRow {
  player_id: number | null;
  team_id: number | null;
  position: string;
}

interface PlayerStatsRow {
  goals: number;
  assists: number;
}

interface TeamStatsRow {
  wins: number;
  shutouts: number;
}

interface RosterMemberRow {
  league_member_id: string;
}

interface LeagueMemberRow {
  id: string;
  league_id: string;
}

/** Build standard PostgREST headers with service role auth. */
function pgHeaders(apiKey: string): Record<string, string> {
  return {
    'Content-Type': 'application/json',
    apikey: apiKey,
    Authorization: `Bearer ${apiKey}`,
  };
}

/** GET rows from a PostgREST table with query params. */
async function pgSelect<T>(
  baseUrl: string,
  apiKey: string,
  table: string,
  params: string
): Promise<T[]> {
  const resp = await fetch(`${baseUrl}/rest/v1/${table}?${params}`, {
    headers: pgHeaders(apiKey),
  });
  if (!resp.ok) return [];
  return (await resp.json()) as T[];
}

/** UPSERT rows into a PostgREST table. */
async function pgUpsert(
  baseUrl: string,
  apiKey: string,
  table: string,
  onConflict: string,
  body: unknown
): Promise<boolean> {
  const resp = await fetch(
    `${baseUrl}/rest/v1/${table}?on_conflict=${onConflict}`,
    {
      method: 'POST',
      headers: {
        ...pgHeaders(apiKey),
        Prefer: 'resolution=merge-duplicates',
      },
      body: JSON.stringify(body),
    }
  );
  return resp.ok;
}

/** PATCH rows in a PostgREST table matching filters. */
async function pgUpdate(
  baseUrl: string,
  apiKey: string,
  table: string,
  filters: string,
  body: unknown
): Promise<boolean> {
  const resp = await fetch(`${baseUrl}/rest/v1/${table}?${filters}`, {
    method: 'PATCH',
    headers: pgHeaders(apiKey),
    body: JSON.stringify(body),
  });
  return resp.ok;
}

/** Call a PostgREST RPC function. */
async function pgRpc(
  baseUrl: string,
  apiKey: string,
  fn: string,
  body: unknown
): Promise<boolean> {
  const resp = await fetch(`${baseUrl}/rest/v1/rpc/${fn}`, {
    method: 'POST',
    headers: pgHeaders(apiKey),
    body: JSON.stringify(body),
  });
  return resp.ok;
}

Deno.serve(async (req: Request) => {
  try {
    const supabaseUrl = Deno.env.get('SUPABASE_URL');
    const supabaseKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY');

    if (!supabaseUrl || !supabaseKey) {
      return new Response(
        JSON.stringify({
          error: 'Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY',
        }),
        {
          status: 500,
          headers: { 'Content-Type': 'application/json' },
        }
      );
    }

    const body = await req.json().catch(() => ({}));
    const season: string = body.season || '20252026';
    const playoffRound: number = body.playoff_round || 1;
    const roundStartDate: string | undefined = body.round_start_date;
    const roundEndDate: string | undefined = body.round_end_date;

    // ── Get active rosters ─────────────────────────────────────
    const rosters = await pgSelect<RosterRow>(
      supabaseUrl,
      supabaseKey,
      'rosters',
      `select=player_id,team_id,position&round=eq.${playoffRound}&is_active=eq.true`
    );

    if (rosters.length === 0) {
      return new Response(
        JSON.stringify({ message: 'No active rosters to sync' }),
        { headers: { 'Content-Type': 'application/json' } }
      );
    }

    const playerIds = [
      ...new Set(
        rosters
          .filter((r) => r.player_id != null)
          .map((r) => r.player_id as number)
      ),
    ];
    const teamIds = [
      ...new Set(
        rosters.filter((r) => r.team_id != null).map((r) => r.team_id as number)
      ),
    ];

    let playerUpdates = 0;
    let teamUpdates = 0;

    // Pull live boxscore deltas once so we can layer in-progress goals/
    // assists on top of the finalized per-player game-log totals.
    const liveDeltas = await fetchLivePlayerDeltas(
      roundStartDate,
      roundEndDate
    );

    // ── Sync player stats from NHL API ─────────────────────────
    for (const playerId of playerIds) {
      try {
        const resp = await fetch(
          `${NHL_API_BASE}/player/${playerId}/game-log/${season}/3`
        );
        if (!resp.ok) continue;

        const data = await resp.json();
        const allGames: PlayerGameLog[] = data.gameLog ?? [];

        const games =
          roundStartDate && roundEndDate
            ? allGames.filter(
                (g) =>
                  g.gameDate >= roundStartDate && g.gameDate <= roundEndDate
              )
            : allGames;

        const finalizedGoals = games.reduce(
          (sum: number, g: PlayerGameLog) => sum + (g.goals ?? 0),
          0
        );
        const finalizedAssists = games.reduce(
          (sum: number, g: PlayerGameLog) => sum + (g.assists ?? 0),
          0
        );

        // Layer live in-progress totals on top of finalized totals. The
        // boxscore reflects only the current game, and the game-log only
        // includes finalized games, so summing the two cannot double-count.
        const live = liveDeltas.get(playerId);
        const totalGoals = finalizedGoals + (live?.goals ?? 0);
        const totalAssists = finalizedAssists + (live?.assists ?? 0);
        const totalGamesPlayed = games.length + (live ? 1 : 0);

        // Extract team abbreviation: prefer the live game (most current),
        // then the most recent finalized game-log entry.
        const teamAbbrev =
          live?.teamAbbrev ??
          (allGames.length > 0
            ? (allGames[allGames.length - 1].teamAbbrev ?? null)
            : null);

        const upsertRow: Record<string, unknown> = {
          player_id: playerId,
          nhl_season: season,
          playoff_round: playoffRound,
          goals: totalGoals,
          assists: totalAssists,
          games_played: totalGamesPlayed,
          last_updated: new Date().toISOString(),
        };
        if (teamAbbrev) {
          upsertRow.team_abbreviation = teamAbbrev;
        }

        const ok = await pgUpsert(
          supabaseUrl,
          supabaseKey,
          'player_stats_cache',
          'player_id,nhl_season,playoff_round',
          upsertRow
        );
        if (ok) playerUpdates++;
      } catch {
        // Continue on individual player failures
      }
    }

    // ── Sync team stats (wins/shutouts) ────────────────────────
    for (const teamId of teamIds) {
      try {
        const resp = await fetch(`${NHL_API_BASE}/score/now`);
        if (!resp.ok) continue;

        const data = await resp.json();
        const games = data.games ?? [];

        let wins = 0;
        let shutouts = 0;

        for (const game of games) {
          if (game.gameType !== 3 || game.gameState !== 'FINAL') continue;

          if (roundStartDate && roundEndDate && game.gameDate) {
            if (game.gameDate < roundStartDate || game.gameDate > roundEndDate)
              continue;
          }

          const isHome = game.homeTeam?.id === teamId;
          const isAway = game.awayTeam?.id === teamId;
          if (!isHome && !isAway) continue;

          const teamScore = isHome
            ? game.homeTeam?.score
            : game.awayTeam?.score;
          const opponentScore = isHome
            ? game.awayTeam?.score
            : game.homeTeam?.score;

          if (teamScore > opponentScore) {
            wins++;
            if (opponentScore === 0) shutouts++;
          }
        }

        const ok = await pgUpsert(
          supabaseUrl,
          supabaseKey,
          'team_stats_cache',
          'team_id,nhl_season,playoff_round',
          {
            team_id: teamId,
            nhl_season: season,
            playoff_round: playoffRound,
            wins,
            shutouts,
            last_updated: new Date().toISOString(),
          }
        );
        if (ok) teamUpdates++;
      } catch {
        // Continue on individual team failures
      }
    }

    // ── Update roster points_earned from stats cache ───────────
    const SCORING_GOAL = 1;
    const SCORING_ASSIST = 1;
    const SCORING_WIN = 2;
    const SCORING_SHUTOUT = 4;

    for (const playerId of playerIds) {
      const rows = await pgSelect<PlayerStatsRow>(
        supabaseUrl,
        supabaseKey,
        'player_stats_cache',
        `select=goals,assists&player_id=eq.${playerId}&nhl_season=eq.${season}&playoff_round=eq.${playoffRound}&limit=1`
      );
      if (rows.length > 0) {
        const stats = rows[0];
        const pts =
          (stats.goals ?? 0) * SCORING_GOAL +
          (stats.assists ?? 0) * SCORING_ASSIST;
        await pgUpdate(
          supabaseUrl,
          supabaseKey,
          'rosters',
          `player_id=eq.${playerId}&round=eq.${playoffRound}&is_active=eq.true`,
          { points_earned: pts }
        );
      }
    }

    for (const teamId of teamIds) {
      const rows = await pgSelect<TeamStatsRow>(
        supabaseUrl,
        supabaseKey,
        'team_stats_cache',
        `select=wins,shutouts&team_id=eq.${teamId}&nhl_season=eq.${season}&playoff_round=eq.${playoffRound}&limit=1`
      );
      if (rows.length > 0) {
        const stats = rows[0];
        const regularWins = (stats.wins ?? 0) - (stats.shutouts ?? 0);
        const pts =
          regularWins * SCORING_WIN + (stats.shutouts ?? 0) * SCORING_SHUTOUT;
        await pgUpdate(
          supabaseUrl,
          supabaseKey,
          'rosters',
          `team_id=eq.${teamId}&round=eq.${playoffRound}&is_active=eq.true`,
          { points_earned: pts }
        );
      }
    }

    // ── Aggregate into league_members standings ────────────────
    const affectedMembers = await pgSelect<RosterMemberRow>(
      supabaseUrl,
      supabaseKey,
      'rosters',
      `select=league_member_id&round=eq.${playoffRound}&is_active=eq.true`
    );

    if (affectedMembers.length > 0) {
      const memberIds = [
        ...new Set(affectedMembers.map((r) => r.league_member_id)),
      ];

      const members = await pgSelect<LeagueMemberRow>(
        supabaseUrl,
        supabaseKey,
        'league_members',
        `select=id,league_id&id=in.(${memberIds.join(',')})`
      );

      if (members.length > 0) {
        const leagueIds = [...new Set(members.map((m) => m.league_id))];
        for (const leagueId of leagueIds) {
          await pgRpc(supabaseUrl, supabaseKey, 'refresh_league_standings', {
            p_league_id: leagueId,
            p_round: playoffRound,
          });
        }
      }
    }

    return new Response(
      JSON.stringify({
        message: 'Stats synced and standings updated',
        playerUpdates,
        teamUpdates,
      }),
      { headers: { 'Content-Type': 'application/json' } }
    );
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return new Response(JSON.stringify({ error: message }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }
});
