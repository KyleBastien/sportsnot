/// <reference path="../deno.d.ts" />

import {
  derivePlayoffRoundsToSync,
  getEffectiveRoundEndDate,
  getPlayoffRoundWindow,
} from '../_shared/playoff-rounds.ts';
import { jsonResponse, pgSelect, type PgConfig } from '../_shared/pg.ts';
import {
  fetchEligibleRoundPlayers,
  fetchEligibleRoundTeams,
  fetchLivePlayerDeltas,
  fetchRoundGames,
  isCompletedGame,
} from './syncNhlStatsApi.ts';
import {
  refreshActiveLeagueStandings,
  syncRoundPlayerStats,
  syncRoundTeamStats,
  updateRoundRosterPoints,
} from './syncNhlStatsDb.ts';
import {
  DEFAULT_SEASON,
  type LeagueRow,
  NHL_API_BASE,
} from './syncNhlStatsTypes.ts';

function parseRequestedRound(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === 'string' && value.trim().length > 0) {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  return null;
}

async function fetchJson<T>(url: string): Promise<T | null> {
  try {
    const response = await fetch(url);
    if (!response.ok) {
      return null;
    }
    return (await response.json()) as T;
  } catch {
    return null;
  }
}

Deno.serve(async (req: Request) => {
  try {
    const supabaseUrl = Deno.env.get('SUPABASE_URL');
    const supabaseKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY');

    if (!supabaseUrl || !supabaseKey) {
      return jsonResponse(
        {
          error: 'Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY',
        },
        500
      );
    }

    const cfg: PgConfig = {
      url: supabaseUrl,
      key: supabaseKey,
    };

    const body = await req.json().catch(() => ({}));
    const season: string = body.season || DEFAULT_SEASON;
    const requestedRound = parseRequestedRound(body.playoff_round);
    const overrideStartDate =
      typeof body.round_start_date === 'string'
        ? body.round_start_date
        : undefined;
    const overrideEndDate =
      typeof body.round_end_date === 'string' ? body.round_end_date : undefined;

    const activeLeagues = await pgSelect<LeagueRow>(
      cfg,
      'leagues',
      'select=id,current_round,status&status=in.(active,drafting)&current_round=gte.1'
    );
    const roundsToSync =
      requestedRound != null
        ? [requestedRound]
        : derivePlayoffRoundsToSync(activeLeagues);

    if (roundsToSync.length === 0) {
      return jsonResponse({
        message: 'No active or drafting league rounds to sync',
        syncedRounds: [],
        playerUpdates: 0,
        teamUpdates: 0,
      });
    }

    let playerUpdates = 0;
    let teamUpdates = 0;
    const syncedRounds: number[] = [];

    for (const playoffRound of roundsToSync) {
      const roundWindow = getPlayoffRoundWindow(
        season,
        playoffRound,
        requestedRound === playoffRound ? overrideStartDate : undefined,
        requestedRound === playoffRound ? overrideEndDate : undefined
      );

      if (!roundWindow) {
        if (requestedRound === playoffRound) {
          return jsonResponse(
            {
              error: `No configured round window for season ${season} round ${playoffRound}`,
            },
            400
          );
        }
        continue;
      }

      const eligibleTeams = await fetchEligibleRoundTeams(season, playoffRound);
      if (eligibleTeams.length === 0) {
        continue;
      }

      const eligiblePlayers = await fetchEligibleRoundPlayers(
        season,
        eligibleTeams
      );
      const liveDeltas = await fetchLivePlayerDeltas(playoffRound);
      const effectiveRoundEndDate = getEffectiveRoundEndDate(roundWindow);
      const roundGames = await fetchRoundGames(
        playoffRound,
        roundWindow.startDate,
        effectiveRoundEndDate
      );
      const finalGames = roundGames.filter(isCompletedGame);
      const finalizedGameIds = new Set(finalGames.map((game) => game.id));

      playerUpdates += await syncRoundPlayerStats(
        cfg,
        season,
        playoffRound,
        eligiblePlayers,
        finalizedGameIds,
        liveDeltas,
        fetchJson,
        NHL_API_BASE
      );
      teamUpdates += await syncRoundTeamStats(
        cfg,
        season,
        playoffRound,
        eligibleTeams,
        finalGames
      );
      await updateRoundRosterPoints(cfg, season, playoffRound);
      await refreshActiveLeagueStandings(cfg, activeLeagues, playoffRound);

      syncedRounds.push(playoffRound);
    }

    return jsonResponse({
      message: 'Stats synced and standings updated',
      syncedRounds,
      playerUpdates,
      teamUpdates,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return jsonResponse({ error: message }, 500);
  }
});
