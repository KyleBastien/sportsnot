import { describe, it, expect } from '@rstest/core';
import {
  mockReducer,
  getInitialState,
  type MockState,
  type MockDraftState,
} from './MockDataProvider';

function makeLeague(
  overrides: Partial<MockState['leagues'][number]> = {}
): MockState['leagues'][number] {
  return {
    id: 'league-1',
    name: 'Test League',
    commissionerId: 'user-1',
    inviteCode: 'ABC123',
    maxParticipants: 8,
    currentRound: 1,
    status: 'active',
    createdAt: '2025-01-01',
    updatedAt: '2025-01-01',
    members: [],
    isMock: true,
    ...overrides,
  };
}

function makeState(overrides: Partial<MockState> = {}): MockState {
  return {
    ...getInitialState(),
    ...overrides,
  };
}

function makeDraftState(round: number): MockDraftState {
  return {
    draft: {
      id: 'draft-1',
      leagueId: 'league-1',
      round,
      status: 'active',
      currentPick: 1,
      draftOrder: ['user-1', 'user-2'],
      startedAt: '2025-01-01',
      completedAt: null,
      totalPicks: 22,
    },
    picks: [],
    availablePlayerIds: [1, 2, 3],
  };
}

// ─── ADVANCE_ROUND ──────────────────────────────────────────────────────

describe('ADVANCE_ROUND', () => {
  it('increments currentRound when roundComplete is true', () => {
    const state = makeState({ currentRound: 1, roundComplete: true });
    const next = mockReducer(state, { type: 'ADVANCE_ROUND' });
    expect(next.currentRound).toBe(2);
  });

  it('does not advance when roundComplete is false', () => {
    const state = makeState({ currentRound: 1, roundComplete: false });
    const next = mockReducer(state, { type: 'ADVANCE_ROUND' });
    expect(next.currentRound).toBe(1);
  });

  it('does not advance when seasonComplete is true', () => {
    const state = makeState({
      currentRound: 4,
      roundComplete: true,
      seasonComplete: true,
    });
    const next = mockReducer(state, { type: 'ADVANCE_ROUND' });
    expect(next.currentRound).toBe(4);
  });

  it('does not advance beyond round 4', () => {
    const state = makeState({ currentRound: 4, roundComplete: true });
    const next = mockReducer(state, { type: 'ADVANCE_ROUND' });
    expect(next.currentRound).toBe(4);
  });

  it('resets roundComplete to false', () => {
    const state = makeState({ currentRound: 1, roundComplete: true });
    const next = mockReducer(state, { type: 'ADVANCE_ROUND' });
    expect(next.roundComplete).toBe(false);
  });

  it('does NOT change any league status', () => {
    const state = makeState({
      currentRound: 1,
      roundComplete: true,
      leagues: [
        makeLeague({ id: 'lg-1', status: 'active' }),
        makeLeague({ id: 'lg-2', status: 'drafting' }),
      ],
    });
    const next = mockReducer(state, { type: 'ADVANCE_ROUND' });
    expect(next.leagues[0].status).toBe('active');
    expect(next.leagues[1].status).toBe('drafting');
  });

  it('does NOT trigger any draft flow', () => {
    const state = makeState({
      currentRound: 1,
      roundComplete: true,
      draftState: null,
    });
    const next = mockReducer(state, { type: 'ADVANCE_ROUND' });
    expect(next.draftState).toBeNull();
  });

  it('archives current rosters to rosterHistory', () => {
    const slots = [{ playerId: 1, position: 'F' as const, isFromIR: false }];
    const state = makeState({
      currentRound: 1,
      roundComplete: true,
      rosters: { 'member-1': slots },
      rosterHistory: {},
    });
    const next = mockReducer(state, { type: 'ADVANCE_ROUND' });
    expect(next.rosterHistory['member-1']?.[1]).toEqual(slots);
  });

  it('clears rosters after advancing rounds 1→2 and 2→3', () => {
    const state = makeState({
      currentRound: 1,
      roundComplete: true,
      rosters: {
        'member-1': [{ playerId: 1, position: 'F' as const, isFromIR: false }],
      },
    });
    const next = mockReducer(state, { type: 'ADVANCE_ROUND' });
    expect(next.rosters).toEqual({});
  });

  it('advances simulationDate to day before next round starts', () => {
    const state = makeState({ currentRound: 1, roundComplete: true });
    const next = mockReducer(state, { type: 'ADVANCE_ROUND' });
    // simulationDate should change (exact value depends on getRoundDateBounds)
    expect(next.simulationDate).not.toBe(state.simulationDate);
  });

  it('does not overwrite rosterHistory if already archived by START_RE_DRAFT', () => {
    const r1Slots = [
      {
        id: 'slot-1',
        leagueMemberId: 'member-1',
        round: 1,
        playerId: 100,
        position: 'F' as const,
        isActive: true,
        pointsEarned: 5,
        activatedFromIr: false,
      },
    ];
    const r2Slots = [
      {
        id: 'slot-2',
        leagueMemberId: 'member-1',
        round: 2,
        playerId: 200,
        position: 'D' as const,
        isActive: true,
        pointsEarned: 0,
        activatedFromIr: false,
      },
    ];
    const state = makeState({
      currentRound: 1,
      roundComplete: true,
      rosters: { 'member-1': r2Slots },
      rosterHistory: { 'member-1': { 1: r1Slots } },
    });
    const next = mockReducer(state, { type: 'ADVANCE_ROUND' });
    // Should preserve the original R1 archive, not overwrite with R2 data
    expect(next.rosterHistory['member-1']?.[1]).toEqual(r1Slots);
  });

  it('preserves rosters if they belong to the next round (from re-draft)', () => {
    const r2Slots = [
      {
        id: 'slot-1',
        leagueMemberId: 'member-1',
        round: 2,
        playerId: 200,
        position: 'F' as const,
        isActive: true,
        pointsEarned: 0,
        activatedFromIr: false,
      },
    ];
    const r1Slots = [
      {
        id: 'slot-2',
        leagueMemberId: 'member-1',
        round: 1,
        playerId: 100,
        position: 'F' as const,
        isActive: true,
        pointsEarned: 5,
        activatedFromIr: false,
      },
    ];
    const state = makeState({
      currentRound: 1,
      roundComplete: true,
      rosters: { 'member-1': r2Slots },
      rosterHistory: { 'member-1': { 1: r1Slots } },
    });
    const next = mockReducer(state, { type: 'ADVANCE_ROUND' });
    // Round 2 rosters should be preserved, not cleared
    expect(next.rosters['member-1']).toEqual(r2Slots);
  });
});

