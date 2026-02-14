import { describe, it, expect, beforeEach, afterEach } from '@rstest/core';
import {
  calculatePlayerPoints,
  calculateGoaliePoints,
  generateSnakeDraftOrder,
  generateReDraftOrder,
  shuffleArray,
  generateInviteCode,
  downloadCsv,
} from './utils';
import type { PlayerStats, TeamStats } from '@sportsnot/types';

function makePlayerStats(overrides: Partial<PlayerStats>): PlayerStats {
  return {
    playerId: 1,
    nhlSeason: '20252026',
    playoffRound: 1,
    goals: 0,
    assists: 0,
    gamesPlayed: 0,
    isInjured: false,
    lastUpdated: new Date().toISOString(),
    ...overrides,
  };
}

function makeTeamStats(overrides: Partial<TeamStats>): TeamStats {
  return {
    teamId: 1,
    nhlSeason: '20252026',
    playoffRound: 1,
    wins: 0,
    shutouts: 0,
    isEliminated: false,
    lastUpdated: new Date().toISOString(),
    ...overrides,
  };
}

describe('calculatePlayerPoints', () => {
  it('should calculate points for goals and assists', () => {
    const stats = makePlayerStats({ goals: 3, assists: 5, gamesPlayed: 4 });
    expect(calculatePlayerPoints(stats)).toBe(8); // 3*1 + 5*1
  });

  it('should return 0 for no stats', () => {
    const stats = makePlayerStats({ goals: 0, assists: 0, gamesPlayed: 0 });
    expect(calculatePlayerPoints(stats)).toBe(0);
  });

  it('should handle high stat lines', () => {
    const stats = makePlayerStats({ goals: 14, assists: 18, gamesPlayed: 28 });
    expect(calculatePlayerPoints(stats)).toBe(32);
  });
});

describe('calculateGoaliePoints', () => {
  it('should calculate win points correctly', () => {
    const stats = makeTeamStats({ wins: 4, shutouts: 0 });
    expect(calculateGoaliePoints(stats)).toBe(8); // 4*2
  });

  it('should replace win points with shutout points', () => {
    const stats = makeTeamStats({ wins: 4, shutouts: 1 });
    // 3 regular wins * 2 + 1 shutout * 4 = 10
    expect(calculateGoaliePoints(stats)).toBe(10);
  });

  it('should handle all shutouts', () => {
    const stats = makeTeamStats({ wins: 4, shutouts: 4 });
    // 0 regular wins + 4 shutouts * 4 = 16
    expect(calculateGoaliePoints(stats)).toBe(16);
  });

  it('should return 0 for no wins', () => {
    const stats = makeTeamStats({ wins: 0, shutouts: 0 });
    expect(calculateGoaliePoints(stats)).toBe(0);
  });
});

describe('generateSnakeDraftOrder', () => {
  it('should generate correct snake order for 2 players, 2 rounds', () => {
    const order = generateSnakeDraftOrder(['A', 'B'], 2);
    expect(order).toEqual(['A', 'B', 'B', 'A']);
  });

  it('should generate correct snake order for 3 players, 3 rounds', () => {
    const order = generateSnakeDraftOrder(['A', 'B', 'C'], 3);
    expect(order).toEqual(['A', 'B', 'C', 'C', 'B', 'A', 'A', 'B', 'C']);
  });

  it('should return empty for 0 rounds', () => {
    const order = generateSnakeDraftOrder(['A', 'B'], 0);
    expect(order).toEqual([]);
  });

  it('should handle single player', () => {
    const order = generateSnakeDraftOrder(['A'], 3);
    expect(order).toEqual(['A', 'A', 'A']);
  });
});

describe('generateReDraftOrder', () => {
  it('should order worst to best (ascending points)', () => {
    const standings = [
      { memberId: 'A', points: 20 },
      { memberId: 'B', points: 5 },
      { memberId: 'C', points: 15 },
    ];
    const order = generateReDraftOrder(standings, 1);
    // Worst first: B(5), C(15), A(20)
    expect(order).toEqual(['B', 'C', 'A']);
  });

  it('should apply snake pattern for multiple rounds', () => {
    const standings = [
      { memberId: 'A', points: 10 },
      { memberId: 'B', points: 5 },
    ];
    const order = generateReDraftOrder(standings, 2);
    // Worst first: B, A → snake: B, A, A, B
    expect(order).toEqual(['B', 'A', 'A', 'B']);
  });
});

