import { afterEach, beforeEach, describe, expect, it, rs } from '@rstest/core';
import { cleanup, screen } from '@testing-library/react';
import type { User } from '@supabase/supabase-js';
import { renderWithAuth } from '../../../test-utils/renderWithAuth';

interface MockHookResult<T> {
  data: T | null;
  isLoading: boolean;
}

const dashboardState = rs.hoisted(() => ({
  myLeagues: {
    data: null as unknown,
    isLoading: true,
  } as MockHookResult<unknown>,
  liveGames: { data: [], isLoading: false } as MockHookResult<unknown>,
}));

rs.mock('./dashboardPageQueries', () => ({
  useMyLeagues: () => dashboardState.myLeagues,
  useLiveGames: () => dashboardState.liveGames,
}));

import { DashboardPage } from './DashboardPage';

const mockUser = {
  id: 'user-1',
  email: 'me@example.com',
  user_metadata: { display_name: 'Me' },
} as unknown as User;

beforeEach(() => {
  dashboardState.myLeagues = { data: null, isLoading: true };
  dashboardState.liveGames = { data: [], isLoading: false };
});

afterEach(() => {
  cleanup();
});

describe('DashboardPage', () => {
  it('hides Create/Join League header buttons while myLeagues is loading and shows skeleton', () => {
    dashboardState.myLeagues = { data: null, isLoading: true };

    renderWithAuth(<DashboardPage />, { auth: { user: mockUser } });

    expect(screen.queryByRole('button', { name: /Create League/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /^Join League$/i })).toBeNull();
    expect(screen.getByTestId('dashboard-header-skeleton')).toBeTruthy();
  });

  it('renders Create/Join League header buttons after myLeagues resolves', () => {
    dashboardState.myLeagues = { data: [], isLoading: false };

    renderWithAuth(<DashboardPage />, { auth: { user: mockUser } });

    expect(
      screen.getByRole('button', { name: /^Create League$/i })
    ).toBeTruthy();
    expect(screen.getByRole('button', { name: /^Join League$/i })).toBeTruthy();
    expect(screen.queryByTestId('dashboard-header-skeleton')).toBeNull();
  });
});
