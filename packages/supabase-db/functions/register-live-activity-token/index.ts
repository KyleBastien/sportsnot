// Supabase Edge Function: register-live-activity-token
// Called by the iOS host app to register an APNs push token (either a Live
// Activity update token or a push-to-start token) against a public league
// share code. Auth: verify_jwt = false — we authenticate via share code
// ownership only.
// Deploy: supabase functions deploy register-live-activity-token --no-verify-jwt

/// <reference path="../deno.d.ts" />

import { jsonResponse, pgInsert, pgSelect, sha256Hex } from '../_shared/pg.ts';

interface RegisterBody {
  shareCode?: string;
  token?: string;
  kind?: 'activity' | 'start';
  bundleId?: string;
  expiresAt?: string;
}

interface LeagueRow {
  id: string;
}

Deno.serve(async (req: Request) => {
  if (req.method === 'OPTIONS') return jsonResponse({}, 204);
  if (req.method !== 'POST') {
    return jsonResponse({ error: 'Method not allowed' }, 405);
  }

  try {
    const supabaseUrl = Deno.env.get('SUPABASE_URL');
    // Writes require service role (live_activity_tokens has no anon INSERT).
    const apiKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY');
    if (!supabaseUrl || !apiKey) {
      return jsonResponse(
        { error: 'Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY' },
        500
      );
    }

    const body = (await req.json().catch(() => ({}))) as RegisterBody;
    const { shareCode, token, kind, bundleId, expiresAt } = body;

    if (!shareCode || !token || !kind || !bundleId) {
      return jsonResponse(
        { error: 'shareCode, token, kind, bundleId are all required' },
        400
      );
    }
    if (kind !== 'activity' && kind !== 'start') {
      return jsonResponse({ error: 'kind must be "activity" or "start"' }, 400);
    }

    const cfg = { url: supabaseUrl, key: apiKey };

    const leagues = await pgSelect<LeagueRow>(
      cfg,
      'leagues',
      `select=id&share_code=eq.${encodeURIComponent(shareCode)}&limit=1`
    );
    if (leagues.length === 0) {
      return jsonResponse({ error: 'League not found' }, 404);
    }
    const leagueId = leagues[0].id;

    const tokenHash = await sha256Hex(token);

    const ok = await pgInsert(
      cfg,
      'live_activity_tokens',
      {
        league_id: leagueId,
        token_hash: tokenHash,
        token,
        platform: 'ios',
        kind,
        bundle_id: bundleId,
        expires_at: expiresAt ?? null,
      },
      'resolution=merge-duplicates,return=minimal'
    );

    if (!ok) {
      return jsonResponse({ error: 'Failed to register token' }, 500);
    }
    return jsonResponse({ registered: true });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return jsonResponse({ error: message }, 500);
  }
});
