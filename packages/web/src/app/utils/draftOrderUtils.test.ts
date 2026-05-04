import { describe, expect, it } from '@rstest/core';
import { buildDraftOrder } from './draftOrderUtils';

describe('buildDraftOrder', () => {
  const members = [
    { user_id: 'user-1', team_name: 'Alpha', total_points: 37 },
    { user_id: 'user-2', team_name: 'Delta', total_points: 56 },
    { user_id: 'user-3', team_name: 'Charlie', total_points: 53 },
    { user_id: 'user-4', team_name: 'Bravo', total_points: 51 },
  ];

  it('builds a full round 1 snake order from the shuffled seed', () => {
    const draftOrder = buildDraftOrder(members, false, 1, () => [
      'user-3',
      'user-1',
      'user-4',
      'user-2',
    ]);

    expect(draftOrder).toHaveLength(36);
    expect(draftOrder.slice(0, 8)).toEqual([
      'user-3',
      'user-1',
      'user-4',
      'user-2',
      'user-2',
      'user-4',
      'user-1',
      'user-3',
    ]);
  });

  it('builds a full re-draft snake order seeded worst to best', () => {
    const draftOrder = buildDraftOrder(members, false, 2);

    expect(draftOrder).toHaveLength(36);
    expect(draftOrder.slice(0, 8)).toEqual([
      'user-1',
      'user-4',
      'user-3',
      'user-2',
      'user-2',
      'user-3',
      'user-4',
      'user-1',
    ]);
  });
});