// ─── START_NEXT_DRAFT ───────────────────────────────────────────────────

describe('START_NEXT_DRAFT', () => {
  it('sets league status to drafting', () => {
    const state = makeState({
      leagues: [makeLeague({ id: 'lg-1', status: 'active' })],
    });
    const next = mockReducer(state, {
      type: 'START_NEXT_DRAFT',
      payload: { leagueId: 'lg-1' },
    });
    expect(next.leagues[0].status).toBe('drafting');
  });

  it('does not change currentRound', () => {
    const state = makeState({
      currentRound: 1,
      leagues: [makeLeague({ id: 'lg-1', status: 'active' })],
    });
    const next = mockReducer(state, {
      type: 'START_NEXT_DRAFT',
      payload: { leagueId: 'lg-1' },
    });
    expect(next.currentRound).toBe(1);
  });

  it('does not change simulationDate', () => {
    const state = makeState({
      simulationDate: '2025-04-20',
      leagues: [makeLeague({ id: 'lg-1', status: 'active' })],
    });
    const next = mockReducer(state, {
      type: 'START_NEXT_DRAFT',
      payload: { leagueId: 'lg-1' },
    });
    expect(next.simulationDate).toBe('2025-04-20');
  });

  it('only affects the targeted league', () => {
    const state = makeState({
      leagues: [
        makeLeague({ id: 'lg-1', status: 'active' }),
        makeLeague({ id: 'lg-2', status: 'active' }),
      ],
    });
    const next = mockReducer(state, {
      type: 'START_NEXT_DRAFT',
      payload: { leagueId: 'lg-1' },
    });
    expect(next.leagues[0].status).toBe('drafting');
    expect(next.leagues[1].status).toBe('active');
  });

  it('does not modify rosters or rosterHistory', () => {
    const state = makeState({
      leagues: [makeLeague({ id: 'lg-1', status: 'active' })],
      rosters: { 'member-1': [] },
      rosterHistory: { 'member-1': { 1: [] } },
    });
    const next = mockReducer(state, {
      type: 'START_NEXT_DRAFT',
      payload: { leagueId: 'lg-1' },
    });
    expect(next.rosters).toEqual({ 'member-1': [] });
    expect(next.rosterHistory).toEqual({ 'member-1': { 1: [] } });
  });
});

