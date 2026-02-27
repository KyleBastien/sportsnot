import { useMockAuthUpdate } from '../MockAuthUpdateContext';
import { useMockData } from '../MockDataProvider';
import type { ProfileUpdateClient } from '../../app/routes/profile/updateProfile';

export function useMockUpdateProfile(): {
  createMockProfileClient: () => ProfileUpdateClient;
} {
  const updateAuth = useMockAuthUpdate();
  const { dispatch } = useMockData();

  function createMockProfileClient(): ProfileUpdateClient {
    return {
      updateUsersTable: async (_userId: string, displayName: string) => {
        dispatch({ type: 'UPDATE_PROFILE', payload: { displayName } });
        return { error: null };
      },
      updateAuthMetadata: async (displayName: string) => {
        if (updateAuth) {
          updateAuth(displayName);
        }
        return { error: null };
      },
    };
  }

  return { createMockProfileClient };
}
