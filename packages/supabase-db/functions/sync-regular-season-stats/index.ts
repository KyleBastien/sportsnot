// Supabase Edge Function: sync-regular-season-stats
// Fetches regular season stats from NHL API for all playoff-eligible players
// and populates the regular_season_stats_cache table.
//
// Deploy: supabase functions deploy sync-regular-season-stats
// Invoke manually or on a schedule before the Round 1 draft.
//
// Request body:
//   season (string)        — NHL season code, e.g. '20252026' (default)
//   team_abbreviations     — array of team abbreviations to sync, e.g. ['TOR','EDM']
//                            If omitted, fetches all teams from the playoff bracket.

/// <reference path="../deno.d.ts" />

const NHL_API_BASE = 'https://api-web.nhle.com/v1';

interface RawRosterPlayer {
  id: number;
  firstName: { default: string };
  lastName: { default: string };
  positionCode: string;
}

interface GameLogEntry {
  goals: number;
  assists: number;
}

interface RawBracketTeam {
  abbrev: string;
}

interface RawBracketSeries {
  topSeedTeam?: RawBracketTeam;
  bottomSeedTeam?: RawBracketTeam;
}

interface PlayerInfo {
  id: number;
  name: string;
  position: 'F' | 'D' | 'G';
  teamAbbrev: string;
}

/** Map NHL position codes to our simplified position categories. */
function mapPosition(positionCode: string): 'F' | 'D' | 'G' {
  if (positionCode === 'D') return 'D';
  if (positionCode === 'G') return 'G';
  return 'F';
}

/** Convert 8-digit season to 4-digit bracket year. */
function seasonToBracketYear(season: string): string {
  return season.length === 8 ? season.slice(4) : season;
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
        { status: 500, headers: { 'Content-Type': 'application/json' } }
      );
    }

    const body = await req.json().catch(() => ({}));
    const season: string = body.season || '20252026';
    const teamAbbreviations: string[] | undefined = body.team_abbreviations;

    // ── Determine which teams to sync ──────────────────────────────
    let abbrevs: string[] = [];

    if (teamAbbreviations && teamAbbreviations.length > 0) {
      abbrevs = teamAbbreviations;
    } else {
      // Fetch from playoff bracket
      try {
        const bracketYear = seasonToBracketYear(season);
        const bracketResp = await fetch(
          `${NHL_API_BASE}/playoff-bracket/${bracketYear}`
        );
        if (bracketResp.ok) {
          const bracketData = await bracketResp.json();
          const series: RawBracketSeries[] = bracketData.series ?? [];
          const teamSet = new Set<string>();
          for (const s of series) {
            if (s.topSeedTeam?.abbrev) teamSet.add(s.topSeedTeam.abbrev);
            if (s.bottomSeedTeam?.abbrev) teamSet.add(s.bottomSeedTeam.abbrev);
          }
          abbrevs = [...teamSet].sort();
        }
      } catch {
        // Bracket not available yet
      }
    }

    if (abbrevs.length === 0) {
      return new Response(
        JSON.stringify({
          message:
            'No teams found. Provide team_abbreviations or wait for the playoff bracket to be published.',
        }),
        { headers: { 'Content-Type': 'application/json' } }
      );
    }

    // ── Fetch rosters for each team ────────────────────────────────
    const players: PlayerInfo[] = [];

    for (const abbrev of abbrevs) {
      try {
        const rosterResp = await fetch(
          `${NHL_API_BASE}/roster/${abbrev}/${season}`
        );
        if (!rosterResp.ok) continue;

        const rosterData = await rosterResp.json();
        const allRaw: RawRosterPlayer[] = [
          ...(rosterData.forwards ?? []),
          ...(rosterData.defensemen ?? []),
          ...(rosterData.goalies ?? []),
        ];

        for (const p of allRaw) {
          players.push({
            id: p.id,
            name: `${p.firstName.default} ${p.lastName.default}`,
            position: mapPosition(p.positionCode),
            teamAbbrev: abbrev,
          });
        }
      } catch {
        // Skip teams whose roster can't be fetched
      }
    }

    if (players.length === 0) {
      return new Response(
        JSON.stringify({ message: 'No players found on team rosters' }),
        { headers: { 'Content-Type': 'application/json' } }
      );
    }

    // ── Fetch regular season game logs and aggregate stats ─────────
    let synced = 0;
    let failed = 0;

    // Process in batches to avoid overwhelming the NHL API
    const BATCH_SIZE = 5;
    const BATCH_DELAY_MS = 500;

    for (let i = 0; i < players.length; i += BATCH_SIZE) {
      const batch = players.slice(i, i + BATCH_SIZE);

      const results = await Promise.allSettled(
        batch.map(async (player) => {
          const resp = await fetch(
            `${NHL_API_BASE}/player/${player.id}/game-log/${season}/2`
          );
          if (!resp.ok) {
            throw new Error(`HTTP ${resp.status}`);
          }

          const data = await resp.json();
          const games: GameLogEntry[] = data.gameLog ?? [];

          const goals = games.reduce(
            (sum: number, g: GameLogEntry) => sum + (g.goals ?? 0),
            0
          );
          const assists = games.reduce(
            (sum: number, g: GameLogEntry) => sum + (g.assists ?? 0),
            0
          );

          return {
            player_id: player.id,
            nhl_season: season,
            player_name: player.name,
            team_abbreviation: player.teamAbbrev,
            position: player.position,
            goals,
            assists,
            points: goals + assists,
            games_played: games.length,
            last_updated: new Date().toISOString(),
          };
        })
      );

      const rows = results
        .filter(
          (
            r
          ): r is PromiseFulfilledResult<{
            player_id: number;
            nhl_season: string;
            player_name: string;
            team_abbreviation: string;
            position: 'F' | 'D' | 'G';
            goals: number;
            assists: number;
            points: number;
            games_played: number;
            last_updated: string;
          }> => r.status === 'fulfilled'
        )
        .map((r) => r.value);

      failed += results.length - rows.length;

      if (rows.length > 0) {
        try {
          const upsertResp = await fetch(
            `${supabaseUrl}/rest/v1/regular_season_stats_cache?on_conflict=player_id,nhl_season`,
            {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
                apikey: supabaseKey,
                Authorization: `Bearer ${supabaseKey}`,
                Prefer: 'resolution=merge-duplicates',
              },
              body: JSON.stringify(rows),
            }
          );
          if (upsertResp.ok) {
            synced += rows.length;
          } else {
            failed += rows.length;
          }
        } catch {
          failed += rows.length;
        }
      }

      // Delay between batches
      if (i + BATCH_SIZE < players.length) {
        await new Promise((resolve) => setTimeout(resolve, BATCH_DELAY_MS));
      }
    }

    return new Response(
      JSON.stringify({
        message: 'Regular season stats synced',
        teams: abbrevs.length,
        playersFound: players.length,
        playersSynced: synced,
        playersFailed: failed,
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