// ─── START_RE_DRAFT (fixed: no global currentRound change) ─────────────

describe('START_RE_DRAFT', () => {
  it('sets league status to drafting', () => {
    const state = makeState({
      leagues: [makeLeague({ id: 'league-1', status: 'active' })],
    });
    const next = mockReducer(state, {
      type: 'START_RE_DRAFT',
      payload: { leagueId: 'league-1', draftState: makeDraftState(2) },
    });
    expect(next.leagues[0].status).toBe('drafting');
  });

  it('updates league currentRound to draft round', () => {
    const state = makeState({
      leagues: [makeLeague({ id: 'league-1', currentRound: 1 })],
    });
    const next = mockReducer(state, {
      type: 'START_RE_DRAFT',
      payload: { leagueId: 'league-1', draftState: makeDraftState(2) },
    });
    expect(next.leagues[0].currentRound).toBe(2);
  });

  it('does NOT change global currentRound', () => {
    const state = makeState({
      currentRound: 1,
      leagues: [makeLeague({ id: 'league-1' })],
    });
    const next = mockReducer(state, {
      type: 'START_RE_DRAFT',
      payload: { leagueId: 'league-1', draftState: makeDraftState(2) },
    });
    expect(next.currentRound).toBe(1);
  });

  it('does NOT change simulationDate', () => {
    const state = makeState({
      simulationDate: '2025-04-25',
      leagues: [makeLeague({ id: 'league-1' })],
    });
    const next = mockReducer(state, {
      type: 'START_RE_DRAFT',
      payload: { leagueId: 'league-1', draftState: makeDraftState(2) },
    });
    expect(next.simulationDate).toBe('2025-04-25');
  });

  it('sets draftState on global state', () => {
    const draftState = makeDraftState(2);
    const state = makeState({
      leagues: [makeLeague({ id: 'league-1' })],
    });
    const next = mockReducer(state, {
      type: 'START_RE_DRAFT',
      payload: { leagueId: 'league-1', draftState },
    });
    expect(next.draftState).toBe(draftState);
  });

  it('archives current rosters to rosterHistory for the current round', () => {
    const r1Slots = [
      {
        id: 'slot-1',
        leagueMemberId: 'member-1',
        round: 1,
        playerId: 100,
        position: 'F' as const,
        isActive: true,
        pointsEarned: 5,
        activatedFromIr: false,
      },
    ];
    const state = makeState({
      currentRound: 1,
      leagues: [makeLeague({ id: 'league-1' })],
      rosters: { 'member-1': r1Slots },
      rosterHistory: {},
    });
    const next = mockReducer(state, {
      type: 'START_RE_DRAFT',
      payload: { leagueId: 'league-1', draftState: makeDraftState(2) },
    });
    expect(next.rosterHistory['member-1']?.[1]).toEqual(r1Slots);
  });

  it('does not archive if currentRound already matches draft round', () => {
    const r2Slots = [
      {
        id: 'slot-1',
        leagueMemberId: 'member-1',
        round: 2,
        playerId: 100,
        position: 'F' as const,
        isActive: true,
        pointsEarned: 0,
        activatedFromIr: false,
      },
    ];
    const state = makeState({
      currentRound: 2,
      leagues: [makeLeague({ id: 'league-1' })],
      rosters: { 'member-1': r2Slots },
      rosterHistory: {},
    });
    const next = mockReducer(state, {
      type: 'START_RE_DRAFT',
      payload: { leagueId: 'league-1', draftState: makeDraftState(2) },
    });
    expect(next.rosterHistory['member-1']).toBeUndefined();
  });

  it('preserves existing rosterHistory entries when archiving', () => {
    const r1Slots = [
      {
        id: 'slot-r1',
        leagueMemberId: 'member-1',
        round: 1,
        playerId: 100,
        position: 'F' as const,
        isActive: true,
        pointsEarned: 5,
        activatedFromIr: false,
      },
    ];
    const r2Slots = [
      {
        id: 'slot-r2',
        leagueMemberId: 'member-1',
        round: 2,
        playerId: 200,
        position: 'D' as const,
        isActive: true,
        pointsEarned: 3,
        activatedFromIr: false,
      },
    ];
    const state = makeState({
      currentRound: 2,
      leagues: [makeLeague({ id: 'league-1' })],
      rosters: { 'member-1': r2Slots },
      rosterHistory: { 'member-1': { 1: r1Slots } },
    });
    const next = mockReducer(state, {
      type: 'START_RE_DRAFT',
      payload: { leagueId: 'league-1', draftState: makeDraftState(3) },
    });
    expect(next.rosterHistory['member-1']?.[1]).toEqual(r1Slots);
    expect(next.rosterHistory['member-1']?.[2]).toEqual(r2Slots);
  });
});

