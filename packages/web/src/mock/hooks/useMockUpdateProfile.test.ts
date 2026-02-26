import { describe, it, expect } from '@rstest/core';
import {
  mockReducer,
  getInitialState,
  type MockAction,
} from '../MockDataProvider';
import type { ProfileUpdateClient } from '../../app/routes/profile/updateProfile';
import { updateProfileDisplayName } from '../../app/routes/profile/updateProfile';

describe('useMockUpdateProfile', () => {
  describe('MockDataProvider UPDATE_PROFILE action', () => {
    it('updates mockUser.displayName in state', () => {
      const state = getInitialState();
      expect(state.mockUser.displayName).toBe('Mock User');

      const action: MockAction = {
        type: 'UPDATE_PROFILE',
        payload: { displayName: 'New Name' },
      };
      const next = mockReducer(state, action);
      expect(next.mockUser.displayName).toBe('New Name');
    });

    it('preserves other mockUser fields', () => {
      const state = getInitialState();
      const action: MockAction = {
        type: 'UPDATE_PROFILE',
        payload: { displayName: 'Updated' },
      };
      const next = mockReducer(state, action);
      expect(next.mockUser.id).toBe(state.mockUser.id);
      expect(next.mockUser.email).toBe(state.mockUser.email);
      expect(next.mockUser.avatarUrl).toBe(state.mockUser.avatarUrl);
    });

    it('preserves other state fields', () => {
      const state = getInitialState();
      const action: MockAction = {
        type: 'UPDATE_PROFILE',
        payload: { displayName: 'Test' },
      };
      const next = mockReducer(state, action);
      expect(next.leagues).toBe(state.leagues);
      expect(next.currentRound).toBe(state.currentRound);
      expect(next.rosters).toBe(state.rosters);
    });
  });

  describe('mock ProfileUpdateClient integration', () => {
    it('updateUsersTable resolves with no error', async () => {
      let dispatchedAction: MockAction | null = null;
      const mockClient: ProfileUpdateClient = {
        updateUsersTable: async (_userId: string, displayName: string) => {
          dispatchedAction = {
            type: 'UPDATE_PROFILE',
            payload: { displayName },
          } as MockAction;
          return { error: null };
        },
        updateAuthMetadata: async () => ({ error: null }),
      };

      const result = await updateProfileDisplayName(
        mockClient,
        'mock-user-001',
        'New Name'
      );
      expect(result.error).toBe(null);
      expect(result.trimmedName).toBe('New Name');
      expect(dispatchedAction).not.toBe(null);
      expect((dispatchedAction as MockAction).type).toBe('UPDATE_PROFILE');
    });

    it('updateAuthMetadata resolves with no error', async () => {
      let authUpdated = false;
      const mockClient: ProfileUpdateClient = {
        updateUsersTable: async () => ({ error: null }),
        updateAuthMetadata: async () => {
          authUpdated = true;
          return { error: null };
        },
      };

      const result = await updateProfileDisplayName(
        mockClient,
        'mock-user-001',
        'New Name'
      );
      expect(result.error).toBe(null);
      expect(authUpdated).toBe(true);
    });

    it('validates input before calling mock client', async () => {
      let clientCalled = false;
      const mockClient: ProfileUpdateClient = {
        updateUsersTable: async () => {
          clientCalled = true;
          return { error: null };
        },
        updateAuthMetadata: async () => {
          clientCalled = true;
          return { error: null };
        },
      };

      const result = await updateProfileDisplayName(
        mockClient,
        'mock-user-001',
        '   '
      );
      expect(result.error).not.toBe(null);
      expect(clientCalled).toBe(false);
    });

    it('trims whitespace before updating', async () => {
      let savedName = '';
      const mockClient: ProfileUpdateClient = {
        updateUsersTable: async (_userId: string, displayName: string) => {
          savedName = displayName;
          return { error: null };
        },
        updateAuthMetadata: async () => ({ error: null }),
      };

      const result = await updateProfileDisplayName(
        mockClient,
        'mock-user-001',
        '  Trimmed Name  '
      );
      expect(result.error).toBe(null);
      expect(result.trimmedName).toBe('Trimmed Name');
      expect(savedName).toBe('Trimmed Name');
    });
  });
});
