import { describe, expect, it } from '@rstest/core';
import {
  canNativeSwipeBack,
  getNativeBackDestination,
} from './nativeBackNavigation';

describe('nativeBackNavigation', () => {
  it('blocks home and auth routes', () => {
    expect(getNativeBackDestination('/')).toBeNull();
    expect(getNativeBackDestination('/auth/login')).toBeNull();
    expect(getNativeBackDestination('/auth/callback')).toBeNull();
  });

  it('maps create and join league routes back to dashboard', () => {
    expect(getNativeBackDestination('/leagues/create')).toBe('/');
    expect(getNativeBackDestination('/leagues/join')).toBe('/');
  });

  it('maps league settings back to league dashboard', () => {
    expect(getNativeBackDestination('/leagues/league-123/settings')).toBe(
      '/leagues/league-123'
    );
  });

  it('maps league dashboard back to dashboard', () => {
    expect(getNativeBackDestination('/leagues/league-123')).toBe('/');
  });

  it('allows draft lobby but blocks active draft routes', () => {
    expect(getNativeBackDestination('/draft/league-123/lobby')).toBe(
      '/leagues/league-123'
    );
    expect(getNativeBackDestination('/draft/league-123')).toBeNull();
    expect(getNativeBackDestination('/draft/league-123/transition')).toBeNull();
  });

  it('maps roster routes with exact current behavior', () => {
    expect(getNativeBackDestination('/roster/league-123')).toBe(
      '/leagues/league-123'
    );
    expect(getNativeBackDestination('/roster/league-123/member-456')).toBe(
      '/leagues/league-123'
    );
    expect(getNativeBackDestination('/roster/league-123/history')).toBe(
      '/roster/league-123'
    );
  });

  it('maps standings, scoring, and profile routes', () => {
    expect(getNativeBackDestination('/standings/league-123')).toBe(
      '/leagues/league-123'
    );
    expect(getNativeBackDestination('/scoring/league-123')).toBe(
      '/leagues/league-123'
    );
    expect(getNativeBackDestination('/profile')).toBe('/');
  });

  it('returns null for unknown routes and mirrors swipe eligibility', () => {
    expect(getNativeBackDestination('/unknown')).toBeNull();
    expect(canNativeSwipeBack('/profile')).toBe(true);
    expect(canNativeSwipeBack('/draft/league-123')).toBe(false);
  });
});
