// Supabase Edge Function: sync-player-stats
// Accepts a list of player IDs, fetches playoff stats from NHL API,
// and upserts into player_stats_cache.
// Deploy: supabase functions deploy sync-player-stats

import { createClient } from 'https://esm.sh/@supabase/supabase-js@2';

const NHL_API_BASE = 'https://api-web.nhle.com/v1';

interface PlayerGameLog {
  gameId: number;
  goals: number;
  assists: number;
}

Deno.serve(async (req) => {
  try {
    const supabase = createClient(
      Deno.env.get('SUPABASE_URL')!,
      Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!
    );

    const body = await req.json().catch(() => ({}));
    const playerIds: number[] = body.player_ids ?? [];
    const season: string = body.season || '20252026';
    const playoffRound: number = body.playoff_round || 1;

    if (playerIds.length === 0) {
      return new Response(
        JSON.stringify({ error: 'player_ids array is required' }),
        { status: 400, headers: { 'Content-Type': 'application/json' } }
      );
    }

    let updated = 0;
    const errors: string[] = [];

    for (const playerId of playerIds) {
      try {
        const resp = await fetch(
          `${NHL_API_BASE}/player/${playerId}/game-log/${season}/3`
        );
        if (!resp.ok) {
          errors.push(`Player ${playerId}: NHL API ${resp.status}`);
          continue;
        }

        const data = await resp.json();
        const games: PlayerGameLog[] = data.gameLog ?? [];

        const goals = games.reduce(
          (sum: number, g: PlayerGameLog) => sum + (g.goals ?? 0),
          0
        );
        const assists = games.reduce(
          (sum: number, g: PlayerGameLog) => sum + (g.assists ?? 0),
          0
        );

        await supabase.from('player_stats_cache').upsert(
          {
            player_id: playerId,
            nhl_season: season,
            playoff_round: playoffRound,
            goals,
            assists,
            games_played: games.length,
            last_updated: new Date().toISOString(),
          },
          { onConflict: 'player_id,nhl_season,playoff_round' }
        );

        updated++;
      } catch {
        errors.push(`Player ${playerId}: unexpected error`);
      }
    }

    return new Response(
      JSON.stringify({
        message: 'Player stats synced',
        updated,
        total: playerIds.length,
        errors: errors.length > 0 ? errors : undefined,
      }),
      { headers: { 'Content-Type': 'application/json' } }
    );
  } catch (error) {
    return new Response(JSON.stringify({ error: (error as Error).message }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }
});
