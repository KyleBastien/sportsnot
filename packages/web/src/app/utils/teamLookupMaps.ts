interface PlayerTeamAbbreviationRow {
  player_id: number;
  team_abbreviation?: string | null;
}

interface TeamAbbreviationRow {
  team_id: number;
  team_abbreviation?: string | null;
}

export function buildPlayerTeamAbbreviationMap(
  ...playerSources: ReadonlyArray<ReadonlyArray<PlayerTeamAbbreviationRow>>
): Map<number, string> {
  const map = new Map<number, string>();

  for (const players of playerSources) {
    addPlayerTeamAbbreviations(map, players);
  }

  return map;
}

export function buildTeamAbbreviationMap(
  ...teamSources: ReadonlyArray<ReadonlyArray<TeamAbbreviationRow>>
): Map<number, string> {
  const map = new Map<number, string>();

  for (const teams of teamSources) {
    addTeamAbbreviations(map, teams);
  }

  return map;
}

function addPlayerTeamAbbreviations(
  map: Map<number, string>,
  players: ReadonlyArray<PlayerTeamAbbreviationRow>
) {
  for (const player of players) {
    if (!player.team_abbreviation) {
      continue;
    }

    map.set(player.player_id, player.team_abbreviation);
  }
}

function addTeamAbbreviations(
  map: Map<number, string>,
  teams: ReadonlyArray<TeamAbbreviationRow>
) {
  for (const team of teams) {
    if (!team.team_abbreviation) {
      continue;
    }

    map.set(team.team_id, team.team_abbreviation);
  }
}
