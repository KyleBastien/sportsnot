// Supabase Edge Function: sync-team-stats
// Accepts a list of team abbreviations, fetches playoff stats from NHL API,
// and upserts into team_stats_cache.
// Deploy: supabase functions deploy sync-team-stats

import { createClient } from 'https://esm.sh/@supabase/supabase-js@2';

const NHL_API_BASE = 'https://api-web.nhle.com/v1';

interface PlayoffSeries {
  topSeedTeam?: { id: number; name: string; abbrev?: string };
  bottomSeedTeam?: { id: number; name: string; abbrev?: string };
  topSeedWins?: number;
  bottomSeedWins?: number;
}

interface ScheduleGame {
  id: number;
  gameType: number;
  gameState: string;
  homeTeam: { id: number; abbrev: string; score?: number };
  awayTeam: { id: number; abbrev: string; score?: number };
}

Deno.serve(async (req) => {
  try {
    const supabase = createClient(
      Deno.env.get('SUPABASE_URL')!,
      Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!
    );

    const body = await req.json().catch(() => ({}));
    const teamAbbreviations: string[] = body.team_abbreviations ?? [];
    const season: string = body.season || '20252026';
    const playoffRound: number = body.playoff_round || 1;

    if (teamAbbreviations.length === 0) {
      return new Response(
        JSON.stringify({ error: 'team_abbreviations array is required' }),
        { status: 400, headers: { 'Content-Type': 'application/json' } }
      );
    }

    // Fetch playoff bracket to determine eliminations and team IDs
    const bracketResp = await fetch(
      `${NHL_API_BASE}/playoff-bracket/${season}`
    );
    const bracketData = bracketResp.ok
      ? await bracketResp.json()
      : { rounds: [] };
    const allSeries: PlayoffSeries[] = (bracketData.rounds ?? []).flatMap(
      (r: { series: PlayoffSeries[] }) => r.series
    );

    // Build eliminated team IDs set
    const eliminatedIds = new Set<number>();
    for (const s of allSeries) {
      if (!s.topSeedTeam || !s.bottomSeedTeam) continue;
      if ((s.topSeedWins ?? 0) === 4) eliminatedIds.add(s.bottomSeedTeam.id);
      else if ((s.bottomSeedWins ?? 0) === 4)
        eliminatedIds.add(s.topSeedTeam.id);
    }

    // Build abbrev -> team ID map from bracket data
    const abbrevToId = new Map<string, number>();
    const abbrevToName = new Map<string, string>();
    for (const s of allSeries) {
      if (s.topSeedTeam?.abbrev) {
        abbrevToId.set(s.topSeedTeam.abbrev, s.topSeedTeam.id);
        abbrevToName.set(s.topSeedTeam.abbrev, s.topSeedTeam.name);
      }
      if (s.bottomSeedTeam?.abbrev) {
        abbrevToId.set(s.bottomSeedTeam.abbrev, s.bottomSeedTeam.id);
        abbrevToName.set(s.bottomSeedTeam.abbrev, s.bottomSeedTeam.name);
      }
    }

    // Fetch recent scores to count wins/shutouts
    const scoresResp = await fetch(`${NHL_API_BASE}/score/now`);
    const scoresData = scoresResp.ok ? await scoresResp.json() : { games: [] };
    const games: ScheduleGame[] = scoresData.games ?? [];

    let updated = 0;
    const errors: string[] = [];

    for (const abbrev of teamAbbreviations) {
      try {
        const teamId = abbrevToId.get(abbrev);
        if (!teamId) {
          errors.push(`Team ${abbrev}: could not resolve team ID`);
          continue;
        }

        let wins = 0;
        let shutouts = 0;

        for (const game of games) {
          if (game.gameType !== 3 || game.gameState !== 'FINAL') continue;

          const isHome = game.homeTeam?.abbrev === abbrev;
          const isAway = game.awayTeam?.abbrev === abbrev;
          if (!isHome && !isAway) continue;

          const teamScore = isHome
            ? game.homeTeam?.score
            : game.awayTeam?.score;
          const opponentScore = isHome
            ? game.awayTeam?.score
            : game.homeTeam?.score;

          if (teamScore != null && opponentScore != null && teamScore > opponentScore) {
            wins++;
            if (opponentScore === 0) shutouts++;
          }
        }

        await supabase.from('team_stats_cache').upsert(
          {
            team_id: teamId,
            nhl_season: season,
            playoff_round: playoffRound,
            team_name: abbrevToName.get(abbrev) ?? null,
            team_abbreviation: abbrev,
            wins,
            shutouts,
            is_eliminated: eliminatedIds.has(teamId),
            last_updated: new Date().toISOString(),
          },
          { onConflict: 'team_id,nhl_season,playoff_round' }
        );

        updated++;
      } catch {
        errors.push(`Team ${abbrev}: unexpected error`);
      }
    }

    return new Response(
      JSON.stringify({
        message: 'Team stats synced',
        updated,
        total: teamAbbreviations.length,
        errors: errors.length > 0 ? errors : undefined,
      }),
      { headers: { 'Content-Type': 'application/json' } }
    );
  } catch (error) {
    return new Response(
      JSON.stringify({ error: (error as Error).message }),
      { status: 500, headers: { 'Content-Type': 'application/json' } }
    );
  }
});
