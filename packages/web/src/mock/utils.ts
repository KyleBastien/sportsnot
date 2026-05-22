import { SCORING } from '@sportsnot/types';
import type { NHLPlayerStats, NHLGame, RosterSlot } from '@sportsnot/types';
import {
  playerGameLogs,
  players,
  teams,
  gamesR1,
  gamesR2,
  gamesCf,
  gamesScf,
} from '@sportsnot/mock-data';
import { getRoundDateBounds, type MockState } from './MockDataProvider';
import { getEliminatedAbbreviations } from './hooks/useMockNhlApi';

export function isMockMode(): boolean {
  return import.meta.env.VITE_MOCK_MODE === 'true';
}

// ── Game lookup for goalie win/shutout determination ───────────────────
const ALL_GAMES: NHLGame[] = [
  ...(gamesR1 as unknown as NHLGame[]),
  ...(gamesR2 as unknown as NHLGame[]),
  ...(gamesCf as unknown as NHLGame[]),
  ...(gamesScf as unknown as NHLGame[]),
];

// ── Elimination helpers (player/team → abbreviation lookup) ────────────
let _playerTeamAbbrMap: Map<number, string> | null = null;
let _teamIdAbbrMap: Map<number, string> | null = null;

/** Map a playerId to the player's team abbreviation. */
export function getPlayerTeamAbbr(playerId: number): string | undefined {
  if (!_playerTeamAbbrMap) {
    _playerTeamAbbrMap = new Map<number, string>();
    for (const [abbr, roster] of Object.entries(
      players as unknown as Record<string, { id: number }[]>
    )) {
      for (const p of roster) {
        _playerTeamAbbrMap.set(p.id, abbr);
      }
    }
  }
  return _playerTeamAbbrMap.get(playerId);
}

/** Map a teamId to the team abbreviation. */
export function getTeamAbbr(teamId: number): string | undefined {
  if (!_teamIdAbbrMap) {
    _teamIdAbbrMap = new Map<number, string>();
    for (const t of teams as unknown as {
      id: number;
      abbreviation: string;
    }[]) {
      _teamIdAbbrMap.set(t.id, t.abbreviation);
    }
  }
  return _teamIdAbbrMap.get(teamId);
}

/**
 * Check if a roster slot's player/team belongs to an eliminated team.
 * Pass the set of eliminated team abbreviations (from getEliminatedAbbreviations).
 */
export function isSlotEliminated(
  slot: { playerId?: number; teamId?: number },
  eliminatedAbbrs: Set<string>
): boolean {
  if (slot.playerId) {
    const abbr = getPlayerTeamAbbr(slot.playerId);
    return abbr ? eliminatedAbbrs.has(abbr) : false;
  }
  if (slot.teamId) {
    const abbr = getTeamAbbr(slot.teamId);
    return abbr ? eliminatedAbbrs.has(abbr) : false;
  }
  return false;
}

/**
 * Calculate points for a set of players/goalies within a date range.
 */
export function calculateRoundMemberPoints(
  playerIds: number[],
  goalieTeamIds: number[],
  fromDate: string,
  throughDate: string
): { playerPts: number; goaliePts: number } {
  let playerPts = 0;
  let goaliePts = 0;

  const logs = playerGameLogs as unknown as Record<number, NHLPlayerStats[]>;

  for (const playerId of playerIds) {
    const entries = logs[playerId] ?? [];
    for (const entry of entries) {
      if (entry.gameDate < fromDate || entry.gameDate > throughDate) continue;
      playerPts += entry.goals * SCORING.goal + entry.assists * SCORING.assist;
    }
  }

  for (const teamId of goalieTeamIds) {
    for (const game of ALL_GAMES) {
      if (game.gameDate < fromDate || game.gameDate > throughDate) continue;

      const isHome = game.homeTeam.id === teamId;
      const isAway = game.awayTeam.id === teamId;
      if (!isHome && !isAway) continue;

      const teamScore = isHome
        ? (game.homeTeam.score ?? 0)
        : (game.awayTeam.score ?? 0);
      const oppScore = isHome
        ? (game.awayTeam.score ?? 0)
        : (game.homeTeam.score ?? 0);

      if (teamScore > oppScore) {
        goaliePts += oppScore === 0 ? SCORING.shutout : SCORING.win;
      }
    }
  }

  return { playerPts, goaliePts };
}

/**
 * Extract active player IDs and goalie team IDs from roster slots.
 */
function extractRosterIds(roster: RosterSlot[]): {
  playerIds: number[];
  goalieTeamIds: number[];
} {
  const playerIds = roster
    .filter((s) => s.isActive && s.playerId)
    .map((s) => s.playerId!);
  const goalieTeamIds = roster
    .filter((s) => s.isActive && s.teamId && !s.playerId)
    .map((s) => s.teamId!);
  return { playerIds, goalieTeamIds };
}

export interface MemberPointsResult {
  totalPoints: number;
  playerPoints: number;
  goaliePoints: number;
  roundPoints: Record<number, number>;
}

/**
 * Calculate cumulative points for a league member across all rounds
 * up to the current simulation state.
 */
export function calculateMemberPoints(
  state: Pick<
    MockState,
    'currentRound' | 'simulationDate' | 'rosters' | 'rosterHistory'
  >,
  memberId: string,
  throughRound = state.currentRound
): MemberPointsResult {
  let totalPlayerPts = 0;
  let totalGoaliePts = 0;
  const roundPts: Record<number, number> = {};
  const maxRound = Math.min(state.currentRound, throughRound);

  for (let r = 1; r <= maxRound; r++) {
    const bounds = getRoundDateBounds(r);
    if (!bounds) continue;

    const currentSlots = state.rosters[memberId] ?? [];
    const rosterMatchesRound =
      currentSlots.length > 0 ? currentSlots[0].round === r : true;
    const roster =
      r === state.currentRound && rosterMatchesRound
        ? currentSlots
        : (state.rosterHistory[memberId]?.[r] ?? []);

    // Round 4: exclude eliminated players (their Round 3 points still count)
    const filteredRoster =
      r === 4
        ? roster.filter(
            (s) => !isSlotEliminated(s, getEliminatedAbbreviations(4))
          )
        : roster;

    const { playerIds, goalieTeamIds } = extractRosterIds(filteredRoster);

    const throughDate =
      state.simulationDate < bounds.lastDate
        ? state.simulationDate
        : bounds.lastDate;

    if (state.simulationDate < bounds.firstDate) continue;

    const pts = calculateRoundMemberPoints(
      playerIds,
      goalieTeamIds,
      bounds.firstDate,
      throughDate
    );

    totalPlayerPts += pts.playerPts;
    totalGoaliePts += pts.goaliePts;
    const roundTotal = pts.playerPts + pts.goaliePts;
    if (roundTotal > 0) {
      roundPts[r] = roundTotal;
    }
  }

  return {
    totalPoints: totalPlayerPts + totalGoaliePts,
    playerPoints: totalPlayerPts,
    goaliePoints: totalGoaliePts,
    roundPoints: roundPts,
  };
}

/**
 * Sort members for re-draft order: fewest cumulative points picks first.
 * Ties broken by team_name alphabetically (A first).
 */
export function sortMembersForReDraft<
  T extends { total_points?: number | null; team_name: string },
>(members: T[]): T[] {
  return [...members].sort((a, b) => {
    const ptsDiff = (a.total_points ?? 0) - (b.total_points ?? 0);
    if (ptsDiff !== 0) return ptsDiff;
    return a.team_name.localeCompare(b.team_name);
  });
}
