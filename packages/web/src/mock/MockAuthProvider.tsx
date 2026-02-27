import { useState, useCallback, type ReactNode } from 'react';
import type { User, Session } from '@supabase/supabase-js';
import { AuthContext } from '../app/context/AuthContext';
import { MockAuthUpdateContext } from './MockAuthUpdateContext';

const INITIAL_USER = {
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

const MOCK_EXPIRES_AT = Math.floor(Date.now() / 1000) + 999999;

export function MockAuthProvider({ children }: { children: ReactNode }) {
  const [mockUser, setMockUser] = useState<User>(INITIAL_USER);

  const updateDisplayName = useCallback((displayName: string) => {
    setMockUser((prev) => ({
      ...prev,
      user_metadata: {
        ...prev.user_metadata,
        display_name: displayName,
      },
    }));
  }, []);

  const session = {
    access_token: 'mock-access-token',
    token_type: 'bearer',
    expires_in: 999999,
    expires_at: MOCK_EXPIRES_AT,
    refresh_token: 'mock-refresh-token',
    user: mockUser,
  } as unknown as Session;

  const auth = {
    user: mockUser,
    session,
    loading: false,
    signInWithMagicLink: async (_email: string) => ({
      error: null as Error | null,
    }),
    signInWithOtp: async (_email: string) => ({
      error: null as Error | null,
    }),
    verifyOtp: async (_email: string, _token: string) => ({
      data: null as unknown,
      error: null as Error | null,
    }),
    signOut: async () => ({ error: null as Error | null }),
  };

  return (
    <MockAuthUpdateContext.Provider value={updateDisplayName}>
      <AuthContext.Provider value={auth}>{children}</AuthContext.Provider>
    </MockAuthUpdateContext.Provider>
  );
}
