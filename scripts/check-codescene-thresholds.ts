/* eslint-disable no-console */
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const THRESHOLDS_PATH = join(process.cwd(), '.codescene-thresholds');
const DEFAULT_API_BASE_URL = 'https://api.codescene.io/v2';

type ThresholdConfigMap = Record<string, string>;

interface ThresholdConfig {
  projectId?: string;
  hotspotThreshold: number;
  averageThreshold: number;
  allowRecoveryMode: boolean;
}

interface CodeSceneProjectResponse {
  analysis?: {
    hotspot_code_health?: {
      now?: number;
    };
    code_health?: {
      now?: number;
    };
  };
}

interface CodeSceneScores {
  hotspotScore: number;
  averageScore: number;
}

function isFiniteNumber(value: number | undefined): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

function parseConfig(rawText: string): ThresholdConfigMap {
  return rawText
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line.length > 0 && !line.startsWith('#'))
    .reduce<ThresholdConfigMap>((config, line) => {
      const separatorIndex = line.indexOf('=');
      if (separatorIndex === -1) {
        return config;
      }

      const key = line.slice(0, separatorIndex).trim();
      const value = line.slice(separatorIndex + 1).trim();

      if (key.length > 0) {
        config[key] = value;
      }

      return config;
    }, {});
}

function parseNumber(value: string | undefined, key: string): number {
  const parsedValue = Number(value);

  if (!Number.isFinite(parsedValue)) {
    throw new Error(`Invalid numeric value for ${key}: "${value}"`);
  }

  return parsedValue;
}

function parseBoolean(value: string | undefined): boolean {
  return value?.toLowerCase() === 'true';
}

function formatScore(score: number): string {
  return score.toFixed(2);
}

function readThresholdConfig(): ThresholdConfig {
  if (!existsSync(THRESHOLDS_PATH)) {
    throw new Error(`Missing threshold file: ${THRESHOLDS_PATH}`);
  }

  const rawText = readFileSync(THRESHOLDS_PATH, 'utf8');
  const config = parseConfig(rawText);

  return {
    projectId: config.CODESCENE_PROJECT_ID,
    hotspotThreshold: parseNumber(
      config.HOTSPOT_THRESHOLD,
      'HOTSPOT_THRESHOLD'
    ),
    averageThreshold: parseNumber(
      config.AVERAGE_THRESHOLD,
      'AVERAGE_THRESHOLD'
    ),
    allowRecoveryMode: parseBoolean(config.ALLOW_RECOVERY_MODE),
  };
}

async function fetchProjectScores(
  projectId: string,
  token: string
): Promise<CodeSceneScores> {
  const response = await fetch(
    `${DEFAULT_API_BASE_URL}/projects/${projectId}`,
    {
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: 'application/json',
      },
    }
  );

  if (!response.ok) {
    const errorBody = await response.text();
    throw new Error(
      `CodeScene API request failed (${response.status} ${response.statusText}): ${errorBody}`
    );
  }

  const payload = (await response.json()) as CodeSceneProjectResponse;
  const hotspotScore = payload.analysis?.hotspot_code_health?.now;
  const averageScore = payload.analysis?.code_health?.now;

  if (!isFiniteNumber(hotspotScore) || !isFiniteNumber(averageScore)) {
    throw new Error('CodeScene response did not include numeric score data.');
  }

  return {
    hotspotScore,
    averageScore,
  };
}

export async function runCodeSceneThresholdCheck(): Promise<number> {
  try {
    const token =
      process.env.CODESCENE_PAT ?? process.env.CODESCENE_ACCESS_TOKEN;

    if (!token) {
      throw new Error(
        'Set CODESCENE_PAT or CODESCENE_ACCESS_TOKEN before committing.'
      );
    }

    const { projectId, hotspotThreshold, averageThreshold, allowRecoveryMode } =
      readThresholdConfig();

    if (!projectId) {
      throw new Error(
        'CODESCENE_PROJECT_ID is missing from .codescene-thresholds.'
      );
    }

    const { hotspotScore, averageScore } = await fetchProjectScores(
      projectId,
      token
    );

    console.log('🏥 CodeScene threshold check');
    console.log(
      `  Hotspot Code Health: ${formatScore(hotspotScore)} (threshold: ${formatScore(hotspotThreshold)})`
    );
    console.log(
      `  Average Code Health: ${formatScore(averageScore)} (threshold: ${formatScore(averageThreshold)})`
    );

    const belowThreshold =
      hotspotScore < hotspotThreshold || averageScore < averageThreshold;

    if (!belowThreshold) {
      console.log('✅ CodeScene thresholds passed');
      return 0;
    }

    if (allowRecoveryMode) {
      console.log(
        '⚠️  CodeScene baseline is below threshold, but recovery mode is enabled.'
      );
      console.log(
        '   Land refactors that improve the baseline, then raise thresholds in the same branch.'
      );
      return 0;
    }

    console.error('❌ CodeScene thresholds failed');
    return 1;
  } catch (error) {
    const message =
      error instanceof Error ? error.message : 'Unknown CodeScene error.';
    console.error(`❌ ${message}`);
    return 1;
  }
}

async function main(): Promise<void> {
  const exitCode = await runCodeSceneThresholdCheck();
  process.exitCode = exitCode;
}

if (fileURLToPath(import.meta.url) === process.argv[1]) {
  void main();
}
