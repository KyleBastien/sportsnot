import { describe, it, expect } from '@rstest/core';
import type { AuthContextValue } from './AuthContext';

function createMockAuthContext(
  overrides?: Partial<AuthContextValue>
): AuthContextValue {
  return {
    user: null,
    session: null,
    loading: false,
    signInWithMagicLink: async () => ({ error: null }),
    signInWithOtp: async () => ({ error: null }),
    verifyOtp: async () => ({ data: null, error: null }),
    signOut: async () => ({ error: null }),
    ...overrides,
  };
}

describe('AuthContextValue', () => {
  it('should include signInWithOtp method', () => {
    const ctx = createMockAuthContext();
    expect(typeof ctx.signInWithOtp).toBe('function');
  });

  it('should include verifyOtp method', () => {
    const ctx = createMockAuthContext();
    expect(typeof ctx.verifyOtp).toBe('function');
  });

  it('signInWithOtp should return { error } shape', async () => {
    const ctx = createMockAuthContext();
    const result = await ctx.signInWithOtp('test@example.com');
    expect(result).toEqual({ error: null });
  });

  it('verifyOtp should return { data, error } shape', async () => {
    const ctx = createMockAuthContext();
    const result = await ctx.verifyOtp('test@example.com', '123456');
    expect(result).toEqual({ data: null, error: null });
  });

  it('signInWithOtp should propagate errors', async () => {
    const mockError = new Error('Rate limit exceeded');
    const ctx = createMockAuthContext({
      signInWithOtp: async () => ({ error: mockError }),
    });
    const result = await ctx.signInWithOtp('test@example.com');
    expect(result.error).toBe(mockError);
    expect(result.error?.message).toBe('Rate limit exceeded');
  });

  it('verifyOtp should propagate errors', async () => {
    const mockError = new Error('Invalid code');
    const ctx = createMockAuthContext({
      verifyOtp: async () => ({ data: null, error: mockError }),
    });
    const result = await ctx.verifyOtp('test@example.com', '000000');
    expect(result.error).toBe(mockError);
    expect(result.data).toBeNull();
  });

  it('should still include existing signInWithMagicLink method', () => {
    const ctx = createMockAuthContext();
    expect(typeof ctx.signInWithMagicLink).toBe('function');
  });

  it('should still include existing signOut method', () => {
    const ctx = createMockAuthContext();
    expect(typeof ctx.signOut).toBe('function');
  });
});
