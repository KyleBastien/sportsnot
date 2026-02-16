/**
 * Stub module for @sportsnot/mock-data when VITE_MOCK_MODE is off.
 * Provides empty data structures so mock hooks don't crash during
 * tree-shaking when imports can't be fully eliminated.
 */

export const teams: readonly never[] = [];
export const players: Record<string, never[]> = {};
export const bracket: readonly never[] = [];
export const gamesR1: readonly never[] = [];
export const gamesR2: readonly never[] = [];
export const gamesCf: readonly never[] = [];
export const gamesScf: readonly never[] = [];
export const playerGameLogs: Record<string, never[]> = {};
export const regularSeasonStats: Record<string, never> = {};

export type RegularSeasonPlayerStats = Record<string, never>;
