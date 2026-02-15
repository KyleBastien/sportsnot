import type { ReactNode } from 'react';
import { AuthContext } from '../app/context/AuthContext';
import { useMockAuth } from './hooks/useMockAuth';

export function MockAuthProvider({ children }: { children: ReactNode }) {
  const auth = useMockAuth();
  return <AuthContext.Provider value={auth}>{children}</AuthContext.Provider>;
}
