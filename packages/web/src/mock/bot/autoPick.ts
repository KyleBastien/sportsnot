import type { NHLPlayer } from '@sportsnot/types';
import { players } from '@sportsnot/mock-data';
import type { MockDraftState, MockState } from '../MockDataProvider';

// ── Roster composition targets (10 total: 5F + 3D + 2G) ───────────────
const ROSTER_TARGETS: Record<string, number> = { Forward: 5, Defenseman: 3, Goalie: 2 };
const TOTAL_ROSTER_SIZE = 10;

// ── Flat player lookup ─────────────────────────────────────────────────
const ALL_PLAYERS: NHLPlayer[] = Object.values(players).flat() as unknown as NHLPlayer[];
const PLAYER_MAP = new Map<number, NHLPlayer>(ALL_PLAYERS.map((p) => [p.id, p]));

/** Returns position type string for a player */
function positionType(player: NHLPlayer): string {
  return player.primaryPosition.type;
}

/** Count how many of each position type a member has already drafted */
function countPositions(
  draftState: MockDraftState,
  memberUserId: string,
): Record<string, number> {
  const counts: Record<string, number> = { Forward: 0, Defenseman: 0, Goalie: 0 };
  for (const pick of draftState.picks) {
    // Find the userId for this pick's league member from the draft order
    const pickIndex = pick.pickNumber - 1;
    const pickerUserId = draftState.draft.draftOrder[pickIndex];
    if (pickerUserId !== memberUserId) continue;

    const pid = pick.playerId ?? pick.teamId;
    if (pid == null) continue;
    const player = PLAYER_MAP.get(pid);
    if (player) {
      const pType = positionType(player);
      counts[pType] = (counts[pType] ?? 0) + 1;
    }
  }
  return counts;
}

/** Determine the position with greatest remaining need */
function greatestNeed(counts: Record<string, number>): string {
  let maxNeed = -1;
  let needPosition = 'Forward';

  for (const [pos, target] of Object.entries(ROSTER_TARGETS)) {
    const have = counts[pos] ?? 0;
    const remaining = target - have;
    if (remaining > maxNeed) {
      maxNeed = remaining;
      needPosition = pos;
    }
  }
  return needPosition;
}

/**
 * Select the best available player for a bot.
 * Strategy: pick best available player for greatest positional need.
 * Tiebreaker: alphabetical by fullName.
 */
export function selectBotPick(
  draftState: MockDraftState,
  botUserId: string,
): { playerId: number; position: string } | null {
  const counts = countPositions(draftState, botUserId);
  const need = greatestNeed(counts);
  const available = new Set(draftState.availablePlayerIds);

  // Filter to players matching the needed position type
  let candidates = ALL_PLAYERS.filter(
    (p) => available.has(p.id) && positionType(p) === need,
  );

  // Fallback: if no candidates for the needed position, pick any available player
  if (candidates.length === 0) {
    candidates = ALL_PLAYERS.filter((p) => available.has(p.id));
  }

  if (candidates.length === 0) return null;

  // Sort alphabetically by name as a stable tiebreaker
  candidates.sort((a, b) => a.fullName.localeCompare(b.fullName));

  const picked = candidates[0];
  // Map position type to draft position code
  const posCode = picked.primaryPosition.type === 'Goalie' ? 'G'
    : picked.primaryPosition.type === 'Defenseman' ? 'D' : 'F';

  return { playerId: picked.id, position: posCode };
}

/**
 * Check if the current pick belongs to a bot (not the mock user).
 * Returns the bot's userId if it's a bot's turn, null otherwise.
 */
export function getCurrentBotUserId(state: MockState): string | null {
  const ds = state.draftState;
  if (!ds || ds.draft.status !== 'active') return null;

  const pickIndex = ds.draft.currentPick - 1;
  if (pickIndex >= ds.draft.draftOrder.length) return null;

  const currentUserId = ds.draft.draftOrder[pickIndex];
  // Mock user is never a bot
  if (currentUserId === state.mockUser.id) return null;

  return currentUserId;
}

/**
 * Get the league member ID for a given userId in the current draft's league.
 */
export function getBotMemberId(state: MockState, botUserId: string): string | null {
  const ds = state.draftState;
  if (!ds) return null;

  const league = state.leagues.find((l) => l.id === ds.draft.leagueId);
  if (!league) return null;

  const member = league.members.find((m) => m.userId === botUserId);
  return member?.id ?? null;
}

/**
 * Compute the number of total roster slots that have been filled.
 * Used to check if the draft is running out of picks.
 */
export function botPickCount(draftState: MockDraftState, botUserId: string): number {
  return draftState.picks.filter((pick) => {
    const pickIndex = pick.pickNumber - 1;
    return draftState.draft.draftOrder[pickIndex] === botUserId;
  }).length;
}

/** Maximum draft rounds (matches useMockDraft.ts) */
export const MAX_DRAFT_ROUNDS = TOTAL_ROSTER_SIZE;
