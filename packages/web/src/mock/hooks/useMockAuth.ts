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

export function useMockAuth() {
  return {
    user: mockUser,
    session: mockSession,
    loading: false,
    signInWithMagicLink: async (_email: string) => {
      console.warn(
        '[Mock Mode] Auth disabled — already signed in as Mock User'
      );
      return { error: null as Error | null };
    },
    signOut: async () => {
      console.warn(
        '[Mock Mode] Auth disabled — sign-out is a no-op in mock mode'
      );
      alert('🧪 Mock mode — auth disabled');
      return { error: null as Error | null };
    },
  };
}
