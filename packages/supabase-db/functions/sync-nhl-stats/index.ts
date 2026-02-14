// Supabase Edge Function: sync-nhl-stats
// Fetches latest playoff stats from NHL API and updates the cache tables
// Deploy: supabase functions deploy sync-nhl-stats
// Schedule via cron or invoke manually

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
    const season = body.season || '20252026';
    const playoffRound = body.playoff_round || 1;

    // Get all active rosters to know which players/teams to sync
    const { data: rosters } = await supabase
      .from('rosters')
      .select('player_id, team_id, position')
      .eq('round', playoffRound)
      .eq('is_active', true);

    if (!rosters || rosters.length === 0) {
      return new Response(
        JSON.stringify({ message: 'No active rosters to sync' }),
        {
          headers: { 'Content-Type': 'application/json' },
        }
      );
    }

    // Unique player IDs and team IDs
    const playerIds = [
      ...new Set(rosters.filter((r) => r.player_id).map((r) => r.player_id!)),
    ];
    const teamIds = [
      ...new Set(rosters.filter((r) => r.team_id).map((r) => r.team_id!)),
    ];

    let playerUpdates = 0;
    let teamUpdates = 0;

    // Sync player stats
    for (const playerId of playerIds) {
      try {
        const resp = await fetch(
          `${NHL_API_BASE}/player/${playerId}/game-log/${season}/3`
        );
        if (!resp.ok) continue;

        const data = await resp.json();
        const games: PlayerGameLog[] = data.gameLog ?? [];

        const totalGoals = games.reduce(
          (sum: number, g: PlayerGameLog) => sum + (g.goals ?? 0),
          0
        );
        const totalAssists = games.reduce(
          (sum: number, g: PlayerGameLog) => sum + (g.assists ?? 0),
          0
        );

        await supabase.from('player_stats_cache').upsert(
          {
            player_id: playerId,
            nhl_season: season,
            playoff_round: playoffRound,
            goals: totalGoals,
            assists: totalAssists,
            games_played: games.length,
            last_updated: new Date().toISOString(),
          },
          { onConflict: 'player_id,nhl_season,playoff_round' }
        );

        playerUpdates++;
      } catch {
        // Continue on individual player failures
      }
    }

    // Sync team stats (wins/shutouts) - check recent game scores
    for (const teamId of teamIds) {
      try {
        const resp = await fetch(`${NHL_API_BASE}/score/now`);
        if (!resp.ok) continue;

        const data = await resp.json();
        const games = data.games ?? [];

        // Count wins and shutouts for this team in completed playoff games
        let wins = 0;
        let shutouts = 0;

        for (const game of games) {
          if (game.gameType !== 3 || game.gameState !== 'FINAL') continue;

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

        await supabase.from('team_stats_cache').upsert(
          {
            team_id: teamId,
            nhl_season: season,
            playoff_round: playoffRound,
            wins,
            shutouts,
            last_updated: new Date().toISOString(),
          },
          { onConflict: 'team_id,nhl_season,playoff_round' }
        );

        teamUpdates++;
      } catch {
        // Continue on individual team failures
      }
    }

    return new Response(
      JSON.stringify({
        message: 'Stats synced successfully',
        playerUpdates,
        teamUpdates,
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
