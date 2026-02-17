// Supabase Edge Function: sync-nhl-stats
// Fetches latest playoff stats from NHL API and updates the cache tables
// Deploy: supabase functions deploy sync-nhl-stats
// Schedule via cron or invoke manually

import { createClient } from 'https://esm.sh/@supabase/supabase-js@2';

const NHL_API_BASE = 'https://api-web.nhle.com/v1';

interface PlayerGameLog {
  gameId: number;
  gameDate: string;
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
    // Optional round date boundaries for filtering game stats
    const roundStartDate: string | undefined = body.round_start_date;
    const roundEndDate: string | undefined = body.round_end_date;

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
        const allGames: PlayerGameLog[] = data.gameLog ?? [];

        // Filter to round-specific date range when provided
        const games =
          roundStartDate && roundEndDate
            ? allGames.filter(
                (g) => g.gameDate >= roundStartDate && g.gameDate <= roundEndDate
              )
            : allGames;

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

          // Filter by round date range when provided
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

    // ── Update roster points_earned from stats cache ──────────────────
    // Player roster slots: points = goals * 1 + assists * 1
    const SCORING_GOAL = 1;
    const SCORING_ASSIST = 1;
    const SCORING_WIN = 2;
    const SCORING_SHUTOUT = 4;

    for (const playerId of playerIds) {
      const { data: stats } = await supabase
        .from('player_stats_cache')
        .select('goals, assists')
        .eq('player_id', playerId)
        .eq('nhl_season', season)
        .eq('playoff_round', playoffRound)
        .single();

      if (stats) {
        const pts =
          (stats.goals ?? 0) * SCORING_GOAL +
          (stats.assists ?? 0) * SCORING_ASSIST;
        await supabase
          .from('rosters')
          .update({ points_earned: pts })
          .eq('player_id', playerId)
          .eq('round', playoffRound)
          .eq('is_active', true);
      }
    }

    // Goalie roster slots: points from team wins/shutouts
    for (const teamId of teamIds) {
      const { data: stats } = await supabase
        .from('team_stats_cache')
        .select('wins, shutouts')
        .eq('team_id', teamId)
        .eq('nhl_season', season)
        .eq('playoff_round', playoffRound)
        .single();

      if (stats) {
        const regularWins = (stats.wins ?? 0) - (stats.shutouts ?? 0);
        const pts =
          regularWins * SCORING_WIN + (stats.shutouts ?? 0) * SCORING_SHUTOUT;
        await supabase
          .from('rosters')
          .update({ points_earned: pts })
          .eq('team_id', teamId)
          .eq('round', playoffRound)
          .eq('is_active', true);
      }
    }

    // ── Aggregate roster points into league_members standings ────────
    // Find all leagues that have active rosters for this round
    const { data: affectedMembers } = await supabase
      .from('rosters')
      .select('league_member_id')
      .eq('round', playoffRound)
      .eq('is_active', true);

    if (affectedMembers && affectedMembers.length > 0) {
      const memberIds = [
        ...new Set(affectedMembers.map((r) => r.league_member_id)),
      ];

      // Get the league IDs for affected members
      const { data: members } = await supabase
        .from('league_members')
        .select('id, league_id')
        .in('id', memberIds);

      if (members) {
        const leagueIds = [...new Set(members.map((m) => m.league_id))];
        for (const leagueId of leagueIds) {
          await supabase.rpc('refresh_league_standings', {
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
    return new Response(JSON.stringify({ error: (error as Error).message }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }
});
