import React from 'react';
import { afterEach, describe, expect, it } from '@rstest/core';
import { cleanup, screen } from '@testing-library/react';
import type { User } from '@supabase/supabase-js';
import { UserMenu } from './UserMenu';
import { renderWithAuth } from '../test-utils/renderWithAuth';

const mockUser = {
  id: 'user-123',
  email: 'tester@example.com',
  user_metadata: { display_name: 'Tester' },
} as unknown as User;

afterEach(() => {
  cleanup();
});

describe('UserMenu', () => {
  it('renders skeleton placeholder while AuthContext.loading=true', () => {
    renderWithAuth(<UserMenu />, { auth: { loading: true, user: null } });

    expect(
      document.querySelector('[data-testid="user-menu-skeleton"]')
    ).not.toBeNull();
    expect(screen.queryByRole('link', { name: /sign in/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /sign in/i })).toBeNull();
  });

  it('renders Sign In button when not loading and no user', () => {
    renderWithAuth(<UserMenu />, { auth: { loading: false, user: null } });

    expect(
      document.querySelector('[data-testid="user-menu-skeleton"]')
    ).toBeNull();
    expect(screen.getByRole('link', { name: /sign in/i })).toBeTruthy();
  });

  it('renders user dropdown trigger when not loading and user is present', () => {
    renderWithAuth(<UserMenu />, {
      auth: { loading: false, user: mockUser },
    });

    expect(
      document.querySelector('[data-testid="user-menu-skeleton"]')
    ).toBeNull();
    expect(screen.queryByRole('link', { name: /sign in/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /sign in/i })).toBeNull();
    expect(screen.getByText('Tester')).toBeTruthy();
  });
});
