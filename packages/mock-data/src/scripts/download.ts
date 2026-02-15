/* eslint-disable no-undef */
/**
 * Download 2025 NHL Playoff fixture data from the NHL API.
 *
 * Usage: npx tsx packages/mock-data/src/scripts/download.ts
 * Or via Nx: nx download mock-data
 *
 * Pipeline:
 *   1. getPlayoffBracket('20242025') → bracket + team abbreviations
 *   2. getTeamRoster(abbr, '20242025') × 16 teams → players
 *   3. getPlayoffSchedule('20242025') → all games, split by round
 *   4. getPlayerGameLog(id, '20242025', 3) for all players → per-game stats
 */

import { writeFile, mkdir } from 'node:fs/promises';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  getPlayoffBracket,
  getTeamRoster,
  getPlayoffSchedule,
  getPlayerGameLog,
} from '@sportsnot/nhl-api';
import type {
  NHLTeam,
  NHLPlayer,
  NHLGame,
  NHLPlayerStats,
} from '@sportsnot/types';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const DATA_DIR = join(__dirname, '..', 'data');

const SEASON = '20242025';
const MAX_CONCURRENT = 10;
const BATCH_DELAY_MS = 100;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function log(msg: string) {
  process.stdout.write(`${msg}\n`);
}

/** Run promises in batches with concurrency limit and delay between batches. */
async function batchAll<T>(
  tasks: (() => Promise<T>)[],
  concurrency: number,
  delayMs: number,
): Promise<T[]> {
  const results: T[] = [];
  for (let i = 0; i < tasks.length; i += concurrency) {
    const batch = tasks.slice(i, i + concurrency);
    const settled = await Promise.allSettled(batch.map((fn) => fn()));
    for (const r of settled) {
      if (r.status === 'fulfilled') {
        results.push(r.value);
      } else {
        log(`  ⚠ Batch item failed: ${String(r.reason)}`);
      }
    }
    if (i + concurrency < tasks.length) {
      await delay(delayMs);
    }
  }
  return results;
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function serializeConst(name: string, value: unknown, typeName: string): string {
  const json = JSON.stringify(value, null, 2);
  return `import type { ${typeName} } from '@sportsnot/types';\n\nexport const ${name} = ${json} as const satisfies readonly ${typeName}[];\n`;
}

function serializeRecordConst(
  name: string,
  value: Record<string, unknown>,
  keyType: string,
  valueType: string,
): string {
  const json = JSON.stringify(value, null, 2);
  return `import type { ${valueType} } from '@sportsnot/types';\n\nexport const ${name} = ${json} as const satisfies Readonly<Record<${keyType}, readonly ${valueType}[]>>;\n`;
}

async function writeTs(filename: string, content: string) {
  const filepath = join(DATA_DIR, filename);
  await writeFile(filepath, content, 'utf-8');
  log(`  ✓ Wrote ${filename}`);
}

// ---------------------------------------------------------------------------
// Round helpers
// ---------------------------------------------------------------------------

/** Map NHL playoff round numbers to our file suffixes. */
const ROUND_FILES: Record<number, string> = {
  1: 'games-r1.ts',
  2: 'games-r2.ts',
  3: 'games-cf.ts',
  4: 'games-scf.ts',
};

const ROUND_CONST_NAMES: Record<number, string> = {
  1: 'gamesR1',
  2: 'gamesR2',
  3: 'gamesCf',
  4: 'gamesScf',
};

function gameRound(game: NHLGame): number {
  // NHL playoff game IDs encode the round in positions.
  // The gameType field is '3' for playoffs.
  // We infer round from the game ID: format is 20XXYY0RGG
  // where R is the round number (1-4).
  const idStr = String(game.id);
  if (idStr.length >= 10) {
    const roundDigit = parseInt(idStr[7], 10);
    if (roundDigit >= 1 && roundDigit <= 4) return roundDigit;
  }
  // Fallback: try to infer from game date ordering
  return 1;
}

// ---------------------------------------------------------------------------
// Main pipeline
// ---------------------------------------------------------------------------

async function main() {
  await mkdir(DATA_DIR, { recursive: true });

  // 1. Bracket
  log('Fetching playoff bracket...');
  const bracket = await getPlayoffBracket(SEASON);
  log(`  ✓ Got ${bracket.length} series`);

  await writeTs(
    'bracket.ts',
    serializeConst('bracket', bracket, 'NHLPlayoffSeries'),
  );

  // Extract unique team abbreviations from bracket
  const teamAbbrs = new Set<string>();
  for (const series of bracket) {
    if (series.topSeedTeam?.abbreviation) teamAbbrs.add(series.topSeedTeam.abbreviation);
    if (series.bottomSeedTeam?.abbreviation) teamAbbrs.add(series.bottomSeedTeam.abbreviation);
  }
  const abbrs = [...teamAbbrs].sort();
  log(`  Found ${abbrs.length} teams: ${abbrs.join(', ')}`);

  // 2. Rosters → teams + players
  log('Fetching rosters...');
  const allTeams: NHLTeam[] = [];
  const allPlayers: Record<string, NHLPlayer[]> = {};

  const rosterTasks = abbrs.map((abbr) => async () => {
    const players = await getTeamRoster(abbr, SEASON);
    log(`  Fetching roster for ${abbr}... done (${players.length} players)`);
    return { abbr, players };
  });

  const rosterResults = await batchAll(rosterTasks, MAX_CONCURRENT, BATCH_DELAY_MS);
  for (const { abbr, players } of rosterResults) {
    allPlayers[abbr] = players;
    // Build a NHLTeam entry from the first player's currentTeam, or from bracket data
    const bracketSeries = bracket.find(
      (s) =>
        s.topSeedTeam?.abbreviation === abbr ||
        s.bottomSeedTeam?.abbreviation === abbr,
    );
    const seedTeam =
      bracketSeries?.topSeedTeam?.abbreviation === abbr
        ? bracketSeries.topSeedTeam
        : bracketSeries?.bottomSeedTeam;
    if (seedTeam) {
      allTeams.push({
        id: seedTeam.id,
        name: seedTeam.name,
        abbreviation: abbr,
        teamName: seedTeam.name,
        locationName: '',
        division: { id: 0, name: '' },
        conference: { id: 0, name: '' },
      });
    }
  }

  await writeTs('teams.ts', serializeConst('teams', allTeams, 'NHLTeam'));
  await writeTs(
    'players.ts',
    serializeRecordConst('players', allPlayers, 'string', 'NHLPlayer'),
  );

  // 3. Playoff schedule → split by round
  log('Fetching playoff schedule...');
  let games: NHLGame[] = [];
  try {
    games = await getPlayoffSchedule(SEASON);
    log(`  ✓ Got ${games.length} total games`);
  } catch (err) {
    log(`  ⚠ Failed to fetch playoff schedule: ${String(err)}`);
    log('  Falling back to empty game lists');
  }

  const gamesByRound: Record<number, NHLGame[]> = { 1: [], 2: [], 3: [], 4: [] };
  for (const game of games) {
    const round = gameRound(game);
    if (gamesByRound[round]) {
      gamesByRound[round].push(game);
    }
  }

  for (const [round, roundGames] of Object.entries(gamesByRound)) {
    const r = Number(round);
    const file = ROUND_FILES[r];
    const constName = ROUND_CONST_NAMES[r];
    if (file && constName) {
      await writeTs(file, serializeConst(constName, roundGames, 'NHLGame'));
    }
  }

  // 4. Player game logs
  log('Fetching player game logs...');
  const allPlayerIds: { id: number; name: string }[] = [];
  for (const players of Object.values(allPlayers)) {
    for (const p of players) {
      allPlayerIds.push({ id: p.id, name: p.fullName ?? `${p.firstName} ${p.lastName}` });
    }
  }
  log(`  ${allPlayerIds.length} players total`);

  const playerGameLogs: Record<number, NHLPlayerStats[]> = {};

  const logTasks = allPlayerIds.map(({ id, name }) => async () => {
    try {
      const stats = await getPlayerGameLog(id, SEASON, 3);
      return { id, name, stats };
    } catch {
      log(`  ⚠ No game log for ${name} (${id})`);
      return { id, name, stats: [] as NHLPlayerStats[] };
    }
  });

  const logResults = await batchAll(logTasks, MAX_CONCURRENT, BATCH_DELAY_MS);
  let playersWithLogs = 0;
  for (const { id, stats } of logResults) {
    if (stats.length > 0) {
      playerGameLogs[id] = stats;
      playersWithLogs++;
    }
  }
  log(`  ✓ Got game logs for ${playersWithLogs}/${allPlayerIds.length} players`);

  await writeTs(
    'player-game-logs.ts',
    serializeRecordConst(
      'playerGameLogs',
      playerGameLogs as unknown as Record<string, unknown>,
      'number',
      'NHLPlayerStats',
    ),
  );

  log('\n✅ All fixture data downloaded successfully!');
  log(`   Files written to: ${DATA_DIR}`);
}

main().catch((err) => {
  console.error('Download failed:', err);
  process.exit(1);
});