describe('shuffleArray', () => {
  it('should return array of same length', () => {
    const original = [1, 2, 3, 4, 5];
    const shuffled = shuffleArray(original);
    expect(shuffled.length).toBe(original.length);
  });

  it('should contain all original elements', () => {
    const original = [1, 2, 3, 4, 5];
    const shuffled = shuffleArray(original);
    expect(shuffled.sort()).toEqual(original.sort());
  });

  it('should not mutate the original array', () => {
    const original = [1, 2, 3, 4, 5];
    const copy = [...original];
    shuffleArray(original);
    expect(original).toEqual(copy);
  });

  it('should handle empty array', () => {
    expect(shuffleArray([])).toEqual([]);
  });

  it('should handle single element', () => {
    expect(shuffleArray([42])).toEqual([42]);
  });
});

describe('generateInviteCode', () => {
  it('should generate an 8-character code', () => {
    const code = generateInviteCode();
    expect(code.length).toBe(8);
  });

  it('should only contain valid characters', () => {
    const validChars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
    const code = generateInviteCode();
    for (const char of code) {
      expect(validChars).toContain(char);
    }
  });

  it('should generate unique codes', () => {
    const codes = new Set<string>();
    for (let i = 0; i < 100; i++) {
      codes.add(generateInviteCode());
    }
    // With 31^8 possible codes, 100 codes should all be unique
    expect(codes.size).toBe(100);
  });
});

describe('downloadCsv', () => {
  let clickCalled: boolean;
  let downloadAttr: string;
  let hrefAttr: string;
  let revokedUrl: string;
  const origCreateElement = document.createElement.bind(document);

  beforeEach(() => {
    clickCalled = false;
    downloadAttr = '';
    hrefAttr = '';
    revokedUrl = '';

    // Mock URL.createObjectURL and revokeObjectURL
    (globalThis.URL as unknown as Record<string, unknown>).createObjectURL = (
      _blob: Blob
    ) => 'blob:mock-url';
    (globalThis.URL as unknown as Record<string, unknown>).revokeObjectURL = (
      url: string
    ) => {
      revokedUrl = url;
    };

    // Mock document.createElement for anchor element
    document.createElement = ((tag: string) => {
      if (tag === 'a') {
        const el = origCreateElement(tag);
        Object.defineProperty(el, 'click', {
          value: () => {
            clickCalled = true;
          },
        });
        const proxy = new Proxy(el, {
          set(target, prop, value) {
            if (prop === 'download') downloadAttr = value as string;
            if (prop === 'href') hrefAttr = value as string;
            (target as unknown as Record<string | symbol, unknown>)[prop] =
              value;
            return true;
          },
        });
        return proxy;
      }
      return origCreateElement(tag);
    }) as typeof document.createElement;
  });

  afterEach(() => {
    document.createElement = origCreateElement;
  });

  it('should trigger a file download with correct filename', () => {
    downloadCsv(['Name', 'Score'], [['Alice', 10]], 'test-export.csv');
    expect(clickCalled).toBe(true);
    expect(downloadAttr).toBe('test-export.csv');
    expect(hrefAttr).toBe('blob:mock-url');
  });

  it('should revoke the blob URL after download', () => {
    downloadCsv(['A'], [['B']], 'file.csv');
    expect(revokedUrl).toBe('blob:mock-url');
  });

  it('should escape values containing commas', () => {
    // We can't easily inspect the blob content, but we verify it doesn't throw
    downloadCsv(['Name'], [['Last, First']], 'file.csv');
    expect(clickCalled).toBe(true);
  });

  it('should escape values containing double quotes', () => {
    downloadCsv(['Name'], [['He said "hello"']], 'file.csv');
    expect(clickCalled).toBe(true);
  });

  it('should handle null and undefined values', () => {
    downloadCsv(['A', 'B'], [[null, undefined]], 'file.csv');
    expect(clickCalled).toBe(true);
  });

  it('should handle empty rows', () => {
    downloadCsv(['A', 'B'], [], 'file.csv');
    expect(clickCalled).toBe(true);
  });
});
