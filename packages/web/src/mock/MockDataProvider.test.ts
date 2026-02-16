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

function makeState(
  overrides: Partial<MockState> = {}
): MockState {
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
});
