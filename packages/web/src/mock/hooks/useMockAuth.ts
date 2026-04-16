import type { User, Session } from '@supabase/supabase-js';

const mockUser = {
  id: 'mock-user-001',
  aud: 'authenticated',
  role: 'authenticated',
  email: 'mock@sportsnot.dev',
  email_confirmed_at: '2025-01-01T00:00:00Z',
  phone: '',
  confirmed_at: '2025-01-01T00:00:00Z',
  last_sign_in_at: '2025-01-01T00:00:00Z',
  app_metadata: { provider: 'mock', providers: ['mock'] },
  user_metadata: {
    display_name: 'Mock User',
    avatar_url: '',
  },
  identities: [],
  created_at: '2025-01-01T00:00:00Z',
  updated_at: '2025-01-01T00:00:00Z',
} as unknown as User;

const mockSession = {
  access_token: 'mock-access-token',
  token_type: 'bearer',
  expires_in: 999999,
  expires_at: Math.floor(Date.now() / 1000) + 999999,
  refresh_token: 'mock-refresh-token',
  user: mockUser,
} as unknown as Session;

const OTP_PATTERN = /^\d{6}$/;

export function useMockAuth() {
  return {
    user: mockUser,
    session: mockSession,
    loading: false,
    signInWithMagicLink: async (_email: string) => ({
      error: null as Error | null,
    }),
    signInWithOtp: async (_email: string) => ({
      error: null as Error | null,
    }),
    verifyOtp: async (_email: string, token: string) => {
      if (!OTP_PATTERN.test(token)) {
        return {
          data: null as unknown,
          error: new Error('Invalid OTP code') as Error | null,
        };
      }
      return {
        data: { user: mockUser, session: mockSession } as unknown,
        error: null as Error | null,
      };
    },
    signOut: async () => ({
      error: null as Error | null,
    }),
  };
}
