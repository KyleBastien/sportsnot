import { describe, expect, it } from '@rstest/core';
import { getInitialState } from '../MockDataProvider';
import { buildMockLeagueWidgetSnapshot } from './useMockLeagueWidgetSnapshot';

describe('buildMockLeagueWidgetSnapshot', () => {
  it('builds full-slate widget data from mock league rosters', () => {
    const baseState = getInitialState();
    const state = {
      ...baseState,
      currentRound: 3,
      simulationDate: '2025-05-28',
      leagues: [
        {
          id: 'league-1',
          name: 'Mock League',
          commissionerId: 'user-1',
          inviteCode: 'INVITE',
          maxParticipants: 2,
          currentRound: 3,
          status: 'active' as const,
          allowIrSlots: true,
          createdAt: '2025-04-01T00:00:00Z',
          updatedAt: '2025-04-01T00:00:00Z',
          members: [
            {
              id: 'member-1',
              leagueId: 'league-1',
              userId: 'user-1',
              teamName: 'Storm',
              totalPoints: 0,
              joinedAt: '2025-04-01T00:00:00Z',
            },
          ],
          isMock: true,
        },
      ],
      rosters: {
        'member-1': [
          {
            id: 'slot-1',
            leagueMemberId: 'member-1',
            round: 3,
            playerId: 8478427,
            position: 'F' as const,
            isActive: true,
            pointsEarned: 0,
            activatedFromIr: false,
          },
          {
            id: 'slot-2',
            leagueMemberId: 'member-1',
            round: 3,
            teamId: 12,
            position: 'G' as const,
            isActive: true,
            pointsEarned: 0,
            activatedFromIr: false,
          },
        ],
      },
    };

    const snapshot = buildMockLeagueWidgetSnapshot(state, 'league-1');

    expect(snapshot).not.toBeNull();
    expect(snapshot?.date).toBe('2025-05-28');
    expect(snapshot?.games.some((game) => game.id === 2024030315)).toBe(true);
    expect(
      snapshot?.games.find((game) => game.id === 2024030315)
    ).toMatchObject({
      hasDraftedPlayers: true,
      homeTeamAbbrev: 'CAR',
      awayTeamAbbrev: 'FLA',
    });
    expect(snapshot?.players).toHaveLength(2);
    expect(snapshot?.players[0]).toMatchObject({
      name: 'Sebastian Aho',
      teamAbbrev: 'CAR',
      gameId: 2024030315,
      fantasyPoints: 5,
      dailyFantasyPoints: 2,
      ownedByTeamName: 'Storm',
    });
    expect(snapshot?.players[1]).toMatchObject({
      teamId: 12,
      teamAbbrev: 'CAR',
      gameId: 2024030315,
      ownedByTeamName: 'Storm',
    });
  });

  it('returns null when league is missing', () => {
    const snapshot = buildMockLeagueWidgetSnapshot(
      getInitialState(),
      'missing'
    );

    expect(snapshot).toBeNull();
  });
});
