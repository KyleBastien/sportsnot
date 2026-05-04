/* eslint-disable no-console */
import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { runCodeSceneThresholdCheck } from './check-codescene-thresholds';

const NX_BIN_PATH = join(
  process.cwd(),
  'node_modules',
  'nx',
  'dist',
  'bin',
  'nx.js'
);

function runNxCommand(label: string, args: string[]): number {
  console.log(`\n→ ${label}`);

  if (!existsSync(NX_BIN_PATH)) {
    throw new Error(`Missing Nx CLI at ${NX_BIN_PATH}`);
  }

  const result = spawnSync(process.execPath, [NX_BIN_PATH, ...args], {
    encoding: 'utf8',
    maxBuffer: 20 * 1024 * 1024,
  });

  if (result.stdout) {
    process.stdout.write(result.stdout);
  }

  if (result.stderr) {
    process.stderr.write(result.stderr);
  }

  if (typeof result.status === 'number') {
    return result.status;
  }

  return 1;
}

function getStagedFiles(): string[] {
  const result = spawnSync(
    'git',
    ['diff', '--cached', '--name-only', '--diff-filter=ACMR'],
    {
      encoding: 'utf8',
    }
  );

  if (result.status !== 0) {
    throw new Error(result.stderr?.trim() || 'Failed to read staged files.');
  }

  return result.stdout
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
}

async function runPrecommit(): Promise<number> {
  const stagedFiles = getStagedFiles();

  if (stagedFiles.length === 0) {
    console.log('No staged files. Skipping pre-commit checks.');
    return 0;
  }

  const filesArg = `--files=${stagedFiles.join(',')}`;

  console.log('🔍 Pre-commit checks');
  console.log(`  Staged files: ${stagedFiles.length}`);

  const commands = [
    {
      label: 'Lint affected projects',
      args: ['affected', '-t', 'lint', filesArg, '--outputStyle=static'],
    },
    {
      label: 'Typecheck affected projects',
      args: [
        'affected',
        '-t',
        'typecheck',
        filesArg,
        '--outputStyle=static',
      ],
    },
    {
      label: 'Run unit tests for affected projects',
      args: ['affected', '-t', 'test', filesArg, '--outputStyle=static'],
    },
  ];

  for (const command of commands) {
    const exitCode = runNxCommand(command.label, command.args);

    if (exitCode !== 0) {
      return exitCode;
    }
  }

  console.log('\n→ Run CodeScene threshold check');
  const codeSceneExitCode = await runCodeSceneThresholdCheck();

  if (codeSceneExitCode !== 0) {
    return codeSceneExitCode;
  }

  console.log('\n✅ Pre-commit passed');
  return 0;
}

async function main(): Promise<void> {
  try {
    const exitCode = await runPrecommit();
    process.exitCode = exitCode;
  } catch (error) {
    const message =
      error instanceof Error ? error.message : 'Unknown pre-commit error.';
    console.error(`❌ ${message}`);
    process.exitCode = 1;
  }
}

if (fileURLToPath(import.meta.url) === process.argv[1]) {
  void main();
}
