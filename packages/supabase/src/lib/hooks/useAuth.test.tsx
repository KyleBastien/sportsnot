import { describe, it, expect, afterEach, beforeEach } from '@rstest/core';
import { renderHook, cleanup, act, waitFor } from '@testing-library/react';
import React from 'react';
import { useAuth } from './useAuth';
import { supabase } from '../supabase';

// Store originals to restore after tests
const originalGetSession = supabase.auth.getSession;
const originalOnAuthStateChange = supabase.auth.onAuthStateChange;
const originalSignInWithOtp = supabase.auth.signInWithOtp;
const originalSignOut = supabase.auth.signOut;

afterEach(() => {
  cleanup();
  // Restore original methods
  supabase.auth.getSession = originalGetSession;
  supabase.auth.onAuthStateChange = originalOnAuthStateChange;
  supabase.auth.signInWithOtp = originalSignInWithOtp;
  supabase.auth.signOut = originalSignOut;
});

const mockUser = {
  id: 'user-123',
  email: 'test@example.com',
  aud: 'authenticated',
  role: 'authenticated',
  app_metadata: {},
  user_metadata: {},
  created_at: '2026-01-01T00:00:00Z',
};

const mockSession = {
  access_token: 'test-token',
  token_type: 'bearer',
  expires_in: 3600,
  refresh_token: 'test-refresh',
  user: mockUser,
};

function setupAuthMocks(options?: {
  session?: typeof mockSession | null;
  signInError?: Error | null;
  signOutError?: Error | null;
}) {
  const session = options?.session ?? null;
  let authChangeCallback: ((event: string, session: unknown) => void) | null =
    null;
  const unsubscribe = () => {};

  supabase.auth.getSession = (() =>
    Promise.resolve({
      data: { session },
      error: null,
    })) as typeof supabase.auth.getSession;

  supabase.auth.onAuthStateChange = ((
    callback: (event: string, session: unknown) => void
  ) => {
    authChangeCallback = callback;
    return { data: { subscription: { unsubscribe } } };
  }) as unknown as typeof supabase.auth.onAuthStateChange;

  supabase.auth.signInWithOtp = (() =>
    Promise.resolve({
      data: {},
      error: options?.signInError ?? null,
    })) as unknown as typeof supabase.auth.signInWithOtp;

  supabase.auth.signOut = (() =>
    Promise.resolve({
      error: options?.signOutError ?? null,
    })) as unknown as typeof supabase.auth.signOut;

  return {
    getAuthChangeCallback: () => authChangeCallback,
    unsubscribe,
  };
}

describe('useAuth', () => {
  it('starts with loading state', () => {
    setupAuthMocks();
    // Don't resolve getSession immediately
    supabase.auth.getSession = (() =>
      new Promise(() => {})) as typeof supabase.auth.getSession;

    const { result } = renderHook(() => useAuth());

    expect(result.current.loading).toBe(true);
    expect(result.current.user).toBe(null);
    expect(result.current.session).toBe(null);
  });

  it('restores session on mount', async () => {
    setupAuthMocks({ session: mockSession as any });

    const { result } = renderHook(() => useAuth());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.user?.id).toBe('user-123');
    expect(result.current.user?.email).toBe('test@example.com');
    expect(result.current.session).toBeTruthy();
  });

  it('sets user to null when no session exists', async () => {
    setupAuthMocks({ session: null });

    const { result } = renderHook(() => useAuth());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.user).toBe(null);
    expect(result.current.session).toBe(null);
  });

  it('updates state on auth state change', async () => {
    const { getAuthChangeCallback } = setupAuthMocks({ session: null });

    const { result } = renderHook(() => useAuth());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.user).toBe(null);

    // Simulate auth state change (sign in)
    act(() => {
      const callback = getAuthChangeCallback();
      if (callback) {
        callback('SIGNED_IN', mockSession);
      }
    });

    expect(result.current.user?.id).toBe('user-123');
    expect(result.current.session).toBeTruthy();
    expect(result.current.loading).toBe(false);
  });

  it('signInWithMagicLink calls signInWithOtp', async () => {
    let otpCalled = false;
    setupAuthMocks();
    supabase.auth.signInWithOtp = ((opts: unknown) => {
      otpCalled = true;
      return Promise.resolve({ data: {}, error: null });
    }) as unknown as typeof supabase.auth.signInWithOtp;

    const { result } = renderHook(() => useAuth());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    let signInResult: { error: unknown };
    await act(async () => {
      signInResult = await result.current.signInWithMagicLink(
        'test@example.com'
      );
    });

    expect(otpCalled).toBe(true);
    expect(signInResult!.error).toBe(null);
  });

  it('signInWithMagicLink returns error on failure', async () => {
    const signInError = new Error('Rate limit exceeded');
    setupAuthMocks({ signInError });
    // Override to return the error object in the expected format
    supabase.auth.signInWithOtp = (() =>
      Promise.resolve({
        data: {},
        error: signInError,
      })) as unknown as typeof supabase.auth.signInWithOtp;

    const { result } = renderHook(() => useAuth());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    let signInResult: { error: unknown };
    await act(async () => {
      signInResult = await result.current.signInWithMagicLink(
        'test@example.com'
      );
    });

    expect(signInResult!.error).toBeTruthy();
  });

  it('signOut calls supabase signOut', async () => {
    let signOutCalled = false;
    setupAuthMocks({ session: mockSession as any });
    supabase.auth.signOut = (() => {
      signOutCalled = true;
      return Promise.resolve({ error: null });
    }) as unknown as typeof supabase.auth.signOut;

    const { result } = renderHook(() => useAuth());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    let signOutResult: { error: unknown };
    await act(async () => {
      signOutResult = await result.current.signOut();
    });

    expect(signOutCalled).toBe(true);
    expect(signOutResult!.error).toBe(null);
  });

  it('signOut returns error on failure', async () => {
    const signOutError = new Error('Network error');
    setupAuthMocks({ session: mockSession as any });
    supabase.auth.signOut = (() =>
      Promise.resolve({
        error: signOutError,
      })) as unknown as typeof supabase.auth.signOut;

    const { result } = renderHook(() => useAuth());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    let signOutResult: { error: unknown };
    await act(async () => {
      signOutResult = await result.current.signOut();
    });

    expect(signOutResult!.error).toBeTruthy();
  });

  it('clears user on sign out auth state change', async () => {
    const { getAuthChangeCallback } = setupAuthMocks({
      session: mockSession as any,
    });

    const { result } = renderHook(() => useAuth());

    await waitFor(() => {
      expect(result.current.user?.id).toBe('user-123');
    });

    // Simulate sign out via auth state change
    act(() => {
      const callback = getAuthChangeCallback();
      if (callback) {
        callback('SIGNED_OUT', null);
      }
    });

    expect(result.current.user).toBe(null);
    expect(result.current.session).toBe(null);
  });

  it('unsubscribes from auth changes on unmount', async () => {
    let unsubscribeCalled = false;
    setupAuthMocks();
    supabase.auth.onAuthStateChange = ((callback: unknown) => ({
      data: {
        subscription: {
          unsubscribe: () => {
            unsubscribeCalled = true;
          },
        },
      },
    })) as unknown as typeof supabase.auth.onAuthStateChange;

    const { unmount } = renderHook(() => useAuth());

    await waitFor(() => {
      expect(true).toBe(true);
    });

    unmount();
    expect(unsubscribeCalled).toBe(true);
  });
});
