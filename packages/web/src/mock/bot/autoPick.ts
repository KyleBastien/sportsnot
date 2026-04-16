import type { NHLPlayer } from '@sportsnot/types';
import { getRosterComposition } from '@sportsnot/types';
import { players } from '@sportsnot/mock-data';
import type { MockDraftState, MockState } from '../MockDataProvider';

// ── Roster slot targets (dynamic based on IR setting) ──────────────────
function getSlotTargets(allowIrSlots: boolean): Record<string, number> {
  const comp = getRosterComposition(allowIrSlots);
  return {
    F: comp.forwards,
    D: comp.defensemen,
    G: comp.goalies,
    IR_F: comp.irForwards,
    IR_D: comp.irDefensemen,
  };
}

function getTotalRosterSize(allowIrSlots: boolean): number {
  const comp = getRosterComposition(allowIrSlots);
  return (
    comp.forwards +
    comp.defensemen +
    comp.goalies +
    comp.irForwards +
    comp.irDefensemen
  );
}

// ── Flat player lookup ─────────────────────────────────────────────────
const ALL_PLAYERS: NHLPlayer[] = Object.values(
  players
).flat() as unknown as NHLPlayer[];

/** Returns position type string for a player */
function positionType(player: NHLPlayer): string {
  return player.primaryPosition.type;
}

/** Count how many of each slot type a member has already drafted */
function countSlots(
  draftState: MockDraftState,
  memberUserId: string
): Record<string, number> {
  const counts: Record<string, number> = {
    F: 0,
    D: 0,
    G: 0,
    IR_F: 0,
    IR_D: 0,
  };
  for (const pick of draftState.picks) {
    const pickIndex = pick.pickNumber - 1;
    const pickerUserId = draftState.draft.draftOrder[pickIndex];
    if (pickerUserId !== memberUserId) continue;
    counts[pick.position] = (counts[pick.position] ?? 0) + 1;
  }
  return counts;
}

/** Determine the slot with greatest remaining need, returning slot code and player type */
function greatestNeed(
  counts: Record<string, number>,
  allowIrSlots: boolean
): {
  slot: string;
  playerType: string;
} {
  const slotTargets = getSlotTargets(allowIrSlots);
  // Fill regular slots first based on greatest remaining need
  const regularSlots: [string, number, string][] = [
    ['F', slotTargets.F, 'Forward'],
    ['D', slotTargets.D, 'Defenseman'],
    ['G', slotTargets.G, 'Goalie'],
  ];

  let maxNeed = 0;
  let needSlot = 'F';
  let needPlayerType = 'Forward';

  for (const [slot, target, playerType] of regularSlots) {
    const remaining = target - (counts[slot] ?? 0);
    if (remaining > maxNeed) {
      maxNeed = remaining;
      needSlot = slot;
      needPlayerType = playerType;
    }
  }

  // If all regular slots are filled, fill IR slots (only when IR is enabled)
  if (maxNeed <= 0 && allowIrSlots) {
    if ((counts['IR_F'] ?? 0) < slotTargets.IR_F)
      return { slot: 'IR_F', playerType: 'Forward' };
    if ((counts['IR_D'] ?? 0) < slotTargets.IR_D)
      return { slot: 'IR_D', playerType: 'Defenseman' };
  }

  return { slot: needSlot, playerType: needPlayerType };
}

/**
 * Select the best available player for a bot.
 * Strategy: pick best available player for greatest positional need.
 * Tiebreaker: alphabetical by fullName.
 */
export function selectBotPick(
  draftState: MockDraftState,
  botUserId: string,
  allowIrSlots = true
): { playerId: number; position: string; nhlTeamId?: number } | null {
  const counts = countSlots(draftState, botUserId);
  const { slot, playerType } = greatestNeed(counts, allowIrSlots);
  const available = new Set(draftState.availablePlayerIds);

  // Filter to players matching the needed player type
  let candidates = ALL_PLAYERS.filter(
    (p) => available.has(p.id) && positionType(p) === playerType
  );

  // Fallback: if no candidates for the needed position, pick any available player
  if (candidates.length === 0) {
    candidates = ALL_PLAYERS.filter((p) => available.has(p.id));
  }

  if (candidates.length === 0) return null;

  // Sort alphabetically by name as a stable tiebreaker
  candidates.sort((a, b) => a.fullName.localeCompare(b.fullName));

  const picked = candidates[0];
  const isGoalie = positionType(picked) === 'Goalie';

  return {
    playerId: picked.id,
    position: slot,
    nhlTeamId: isGoalie ? picked.currentTeam?.id : undefined,
  };
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
export function getBotMemberId(
  state: MockState,
  botUserId: string
): string | null {
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
export function botPickCount(
  draftState: MockDraftState,
  botUserId: string
): number {
  return draftState.picks.filter((pick) => {
    const pickIndex = pick.pickNumber - 1;
    return draftState.draft.draftOrder[pickIndex] === botUserId;
  }).length;
}

/** Maximum draft rounds (matches useMockDraft.ts) */
export function getMaxDraftRounds(allowIrSlots = true): number {
  return getTotalRosterSize(allowIrSlots);
}
