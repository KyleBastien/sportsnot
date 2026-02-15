#!/usr/bin/env node
/* eslint-disable no-undef */
/**
 * verify-no-mock-in-bundle.mjs
 *
 * CI check that ensures zero mock mode code ships in production builds.
 * Run after `nx build web` with VITE_MOCK_MODE unset (defaults to 'false').
 *
 * Usage:
 *   node scripts/verify-no-mock-in-bundle.mjs
 *
 * Exit codes:
 *   0 — No mock identifiers found (pass)
 *   1 — Mock identifiers detected in production bundle (fail)
 */

import { readFileSync, readdirSync } from 'fs';
import { join } from 'path';

const DIST_DIR = join(process.cwd(), 'packages', 'web', 'dist');

// Known mock identifiers that must NOT appear in the production bundle
const MOCK_IDENTIFIERS = [
  // Components
  'MockDataProvider',
  'MockModeBanner',
  'SimulationControlPanel',
  'MockAuthProvider',
  'BotAutoPickRunner',
  // Hooks
  'useMockData',
  'useMockDraft',
  'useMockLeagues',
  'useMockRoster',
  'useMockStandings',
  'useMockScoringHistory',
  'useMockLiveGames',
  'useMockPlayoffBracket',
  'useMockNhlApi',
  'useMockAuth',
  'useMockMyLeagues',
  'useMockCreateLeague',
  'useMockStartDraft',
  'useMockMakePick',
  // Actions / state
  'ADVANCE_DAY',
  'ADVANCE_ROUND',
  'ACTIVATE_IR',
  'DEACTIVATE_IR',
  'RESET_ALL',
  // Mock data identifiers
  'mock-user-001',
  'mockGetScoresNow',
  'isMockMode',
  'mockHooksRegistry',
  // Fixture data (team names from stub data)
  'Edmonton Oilers',
  'Florida Panthers',
  'Dallas Stars',
  'Carolina Hurricanes',
];

let jsFiles;
try {
  jsFiles = readdirSync(DIST_DIR).filter((f) => f.endsWith('.js'));
} catch {
  console.error(`❌ dist directory not found: ${DIST_DIR}`);
  console.error('   Run "nx build web" first.');
  process.exit(1);
}

if (jsFiles.length === 0) {
  console.error(`❌ No .js files found in ${DIST_DIR}`);
  process.exit(1);
}

console.log(`Scanning ${jsFiles.length} JS file(s) in ${DIST_DIR}...\n`);

const violations = [];

for (const file of jsFiles) {
  const content = readFileSync(join(DIST_DIR, file), 'utf-8');
  for (const identifier of MOCK_IDENTIFIERS) {
    if (content.includes(identifier)) {
      violations.push({ file, identifier });
    }
  }
}

if (violations.length > 0) {
  console.error('❌ FAIL: Mock identifiers found in production bundle!\n');
  for (const { file, identifier } of violations) {
    console.error(`   ${file}: "${identifier}"`);
  }
  console.error(
    '\nMock mode code is leaking into the production bundle.'
  );
  console.error(
    'Ensure all mock imports use dynamic import() inside build-time guards:'
  );
  console.error(
    "  if (import.meta.env.VITE_MOCK_MODE === 'true') { ... }\n"
  );
  process.exit(1);
} else {
  console.log('✅ PASS: No mock identifiers found in production bundle.');
  console.log(`   Checked ${MOCK_IDENTIFIERS.length} identifiers across ${jsFiles.length} file(s).`);
  process.exit(0);
}
