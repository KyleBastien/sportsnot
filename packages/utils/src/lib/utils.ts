import { SCORING, type PlayerStats, type TeamStats } from '@sportsnot/types';

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

/**
 * Convert tabular data to a CSV string and trigger a download.
 * @param headers Array of column header strings
 * @param rows Array of arrays, each inner array is a row of cell values
 * @param filename Filename for the downloaded CSV
 */
export function downloadCsv(
  headers: string[],
  rows: (string | number | null | undefined)[][],
  filename: string
): void {
  const escape = (val: string | number | null | undefined): string => {
    const str = val == null ? '' : String(val);
    return str.includes(',') || str.includes('"') || str.includes('\n')
      ? `"${str.replace(/"/g, '""')}"`
      : str;
  };

  const csvContent = [
    headers.map(escape).join(','),
    ...rows.map((row) => row.map(escape).join(',')),
  ].join('\n');

  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
