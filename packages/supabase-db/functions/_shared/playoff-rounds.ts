export interface PlayoffRoundWindow {
  startDate: string;
  endDate?: string;
}

const PLAYOFF_ROUND_WINDOWS: Record<
  string,
  Partial<Record<number, PlayoffRoundWindow>>
> = {
  '20252026': {
    1: {
      startDate: '2026-04-18',
      endDate: '2026-05-03',
    },
    2: {
      startDate: '2026-05-02',
    },
    3: {
      startDate: '2026-05-20',
    },
    4: {
      startDate: '2026-05-30',
    },
  },
};

export interface LeagueRoundRow {
  current_round: number | null;
}

export interface PlayoffGameLike {
  gameType: number;
  seriesStatus?: {
    round?: number;
  } | null;
}

export function derivePlayoffRoundsToSync(leagues: LeagueRoundRow[]): number[] {
  return [...new Set(leagues.map((league) => league.current_round))]
    .filter((round): round is number => round != null && round >= 1)
    .sort((a, b) => a - b);
}

export function getPlayoffRoundWindow(
  season: string,
  playoffRound: number,
  overrideStartDate?: string,
  overrideEndDate?: string
): PlayoffRoundWindow | null {
  const configured = PLAYOFF_ROUND_WINDOWS[season]?.[playoffRound];
  const startDate = overrideStartDate ?? configured?.startDate;
  const endDate = overrideEndDate ?? configured?.endDate;

  if (!startDate) {
    return null;
  }

  return endDate ? { startDate, endDate } : { startDate };
}

export function getEffectiveRoundEndDate(
  window: PlayoffRoundWindow,
  today = new Date().toISOString().split('T')[0]
): string {
  if (!window.endDate || window.endDate > today) {
    return today;
  }
  return window.endDate;
}

export function incrementIsoDate(date: string): string {
  const next = new Date(`${date}T12:00:00Z`);
  next.setUTCDate(next.getUTCDate() + 1);
  return next.toISOString().split('T')[0];
}

export function isPlayoffGameInRound(
  game: PlayoffGameLike,
  playoffRound: number
): boolean {
  return game.gameType === 3 && game.seriesStatus?.round === playoffRound;
}
