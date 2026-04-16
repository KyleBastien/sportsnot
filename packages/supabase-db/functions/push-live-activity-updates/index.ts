// Supabase Edge Function: push-live-activity-updates
// Fans out APNs Live Activity content-state updates to every registered
// token whose league has at least one game in progress today. Schedule via
// pg_cron (every ~30s while games are live). Auth: verify_jwt = false —
// intended to be called by pg_cron / the Supabase scheduler.
// Deploy: supabase functions deploy push-live-activity-updates --no-verify-jwt

/// <reference path="../deno.d.ts" />

import { calculatePlayerPoints } from '../_shared/scoring.ts';
import { jsonResponse, pgSelect } from '../_shared/pg.ts';

const NHL_API_BASE = 'https://api-web.nhle.com/v1';

interface LeagueRow {
  id: string;
  current_round: number;
  share_code: string;
}

interface MemberRow {
  id: string;
  league_id: string;
}

interface RosterRow {
  league_member_id: string;
  player_id: number | null;
  team_id: number | null;
  points_earned: number;
}

interface PlayerStatsRow {
  player_id: number;
  team_abbreviation: string | null;
  goals: number;
  assists: number;
}

interface TokenRow {
  id: string;
  league_id: string;
  token: string;
  kind: 'activity' | 'start';
  bundle_id: string;
  expires_at: string | null;
}

interface NhlScoreGame {
  id: number;
  gameType: number;
  startTimeUTC: string;
  gameState: string;
  period?: number;
  clock?: { timeRemaining?: string };
  homeTeam: { id: number; abbrev?: string; score?: number };
  awayTeam: { id: number; abbrev?: string; score?: number };
}

/** Base64url-encode a Uint8Array (no padding). */
function b64url(bytes: Uint8Array): string {
  let s = btoa(String.fromCharCode(...bytes));
  return s.replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
}

