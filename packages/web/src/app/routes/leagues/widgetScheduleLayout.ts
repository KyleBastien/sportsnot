import type {
  WidgetDraftedPlayer,
  WidgetGame,
  WidgetSnapshot,
} from '@sportsnot/widget-api';

export interface WidgetAssetEntry {
  name: string;
  fantasyPoints: number;
  dailyFantasyPoints: number;
}

export interface WidgetTeamAssetLine {
  teamAbbrev: string;
  assets: WidgetAssetEntry[];
}

export interface WidgetFantasyTeamGroup {
  name: string;
  totalFantasyPoints: number;
  teamLines: WidgetTeamAssetLine[];
}

export interface WidgetGameCard {
  game: WidgetGame;
  fantasyTeams: WidgetFantasyTeamGroup[];
}

export function buildWidgetGameCards(
  snapshot: WidgetSnapshot
): WidgetGameCard[] {
  return snapshot.games
    .map((game) => ({
      game,
      fantasyTeams: groupFantasyTeams(
        snapshot.players.filter((player) => player.gameId === game.id)
      ),
    }))
    .sort((lhs, rhs) => chronologicalSort(lhs.game, rhs.game));
}

export function formatWidgetGameHeader(game: WidgetGame): string {
  const matchup = `${game.awayTeamAbbrev} @ ${game.homeTeamAbbrev}`;

  switch (game.state) {
    case 'LIVE':
    case 'CRIT': {
      const detail = liveDetail(game);
      return `${matchup} - ${game.awayScore}-${game.homeScore} ${detail}`.trim();
    }
    case 'FINAL':
    case 'OFF':
      return `${matchup} - ${game.awayScore}-${game.homeScore} F`;
    default:
      return `${matchup} - ${startTimeText(game.startsAt)}`;
  }
}

export function formatWidgetTeamLines(team: WidgetFantasyTeamGroup): string[] {
  return team.teamLines.map((line) => {
    if (line.assets.length === 0) {
      return `- ${line.teamAbbrev}`;
    }

    return `- ${line.teamAbbrev}: ${line.assets
      .map(formatWidgetAssetText)
      .join(', ')}`;
  });
}

export function formatWidgetAssetText(asset: WidgetAssetEntry): string {
  return `${asset.name} ${formatPoints(asset.fantasyPoints)} +${formatPoints(
    asset.dailyFantasyPoints
  )}`;
}

function groupFantasyTeams(
  players: WidgetDraftedPlayer[]
): WidgetFantasyTeamGroup[] {
  return Object.entries(groupBy(players, (player) => player.ownedByTeamName))
    .map(([teamName, members]) => ({
      name: teamName,
      totalFantasyPoints: members.reduce(
        (total, player) => total + player.fantasyPoints,
        0
      ),
      teamLines: Object.entries(
        groupBy(members, (player) => player.teamAbbrev.trim() || 'NHL')
      )
        .map(([teamAbbrev, assets]) => ({
          teamAbbrev,
          assets: [...assets].sort(draftedAssetSort).map((player) => ({
            name: player.name,
            fantasyPoints: player.fantasyPoints,
            dailyFantasyPoints: player.dailyFantasyPoints,
          })),
        }))
        .sort((lhs, rhs) =>
          lhs.teamAbbrev.localeCompare(rhs.teamAbbrev, undefined, {
            sensitivity: 'base',
          })
        ),
    }))
    .sort((lhs, rhs) => {
      if (lhs.totalFantasyPoints !== rhs.totalFantasyPoints) {
        return rhs.totalFantasyPoints - lhs.totalFantasyPoints;
      }

      return lhs.name.localeCompare(rhs.name, undefined, {
        sensitivity: 'base',
      });
    });
}

function groupBy<T>(
  items: T[],
  getKey: (item: T) => string
): Record<string, T[]> {
  return items.reduce<Record<string, T[]>>((groups, item) => {
    const key = getKey(item);
    groups[key] = groups[key] ?? [];
    groups[key].push(item);
    return groups;
  }, {});
}

function draftedAssetSort(
  lhs: WidgetDraftedPlayer,
  rhs: WidgetDraftedPlayer
): number {
  if (lhs.fantasyPoints !== rhs.fantasyPoints) {
    return rhs.fantasyPoints - lhs.fantasyPoints;
  }

  return lhs.name.localeCompare(rhs.name, undefined, {
    sensitivity: 'base',
  });
}

function chronologicalSort(lhs: WidgetGame, rhs: WidgetGame): number {
  const left = gameTime(lhs.startsAt);
  const right = gameTime(rhs.startsAt);

  if (left !== right) {
    return left - right;
  }

  return lhs.id - rhs.id;
}

function gameTime(value: string): number {
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? Number.MAX_SAFE_INTEGER : parsed;
}

function startTimeText(value: string): string {
  const parsed = Date.parse(value);
  if (Number.isNaN(parsed)) {
    return value;
  }

  return new Intl.DateTimeFormat('en-US', {
    hour: 'numeric',
    minute: '2-digit',
  }).format(new Date(parsed));
}

function liveDetail(game: WidgetGame): string {
  const period = game.period != null ? `P${game.period}` : 'LIVE';
  if (game.timeRemaining) {
    return `${period} ${game.timeRemaining}`;
  }

  return period;
}

function formatPoints(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}
