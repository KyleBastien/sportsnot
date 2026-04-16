import { describe, it, expect } from '@rstest/core';
import { useMockAuth } from './useMockAuth';

describe('useMockAuth', () => {
  it('should return user, session, and loading state', () => {
    const auth = useMockAuth();
    expect(auth.user).toBeDefined();
    expect(auth.user.email).toBe('mock@sportsnot.dev');
    expect(auth.session).toBeDefined();
    expect(auth.loading).toBe(false);
  });

  it('should return signInWithMagicLink method', () => {
    const auth = useMockAuth();
    expect(typeof auth.signInWithMagicLink).toBe('function');
  });

  it('should return signInWithOtp method', () => {
    const auth = useMockAuth();
    expect(typeof auth.signInWithOtp).toBe('function');
  });

  it('should return verifyOtp method', () => {
    const auth = useMockAuth();
    expect(typeof auth.verifyOtp).toBe('function');
  });

  it('should return signOut method', () => {
    const auth = useMockAuth();
    expect(typeof auth.signOut).toBe('function');
  });

  describe('signInWithOtp', () => {
    it('should resolve with no error', async () => {
      const auth = useMockAuth();
      const result = await auth.signInWithOtp('test@example.com');
      expect(result.error).toBe(null);
    });
  });

  describe('verifyOtp', () => {
    it('should accept a valid 6-digit code', async () => {
      const auth = useMockAuth();
      const result = await auth.verifyOtp('test@example.com', '123456');
      expect(result.error).toBe(null);
      expect(result.data).toBeDefined();
    });

    it('should return user and session for valid code', async () => {
      const auth = useMockAuth();
      const result = await auth.verifyOtp('test@example.com', '000000');
      const data = result.data as { user: unknown; session: unknown };
      expect(data.user).toBeDefined();
      expect(data.session).toBeDefined();
    });

    it('should reject non-6-digit input', async () => {
      const auth = useMockAuth();
      const result = await auth.verifyOtp('test@example.com', '12345');
      expect(result.error).not.toBe(null);
      expect(result.error?.message).toBe('Invalid OTP code');
      expect(result.data).toBe(null);
    });

    it('should reject non-numeric input', async () => {
      const auth = useMockAuth();
      const result = await auth.verifyOtp('test@example.com', 'abcdef');
      expect(result.error).not.toBe(null);
      expect(result.error?.message).toBe('Invalid OTP code');
    });

    it('should reject empty string', async () => {
      const auth = useMockAuth();
      const result = await auth.verifyOtp('test@example.com', '');
      expect(result.error).not.toBe(null);
      expect(result.error?.message).toBe('Invalid OTP code');
    });

    it('should reject 7-digit input', async () => {
      const auth = useMockAuth();
      const result = await auth.verifyOtp('test@example.com', '1234567');
      expect(result.error).not.toBe(null);
    });
  });

  describe('signInWithMagicLink', () => {
    it('should resolve with no error', async () => {
      const auth = useMockAuth();
      const result = await auth.signInWithMagicLink('test@example.com');
      expect(result.error).toBe(null);
    });
  });

  describe('signOut', () => {
    it('should resolve with no error', async () => {
      const auth = useMockAuth();
      const result = await auth.signOut();
      expect(result.error).toBe(null);
    });
  });
});