// ─── ADVANCE_ROUND: Round 3→4 auto-copy (US-007) ─────────────────────

describe('ADVANCE_ROUND: Round 3→4 roster auto-copy', () => {
  const round3Slots = [
    {
      id: 'slot-1',
      leagueMemberId: 'member-1',
      round: 3,
      playerId: 100,
      position: 'F' as const,
      isActive: true,
      pointsEarned: 5,
      activatedFromIr: false,
    },
    {
      id: 'slot-2',
      leagueMemberId: 'member-1',
      round: 3,
      playerId: 200,
      position: 'D' as const,
      isActive: true,
      pointsEarned: 3,
      activatedFromIr: false,
    },
    {
      id: 'slot-3',
      leagueMemberId: 'member-1',
      round: 3,
      playerId: 300,
      position: 'IR_F' as const,
      isActive: false,
      pointsEarned: 0,
      activatedFromIr: false,
    },
  ];

  it('copies Round 3 rosters into Round 4 when advancing from round 3', () => {
    const state = makeState({
      currentRound: 3,
      roundComplete: true,
      rosters: { 'member-1': round3Slots },
    });
    const next = mockReducer(state, { type: 'ADVANCE_ROUND' });
    expect(next.currentRound).toBe(4);
    expect(Object.keys(next.rosters)).toContain('member-1');
    expect(next.rosters['member-1']).toHaveLength(3);
  });

  it('updates round to 4 on copied slots', () => {
    const state = makeState({
      currentRound: 3,
      roundComplete: true,
      rosters: { 'member-1': round3Slots },
    });
    const next = mockReducer(state, { type: 'ADVANCE_ROUND' });
    for (const slot of next.rosters['member-1']) {
      expect(slot.round).toBe(4);
    }
  });

  it('resets pointsEarned to 0 on copied slots', () => {
    const state = makeState({
      currentRound: 3,
      roundComplete: true,
      rosters: { 'member-1': round3Slots },
    });
    const next = mockReducer(state, { type: 'ADVANCE_ROUND' });
    for (const slot of next.rosters['member-1']) {
      expect(slot.pointsEarned).toBe(0);
    }
  });

  it('preserves player IDs, positions, and IR state from Round 3', () => {
    const state = makeState({
      currentRound: 3,
      roundComplete: true,
      rosters: { 'member-1': round3Slots },
    });
    const next = mockReducer(state, { type: 'ADVANCE_ROUND' });
    const r4 = next.rosters['member-1'];
    expect(r4[0].playerId).toBe(100);
    expect(r4[0].position).toBe('F');
    expect(r4[1].playerId).toBe(200);
    expect(r4[1].position).toBe('D');
    expect(r4[2].position).toBe('IR_F');
    expect(r4[2].isActive).toBe(false);
  });

  it('copies rosters for multiple members', () => {
    const member2Slots = [
      {
        id: 'slot-m2-1',
        leagueMemberId: 'member-2',
        round: 3,
        playerId: 400,
        position: 'G' as const,
        isActive: true,
        pointsEarned: 8,
        activatedFromIr: false,
      },
    ];
    const state = makeState({
      currentRound: 3,
      roundComplete: true,
      rosters: { 'member-1': round3Slots, 'member-2': member2Slots },
    });
    const next = mockReducer(state, { type: 'ADVANCE_ROUND' });
    expect(Object.keys(next.rosters)).toHaveLength(2);
    expect(next.rosters['member-2'][0].playerId).toBe(400);
    expect(next.rosters['member-2'][0].round).toBe(4);
    expect(next.rosters['member-2'][0].pointsEarned).toBe(0);
  });

  it('archives Round 3 rosters to rosterHistory', () => {
    const state = makeState({
      currentRound: 3,
      roundComplete: true,
      rosters: { 'member-1': round3Slots },
      rosterHistory: {},
    });
    const next = mockReducer(state, { type: 'ADVANCE_ROUND' });
    expect(next.rosterHistory['member-1']?.[3]).toEqual(round3Slots);
  });

  it('preserves activatedFromIr state on IR slots', () => {
    const slotsWithActivatedIr = [
      {
        ...round3Slots[2],
        isActive: true,
        activatedFromIr: true,
      },
    ];
    const state = makeState({
      currentRound: 3,
      roundComplete: true,
      rosters: { 'member-1': slotsWithActivatedIr },
    });
    const next = mockReducer(state, { type: 'ADVANCE_ROUND' });
    expect(next.rosters['member-1'][0].activatedFromIr).toBe(true);
    expect(next.rosters['member-1'][0].isActive).toBe(true);
  });

  it('does NOT copy rosters for round 1→2 advance', () => {
    const state = makeState({
      currentRound: 1,
      roundComplete: true,
      rosters: { 'member-1': round3Slots },
    });
    const next = mockReducer(state, { type: 'ADVANCE_ROUND' });
    expect(next.rosters).toEqual({});
  });

  it('does NOT copy rosters for round 2→3 advance', () => {
    const round2Slots = round3Slots.map((s) => ({ ...s, round: 2 }));
    const state = makeState({
      currentRound: 2,
      roundComplete: true,
      rosters: { 'member-1': round2Slots },
    });
    const next = mockReducer(state, { type: 'ADVANCE_ROUND' });
    expect(next.rosters).toEqual({});
  });
});

