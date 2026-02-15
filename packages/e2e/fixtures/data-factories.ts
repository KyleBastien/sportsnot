import type {
  User,
  League,
  LeagueStatus,
  LeagueMember,
  Draft,
  DraftStatus,
  DraftPick,
  RosterSlot,
  Position,
  PlayerStats,
  TeamStats,
} from '@sportsnot/types';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

let _seq = 0;
function seq(): number {
  return ++_seq;
}

function uuid(): string {
  const s = seq();
  return `00000000-0000-4000-a000-${String(s).padStart(12, '0')}`;
}

function isoNow(): string {
  return new Date().toISOString();
}

// ---------------------------------------------------------------------------
// NHL reference data
// ---------------------------------------------------------------------------

const NHL_FORWARDS = [
  { id: 8478402, name: 'Connor McDavid', team: 'EDM' },
  { id: 8479318, name: 'Auston Matthews', team: 'TOR' },
  { id: 8471675, name: 'Sidney Crosby', team: 'PIT' },
  { id: 8477934, name: 'Leon Draisaitl', team: 'EDM' },
  { id: 8479339, name: 'Mitch Marner', team: 'TOR' },
  { id: 8477492, name: 'Nathan MacKinnon', team: 'COL' },
  { id: 8478483, name: 'Jack Eichel', team: 'VGK' },
  { id: 8480012, name: 'Brady Tkachuk', team: 'OTT' },
  { id: 8478427, name: 'Sebastian Aho', team: 'CAR' },
  { id: 8480064, name: 'Elias Pettersson', team: 'VAN' },
] as const;

const NHL_DEFENSEMEN = [
  { id: 8480069, name: 'Cale Makar', team: 'COL' },
  { id: 8479323, name: 'Victor Hedman', team: 'TBL' },
  { id: 8480145, name: 'Quinn Hughes', team: 'VAN' },
  { id: 8477939, name: 'Adam Fox', team: 'NYR' },
  { id: 8479400, name: 'Miro Heiskanen', team: 'DAL' },
] as const;

const NHL_GOALIES = [
  { id: 8479496, name: 'Andrei Vasilevskiy', team: 'TBL', teamId: 14 },
  { id: 8477424, name: 'Connor Hellebuyck', team: 'WPG', teamId: 52 },
  { id: 8480382, name: 'Igor Shesterkin', team: 'NYR', teamId: 3 },
] as const;

const NHL_TEAMS = [
  { id: 6, name: 'Boston Bruins', abbrev: 'BOS' },
  { id: 14, name: 'Tampa Bay Lightning', abbrev: 'TBL' },
  { id: 10, name: 'Toronto Maple Leafs', abbrev: 'TOR' },
  { id: 22, name: 'Edmonton Oilers', abbrev: 'EDM' },
  { id: 21, name: 'Colorado Avalanche', abbrev: 'COL' },
  { id: 52, name: 'Winnipeg Jets', abbrev: 'WPG' },
  { id: 3, name: 'New York Rangers', abbrev: 'NYR' },
  { id: 12, name: 'Carolina Hurricanes', abbrev: 'CAR' },
  { id: 25, name: 'Dallas Stars', abbrev: 'DAL' },
  { id: 23, name: 'Vancouver Canucks', abbrev: 'VAN' },
] as const;

// ---------------------------------------------------------------------------
// Factory: User
// ---------------------------------------------------------------------------