/** Decode a base64 string to Uint8Array. */
function b64decode(b64: string): Uint8Array {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

/** Convert a PEM ES256 private key (PKCS8) to a CryptoKey. */
async function importApnsKey(pem: string): Promise<CryptoKey> {
  const body = pem
    .replace(/-----BEGIN PRIVATE KEY-----/g, '')
    .replace(/-----END PRIVATE KEY-----/g, '')
    .replace(/\s+/g, '');
  const der = b64decode(body);
  return crypto.subtle.importKey(
    'pkcs8',
    der,
    { name: 'ECDSA', namedCurve: 'P-256' },
    false,
    ['sign']
  );
}

/** Sign an APNs provider JWT (ES256). Cached for up to 55 minutes. */
let cachedJwt: { token: string; iat: number } | null = null;
async function getApnsJwt(
  keyId: string,
  teamId: string,
  p8Pem: string
): Promise<string> {
  const now = Math.floor(Date.now() / 1000);
  if (cachedJwt && now - cachedJwt.iat < 55 * 60) return cachedJwt.token;

  const header = { alg: 'ES256', kid: keyId };
  const claims = { iss: teamId, iat: now };
  const enc = (obj: unknown) =>
    b64url(new TextEncoder().encode(JSON.stringify(obj)));
  const signingInput = `${enc(header)}.${enc(claims)}`;

  const key = await importApnsKey(p8Pem);
  const sig = await crypto.subtle.sign(
    { name: 'ECDSA', hash: 'SHA-256' },
    key,
    new TextEncoder().encode(signingInput)
  );
  const token = `${signingInput}.${b64url(new Uint8Array(sig))}`;
  cachedJwt = { token, iat: now };
  return token;
}

interface PushResult {
  ok: boolean;
  status: number;
  reason?: string;
}

async function sendApnsPush(
  apnsHost: string,
  bundleId: string,
  deviceToken: string,
  jwt: string,
  payload: unknown,
  opts: { pushType: 'liveactivity'; priority?: number }
): Promise<PushResult> {
  const resp = await fetch(`${apnsHost}/3/device/${deviceToken}`, {
    method: 'POST',
    headers: {
      authorization: `bearer ${jwt}`,
      'apns-topic': `${bundleId}.push-type.liveactivity`,
      'apns-push-type': opts.pushType,
      'apns-priority': String(opts.priority ?? 10),
      'apns-expiration': '0',
      'content-type': 'application/json',
    },
    body: JSON.stringify(payload),
  });
  let reason: string | undefined;
  if (!resp.ok) {
    try {
      const data = await resp.json();
      reason = typeof data?.reason === 'string' ? data.reason : undefined;
    } catch {
      // ignore
    }
  }
  return { ok: resp.ok, status: resp.status, reason };
}

async function fetchTodayGames(): Promise<NhlScoreGame[]> {
  try {
    const resp = await fetch(`${NHL_API_BASE}/score/now`);
    if (!resp.ok) return [];
    const data = await resp.json();
    return ((data.games ?? []) as NhlScoreGame[]).filter(
      (g) => g.gameType === 3
    );
  } catch {
    return [];
  }
}

Deno.serve(async (_req: Request) => {
  try {
    const supabaseUrl = Deno.env.get('SUPABASE_URL');
    const apiKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY');
    const apnsKeyId = Deno.env.get('APNS_KEY_ID');
    const apnsTeamId = Deno.env.get('APNS_TEAM_ID');
    const apnsP8 = Deno.env.get('APNS_P8');
    const apnsEnv = Deno.env.get('APNS_ENV') ?? 'production';

    if (!supabaseUrl || !apiKey) {
      return jsonResponse(
        { error: 'Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY' },
        500
      );
    }
    if (!apnsKeyId || !apnsTeamId || !apnsP8) {
      return jsonResponse(
        { error: 'Missing APNS_KEY_ID / APNS_TEAM_ID / APNS_P8' },
        500
      );
    }

    const cfg = { url: supabaseUrl, key: apiKey };

    const games = await fetchTodayGames();
    const liveGames = games.filter((g) => g.gameState === 'LIVE');
    if (liveGames.length === 0) {
      return jsonResponse({ message: 'No live games', pushed: 0 });
    }

    // ── Find every league whose current-round roster touches a live team ──
    const liveTeamAbbrevs = new Set<string>();
    for (const g of liveGames) {
      if (g.homeTeam.abbrev) liveTeamAbbrevs.add(g.homeTeam.abbrev);
      if (g.awayTeam.abbrev) liveTeamAbbrevs.add(g.awayTeam.abbrev);
    }

    // Fetch all leagues with their current_round. Cheap at the scale of
    // a fantasy league app; for large deployments, prefilter via a view.
    const leagues = await pgSelect<LeagueRow>(
      cfg,
      'leagues',
      `select=id,current_round,share_code&status=eq.active`
    );
    if (leagues.length === 0) {
      return jsonResponse({ message: 'No active leagues', pushed: 0 });
    }

    const members = await pgSelect<MemberRow>(
      cfg,
      'league_members',
      `select=id,league_id&league_id=in.(${leagues.map((l) => l.id).join(',')})`
    );
    const membersByLeague = new Map<string, string[]>();
    for (const m of members) {
      const arr = membersByLeague.get(m.league_id) ?? [];
      arr.push(m.id);
      membersByLeague.set(m.league_id, arr);
    }

    // Per-league: compute ContentState (per-player fantasy pts + full game slate)
    const perLeaguePayload: Record<string, unknown> = {};
    const gamesSlate = games.map((g) => ({
      id: g.id,
      homeScore: g.homeTeam.score ?? 0,
      awayScore: g.awayTeam.score ?? 0,
      period: g.period ?? null,
      clock: g.clock?.timeRemaining ?? null,
      state: g.gameState,
    }));

    for (const league of leagues) {
      const memberIds = membersByLeague.get(league.id) ?? [];
      if (memberIds.length === 0) continue;

      const rosters = await pgSelect<RosterRow>(
        cfg,
        'rosters',
        `select=league_member_id,player_id,team_id,points_earned&round=eq.${league.current_round}&is_active=eq.true&league_member_id=in.(${memberIds.join(',')})`
      );

      const playerIds = [
        ...new Set(
          rosters
            .filter((r) => r.player_id != null)
            .map((r) => r.player_id as number)
        ),
      ];

      const playerStats =
        playerIds.length === 0
          ? []
          : await pgSelect<PlayerStatsRow>(
              cfg,
              'player_stats_cache',
              `select=player_id,team_abbreviation,goals,assists&player_id=in.(${playerIds.join(',')})&playoff_round=eq.${league.current_round}`
            );
      const statsById = new Map(playerStats.map((p) => [p.player_id, p]));

      // Only push when at least one drafted skater/team is on a live team.
      const touchesLive = rosters.some((r) => {
        if (r.player_id != null) {
          const abbrev = statsById.get(r.player_id)?.team_abbreviation;
          return !!abbrev && liveTeamAbbrevs.has(abbrev);
        }
        // For team/goalie slots: we don't have team abbrev here without
        // another join; conservatively push if any skater is live.
        return false;
      });
      if (!touchesLive) continue;

      const perPlayer: Record<string, number> = {};
      for (const r of rosters) {
        if (r.player_id != null) {
          const s = statsById.get(r.player_id);
          const pts = s
            ? calculatePlayerPoints({
                goals: s.goals ?? 0,
                assists: s.assists ?? 0,
              })
            : (r.points_earned ?? 0);
          perPlayer[String(r.player_id)] = pts;
        } else if (r.team_id != null) {
          // Server-maintained; just surface current value.
          perPlayer[`t${r.team_id}`] = r.points_earned ?? 0;
        }
      }

      perLeaguePayload[league.id] = {
        aps: {
          timestamp: Math.floor(Date.now() / 1000),
          event: 'update',
          'content-state': {
            perPlayerFantasyPoints: perPlayer,
            games: gamesSlate,
          },
        },
      };
    }

    const leagueIdsWithPayload = Object.keys(perLeaguePayload);
    if (leagueIdsWithPayload.length === 0) {
      return jsonResponse({
        message: 'No leagues touched by live games',
        pushed: 0,
      });
    }

    const tokens = await pgSelect<TokenRow>(
      cfg,
      'live_activity_tokens',
      `select=id,league_id,token,kind,bundle_id,expires_at&kind=eq.activity&league_id=in.(${leagueIdsWithPayload.join(',')})`
    );

    const jwt = await getApnsJwt(apnsKeyId, apnsTeamId, apnsP8);
    const apnsHost =
      apnsEnv === 'sandbox'
        ? 'https://api.sandbox.push.apple.com'
        : 'https://api.push.apple.com';

    let pushed = 0;
    let failed = 0;
    for (const t of tokens) {
      if (t.expires_at && new Date(t.expires_at).getTime() < Date.now())
        continue;
      const payload = perLeaguePayload[t.league_id];
      if (!payload) continue;
      const result = await sendApnsPush(
        apnsHost,
        t.bundle_id,
        t.token,
        jwt,
        payload,
        { pushType: 'liveactivity', priority: 10 }
      );
      if (result.ok) {
        pushed++;
      } else {
        failed++;
      }
    }

    return jsonResponse({ pushed, failed, liveGames: liveGames.length });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return jsonResponse({ error: message }, 500);
  }
});