// ─── SKIP_TO_ROUND4 (US-007) ──────────────────────────────────────────

describe('SKIP_TO_ROUND4', () => {
  it('sets league status to active', () => {
    const state = makeState({
      leagues: [makeLeague({ id: 'lg-1', status: 'drafting' })],
    });
    const next = mockReducer(state, {
      type: 'SKIP_TO_ROUND4',
      payload: { leagueId: 'lg-1' },
    });
    expect(next.leagues[0].status).toBe('active');
  });

  it('sets league currentRound to 4', () => {
    const state = makeState({
      leagues: [makeLeague({ id: 'lg-1', currentRound: 3 })],
    });
    const next = mockReducer(state, {
      type: 'SKIP_TO_ROUND4',
      payload: { leagueId: 'lg-1' },
    });
    expect(next.leagues[0].currentRound).toBe(4);
  });

  it('does not change global currentRound or simulationDate', () => {
    const state = makeState({
      currentRound: 4,
      simulationDate: '2025-05-20',
      leagues: [makeLeague({ id: 'lg-1' })],
    });
    const next = mockReducer(state, {
      type: 'SKIP_TO_ROUND4',
      payload: { leagueId: 'lg-1' },
    });
    expect(next.currentRound).toBe(4);
    expect(next.simulationDate).toBe('2025-05-20');
  });

  it('only affects the targeted league', () => {
    const state = makeState({
      leagues: [
        makeLeague({ id: 'lg-1', status: 'active', currentRound: 3 }),
        makeLeague({ id: 'lg-2', status: 'active', currentRound: 3 }),
      ],
    });
    const next = mockReducer(state, {
      type: 'SKIP_TO_ROUND4',
      payload: { leagueId: 'lg-1' },
    });
    expect(next.leagues[0].currentRound).toBe(4);
    expect(next.leagues[1].currentRound).toBe(3);
  });

  it('copies R3 rosters to R4 with round=4 and pointsEarned=0', () => {
    const r3Slots = [
      {
        id: 'slot-1',
        leagueMemberId: 'member-1',
        round: 3,
        playerId: 100,
        position: 'F' as const,
        isActive: true,
        pointsEarned: 42,
        activatedFromIr: false,
      },
      {
        id: 'slot-2',
        leagueMemberId: 'member-1',
        round: 3,
        playerId: 200,
        position: 'D' as const,
        isActive: true,
        pointsEarned: 18,
        activatedFromIr: false,
      },
    ];
    const state = makeState({
      leagues: [makeLeague({ id: 'lg-1', currentRound: 3 })],
      rosters: { 'member-1': r3Slots },
    });
    const next = mockReducer(state, {
      type: 'SKIP_TO_ROUND4',
      payload: { leagueId: 'lg-1' },
    });
    expect(next.rosters['member-1']).toHaveLength(2);
    expect(next.rosters['member-1'][0].round).toBe(4);
    expect(next.rosters['member-1'][0].pointsEarned).toBe(0);
    expect(next.rosters['member-1'][0].playerId).toBe(100);
    expect(next.rosters['member-1'][1].round).toBe(4);
    expect(next.rosters['member-1'][1].pointsEarned).toBe(0);
  });

  it('archives R3 rosters to rosterHistory', () => {
    const r3Slots = [
      {
        id: 'slot-1',
        leagueMemberId: 'member-1',
        round: 3,
        playerId: 100,
        position: 'F' as const,
        isActive: true,
        pointsEarned: 42,
        activatedFromIr: false,
      },
    ];
    const state = makeState({
      leagues: [makeLeague({ id: 'lg-1', currentRound: 3 })],
      rosters: { 'member-1': r3Slots },
      rosterHistory: {},
    });
    const next = mockReducer(state, {
      type: 'SKIP_TO_ROUND4',
      payload: { leagueId: 'lg-1' },
    });
    expect(next.rosterHistory['member-1']).toBeDefined();
    expect(next.rosterHistory['member-1'][3]).toEqual(r3Slots);
  });

  it('is idempotent — does not duplicate R4 rosters if they already exist', () => {
    const r4Slots = [
      {
        id: 'slot-1',
        leagueMemberId: 'member-1',
        round: 4,
        playerId: 100,
        position: 'F' as const,
        isActive: true,
        pointsEarned: 0,
        activatedFromIr: false,
      },
    ];
    const state = makeState({
      leagues: [makeLeague({ id: 'lg-1', currentRound: 3 })],
      rosters: { 'member-1': r4Slots },
      rosterHistory: { 'member-1': { 3: r4Slots } },
    });
    const next = mockReducer(state, {
      type: 'SKIP_TO_ROUND4',
      payload: { leagueId: 'lg-1' },
    });
    // Rosters should be unchanged (already R4)
    expect(next.rosters).toEqual(state.rosters);
    expect(next.rosterHistory).toEqual(state.rosterHistory);
  });

  it('does not create rosters when state.rosters is empty', () => {
    const state = makeState({
      leagues: [makeLeague({ id: 'lg-1', currentRound: 3 })],
      rosters: {},
    });
    const next = mockReducer(state, {
      type: 'SKIP_TO_ROUND4',
      payload: { leagueId: 'lg-1' },
    });
    expect(next.rosters).toEqual({});
  });

  it('copies rosters for multiple members', () => {
    const m1Slots = [
      {
        id: 'slot-1',
        leagueMemberId: 'member-1',
        round: 3,
        playerId: 100,
        position: 'F' as const,
        isActive: true,
        pointsEarned: 10,
        activatedFromIr: false,
      },
    ];
    const m2Slots = [
      {
        id: 'slot-2',
        leagueMemberId: 'member-2',
        round: 3,
        playerId: 200,
        position: 'D' as const,
        isActive: true,
        pointsEarned: 20,
        activatedFromIr: false,
      },
    ];
    const state = makeState({
      leagues: [makeLeague({ id: 'lg-1', currentRound: 3 })],
      rosters: { 'member-1': m1Slots, 'member-2': m2Slots },
    });
    const next = mockReducer(state, {
      type: 'SKIP_TO_ROUND4',
      payload: { leagueId: 'lg-1' },
    });
    expect(next.rosters['member-1'][0].round).toBe(4);
    expect(next.rosters['member-1'][0].pointsEarned).toBe(0);
    expect(next.rosters['member-2'][0].round).toBe(4);
    expect(next.rosters['member-2'][0].pointsEarned).toBe(0);
    expect(next.rosterHistory['member-1'][3]).toEqual(m1Slots);
    expect(next.rosterHistory['member-2'][3]).toEqual(m2Slots);
  });
});
