import { SCORING, type PlayerStats, type TeamStats } from '@sportsnot/types';

// ── Player / Team name lookup utilities ─────────────────────────────────

interface PlayerLookupRow {
  player_id: number;
  player_name?: string | null;
}

interface TeamLookupRow {
  team_id: number;
  team_name?: string | null;
}

/**
 * Build a Map<player_id, player_name> from player stat rows.
 * Works with both mock and live data shapes.
 */
export function buildPlayerNameMap(
  players: PlayerLookupRow[]
): Map<number, string> {
  const map = new Map<number, string>();
  for (const p of players) {
    if (p.player_name) {
      map.set(p.player_id, p.player_name);
    }
  }
  return map;
}

/**
 * Build a Map<team_id, team_name> from team stat rows.
 * Works with both mock and live data shapes.
 */
export function buildTeamNameMap(teams: TeamLookupRow[]): Map<number, string> {
  const map = new Map<number, string>();
  for (const t of teams) {
    if (t.team_name) {
      map.set(t.team_id, t.team_name);
    }
  }
  return map;
}

/**
 * Resolve a draft pick to a display name.
 * Checks player_id first, then team_id, with fallback.
 */
export function resolvePickName(
  playerId: number | null | undefined,
  teamId: number | null | undefined,
  playerMap: Map<number, string>,
  teamMap: Map<number, string>,
  fallback = 'Unknown Player'
): string {
  if (playerId != null) {
    return playerMap.get(playerId) ?? fallback;
  }
  if (teamId != null) {
    return teamMap.get(teamId) ?? 'Unknown Team';
  }
  return fallback;
}

/**
 * Calculate points for a player based on their stats
 */
export function calculatePlayerPoints(stats: PlayerStats): number {
  return stats.goals * SCORING.goal + stats.assists * SCORING.assist;
}

/**
 * Calculate points for a goalie/team based on their stats
 * Shutouts replace win points (4 points instead of 2)
 */
export function calculateGoaliePoints(stats: TeamStats): number {
  const regularWins = stats.wins - stats.shutouts;
  return regularWins * SCORING.win + stats.shutouts * SCORING.shutout;
}

/**
 * Determine goalie points for a single game based on scores.
 * Returns SCORING.shutout if team won and opponent scored 0,
 * SCORING.win if team won, or 0 otherwise.
 * Shutout replaces win points (not additive).
 */
export function calculateGoalieGamePoints(
  teamScore: number,
  opponentScore: number
): number {
  if (teamScore <= opponentScore) return 0;
  return opponentScore === 0 ? SCORING.shutout : SCORING.win;
}

/**
 * Generate snake draft order for a given number of participants
 * @param participantIds Array of participant IDs in initial order
 * @param totalPicks Total number of picks per participant
 * @returns Array of participant IDs in pick order
 */
export function generateSnakeDraftOrder(
  participantIds: string[],
  totalPicks: number
): string[] {
  const order: string[] = [];

  for (let round = 0; round < totalPicks; round++) {
    const isEvenRound = round % 2 === 0;
    const roundOrder = isEvenRound
      ? [...participantIds]
      : [...participantIds].reverse();
    order.push(...roundOrder);
  }

  return order;
}

/**
 * Generate re-draft order based on standings (worst to best, snake pattern)
 * @param standings Array of { memberId, points } sorted by points ascending (worst first)
 * @param totalPicks Total number of picks per participant
 */
export function generateReDraftOrder(
  standings: Array<{ memberId: string; points: number }>,
  totalPicks: number
): string[] {
  // Sort by points ascending (worst first)
  const sorted = [...standings].sort((a, b) => a.points - b.points);
  const participantIds = sorted.map((s) => s.memberId);

  return generateSnakeDraftOrder(participantIds, totalPicks);
}

/**
 * Shuffle array using Fisher-Yates algorithm
 */
export function shuffleArray<T>(array: T[]): T[] {
  const shuffled = [...array];
  for (let i = shuffled.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
  }
  return shuffled;
}

/**
 * Generate random invite code
 */
export function generateInviteCode(): string {
  const characters = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
  let result = '';
  for (let i = 0; i < 8; i++) {
    result += characters.charAt(Math.floor(Math.random() * characters.length));
  }
  return result;
}
