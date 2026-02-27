import { createContext, useContext } from 'react';

/**
 * Context for updating the mock auth user's display name.
 * Separated from MockAuthProvider to avoid pulling in AuthContext/supabase
 * in test bundles that only need the update function.
 */
export const MockAuthUpdateContext = createContext<
  ((displayName: string) => void) | null
>(null);

export function useMockAuthUpdate(): ((displayName: string) => void) | null {
  return useContext(MockAuthUpdateContext);
}