export function createMockUser(overrides?: Partial<User>): User {
  const s = seq();
  return {
    id: uuid(),
    email: `user${s}@sportsnot.test`,
    displayName: `Test User ${s}`,
    avatarUrl: `https://api.dicebear.com/7.x/identicon/svg?seed=user${s}`,
    createdAt: '2026-01-01T00:00:00.000Z',
    updatedAt: isoNow(),
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Factory: League
// ---------------------------------------------------------------------------

export function createMockLeague(overrides?: Partial<League>): League {
  const s = seq();
  return {
    id: uuid(),
    name: `Playoff League ${s}`,
    commissionerId: uuid(),
    inviteCode: `INV${String(s).padStart(6, '0')}`,
    maxParticipants: 8,
    currentRound: 1,
    status: 'active' as LeagueStatus,
    createdAt: '2026-01-15T00:00:00.000Z',
    updatedAt: isoNow(),
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Factory: LeagueMember
// ---------------------------------------------------------------------------

export function createMockLeagueMember(
  overrides?: Partial<LeagueMember>
): LeagueMember {
  const s = seq();
  return {
    id: uuid(),
    leagueId: uuid(),
    userId: uuid(),
    teamName: `Team Alpha ${s}`,
    totalPoints: Math.floor(Math.random() * 50),
    joinedAt: '2026-01-20T00:00:00.000Z',
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Factory: Draft
// ---------------------------------------------------------------------------

export function createMockDraft(overrides?: Partial<Draft>): Draft {
  return {
    id: uuid(),
    leagueId: uuid(),
    round: 1,
    status: 'active' as DraftStatus,
    currentPick: 1,
    draftOrder: [uuid(), uuid(), uuid(), uuid()],
    startedAt: isoNow(),
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Factory: DraftPick
// ---------------------------------------------------------------------------

export function createMockDraftPick(overrides?: Partial<DraftPick>): DraftPick {
  const s = seq();
  const fwd = NHL_FORWARDS[s % NHL_FORWARDS.length];
  return {
    id: uuid(),
    draftId: uuid(),
    leagueMemberId: uuid(),
    pickNumber: s,
    playerId: fwd.id,
    position: 'F' as Position,
    pickedAt: isoNow(),
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Factory: RosterSlot
// ---------------------------------------------------------------------------

export function createMockRosterSlot(
  overrides?: Partial<RosterSlot>
): RosterSlot {
  const fwd = NHL_FORWARDS[seq() % NHL_FORWARDS.length];
  return {
    id: uuid(),
    leagueMemberId: uuid(),
    round: 1,
    playerId: fwd.id,
    position: 'F' as Position,
    isActive: true,
    pointsEarned: Math.floor(Math.random() * 10),
    activatedFromIr: false,
    ...overrides,
  };
}

/**
 * Creates a full roster: 5F + 3D + 1G active, plus 1 IR_F and 1 IR_D.
 * Each slot has a unique realistic NHL player assigned.
 */
export function createMockRoster(
  leagueMemberId: string,
  overrides?: { round?: number }
): RosterSlot[] {
  const round = overrides?.round ?? 1;
  let _slotIdx = 0;

  function slot(
    position: Position,
    playerId: number | undefined,
    teamId: number | undefined,
    isActive: boolean
  ): RosterSlot {
    _slotIdx++;
    return {
      id: uuid(),
      leagueMemberId,
      round,
      playerId,
      teamId,
      position,
      isActive,
      pointsEarned: Math.floor(Math.random() * 8) + 1,
      activatedFromIr: false,
    };
  }

  return [
    // 5 Forwards
    slot('F', NHL_FORWARDS[0].id, undefined, true),
    slot('F', NHL_FORWARDS[1].id, undefined, true),
    slot('F', NHL_FORWARDS[2].id, undefined, true),
    slot('F', NHL_FORWARDS[3].id, undefined, true),
    slot('F', NHL_FORWARDS[4].id, undefined, true),
    // 3 Defensemen
    slot('D', NHL_DEFENSEMEN[0].id, undefined, true),
    slot('D', NHL_DEFENSEMEN[1].id, undefined, true),
    slot('D', NHL_DEFENSEMEN[2].id, undefined, true),
    // 1 Goalie (uses teamId)
    slot('G', undefined, NHL_GOALIES[0].teamId, true),
    // IR slots
    slot('IR_F', NHL_FORWARDS[5].id, undefined, false),
    slot('IR_D', NHL_DEFENSEMEN[3].id, undefined, false),
  ];
}

// ---------------------------------------------------------------------------
// Factory: PlayerStats
// ---------------------------------------------------------------------------

export function createMockPlayerStats(
  overrides?: Partial<PlayerStats>
): PlayerStats {
  const fwd = NHL_FORWARDS[seq() % NHL_FORWARDS.length];
  return {
    playerId: fwd.id,
    nhlSeason: '20252026',
    playoffRound: 1,
    playerName: fwd.name,
    teamAbbreviation: fwd.team,
    position: 'F',
    goals: Math.floor(Math.random() * 6),
    assists: Math.floor(Math.random() * 8),
    gamesPlayed: Math.floor(Math.random() * 7) + 1,
    isInjured: false,
    lastUpdated: isoNow(),
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Factory: TeamStats
// ---------------------------------------------------------------------------

export function createMockTeamStats(overrides?: Partial<TeamStats>): TeamStats {
  const team = NHL_TEAMS[seq() % NHL_TEAMS.length];
  return {
    teamId: team.id,
    nhlSeason: '20252026',
    playoffRound: 1,
    teamName: team.name,
    teamAbbreviation: team.abbrev,
    wins: Math.floor(Math.random() * 4),
    shutouts: Math.random() > 0.7 ? 1 : 0,
    isEliminated: false,
    lastUpdated: isoNow(),
    ...overrides,
  };
}
