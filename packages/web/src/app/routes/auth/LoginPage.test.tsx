import { afterEach, describe, expect, it } from '@rstest/core';
import { cleanup, screen } from '@testing-library/react';
import type { User } from '@supabase/supabase-js';
import { LoginPage } from './LoginPage';
import { renderWithAuth } from '../../../test-utils/renderWithAuth';

const mockUser = {
  id: 'user-123',
  email: 'tester@example.com',
} as unknown as User;

afterEach(() => {
  cleanup();
});

describe('LoginPage', () => {
  it('renders centered loader while AuthContext.loading=true', () => {
    renderWithAuth(<LoginPage />, { auth: { loading: true, user: null } });

    expect(
      document.querySelector('[data-testid="login-loader"]')
    ).not.toBeNull();
    expect(screen.queryByText(/Sign in to SportsNot/i)).toBeNull();
    expect(screen.queryByPlaceholderText('you@example.com')).toBeNull();
  });

  it('renders sign-in form when not loading and no user', () => {
    renderWithAuth(<LoginPage />, { auth: { loading: false, user: null } });

    expect(document.querySelector('[data-testid="login-loader"]')).toBeNull();
    expect(screen.getByText(/Sign in to SportsNot/i)).toBeTruthy();
    expect(screen.getByPlaceholderText('you@example.com')).toBeTruthy();
  });

  it('renders loader (and not the form) when an authenticated user lands on /auth/login', () => {
    renderWithAuth(<LoginPage />, {
      auth: { loading: false, user: mockUser },
    });

    expect(
      document.querySelector('[data-testid="login-loader"]')
    ).not.toBeNull();
    expect(screen.queryByText(/Sign in to SportsNot/i)).toBeNull();
    expect(screen.queryByPlaceholderText('you@example.com')).toBeNull();
  });
});
