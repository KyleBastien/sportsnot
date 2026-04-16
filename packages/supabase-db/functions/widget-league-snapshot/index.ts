// Supabase Edge Function: widget-league-snapshot
// Returns the widget payload (today's games + drafted players + server-
// computed fantasy points) for a league keyed by public share_code.
// Auth: verify_jwt = false (public read-only).
// Deploy: supabase functions deploy widget-league-snapshot --no-verify-jwt

/// <reference path="../deno.d.ts" />

import { calculatePlayerPoints } from '../_shared/scoring.ts';
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
    const date =
      url.searchParams.get('date') ?? new Date().toISOString().slice(0, 10);

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
    const teamIds = [
      ...new Set(
        rosters.filter((r) => r.team_id != null).map((r) => r.team_id as number)
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

    const teamStats =
      teamIds.length === 0
        ? []
        : await pgSelect<TeamStatsRow>(
            cfg,
            'team_stats_cache',
            `select=team_id,team_name,team_abbreviation,wins,shutouts&team_id=in.(${teamIds.join(',')})&playoff_round=eq.${league.current_round}`
          );
    const teamStatsById = new Map(teamStats.map((t) => [t.team_id, t]));

    // ── Today's NHL playoff games ───────────────────────────
    const games = await fetchGamesForDate(date);
    const gameByTeamId = new Map<number, NhlScoreGame>();
    for (const g of games) {
      gameByTeamId.set(g.homeTeam.id, g);
      gameByTeamId.set(g.awayTeam.id, g);
    }

    // ── Build players payload ───────────────────────────────
    const playersPayload = [] as Array<{
      playerId: number | null;
      teamId: number | null;
      name: string;
      teamAbbrev: string;
      position: string;
      gameId: number | null;
      fantasyPoints: number;
      ownedByTeamName: string;
    }>;
    for (const r of rosters) {
      const teamName = memberById.get(r.league_member_id)?.team_name ?? '';
      if (r.player_id != null) {
        const stats = playerStatsById.get(r.player_id);
        const fantasyPoints = stats
          ? calculatePlayerPoints({
              goals: stats.goals ?? 0,
              assists: stats.assists ?? 0,
            })
          : (r.points_earned ?? 0);
        playersPayload.push({
          playerId: r.player_id,
          teamId: null,
          name: stats?.player_name ?? `Player ${r.player_id}`,
          teamAbbrev: stats?.team_abbreviation ?? '',
          position: r.position,
          gameId: correlatePlayerGame(stats?.team_abbreviation, games),
          fantasyPoints,
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
