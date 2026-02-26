import { describe, it, expect } from '@rstest/core';
import {
  updateProfileDisplayName,
  type ProfileUpdateClient,
} from './updateProfile';

function createMockClient(overrides?: {
  tableError?: { message: string } | null;
  authError?: { message: string } | null;
}): ProfileUpdateClient & {
  tableCallArgs: { userId: string; displayName: string }[];
  authCallArgs: string[];
} {
  const tableCallArgs: { userId: string; displayName: string }[] = [];
  const authCallArgs: string[] = [];

  return {
    tableCallArgs,
    authCallArgs,
    updateUsersTable: async (userId: string, displayName: string) => {
      tableCallArgs.push({ userId, displayName });
      return { error: overrides?.tableError ?? null };
    },
    updateAuthMetadata: async (displayName: string) => {
      authCallArgs.push(displayName);
      return { error: overrides?.authError ?? null };
    },
  };
}

describe('updateProfileDisplayName', () => {
  it('should reject empty display name without calling client', async () => {
    const client = createMockClient();
    const result = await updateProfileDisplayName(client, 'user-1', '');
    expect(result.error).toBe('Display name is required');
    expect(client.tableCallArgs.length).toBe(0);
    expect(client.authCallArgs.length).toBe(0);
  });

  it('should reject whitespace-only display name', async () => {
    const client = createMockClient();
    const result = await updateProfileDisplayName(client, 'user-1', '   ');
    expect(result.error).toBe('Display name is required');
    expect(client.tableCallArgs.length).toBe(0);
  });

  it('should trim whitespace before saving', async () => {
    const client = createMockClient();
    const result = await updateProfileDisplayName(
      client,
      'user-1',
      '  Player One  '
    );
    expect(result.error).toBeNull();
    expect(result.trimmedName).toBe('Player One');
    expect(client.tableCallArgs[0]?.displayName).toBe('Player One');
    expect(client.authCallArgs[0]).toBe('Player One');
  });

  it('should update both users table and auth metadata on success', async () => {
    const client = createMockClient();
    const result = await updateProfileDisplayName(
      client,
      'user-123',
      'New Name'
    );
    expect(result.error).toBeNull();
    expect(result.trimmedName).toBe('New Name');
    expect(client.tableCallArgs).toEqual([
      { userId: 'user-123', displayName: 'New Name' },
    ]);
    expect(client.authCallArgs).toEqual(['New Name']);
  });

  it('should return error when users table update fails', async () => {
    const client = createMockClient({
      tableError: { message: 'DB connection failed' },
    });
    const result = await updateProfileDisplayName(
      client,
      'user-1',
      'Valid Name'
    );
    expect(result.error).toBe('DB connection failed');
    expect(client.authCallArgs.length).toBe(0);
  });

  it('should return error when auth metadata update fails', async () => {
    const client = createMockClient({
      authError: { message: 'Auth service unavailable' },
    });
    const result = await updateProfileDisplayName(
      client,
      'user-1',
      'Valid Name'
    );
    expect(result.error).toBe('Auth service unavailable');
    expect(client.tableCallArgs.length).toBe(1);
  });

  it('should accept a name at exactly 30 characters', async () => {
    const client = createMockClient();
    const name = 'A'.repeat(30);
    const result = await updateProfileDisplayName(client, 'user-1', name);
    expect(result.error).toBeNull();
    expect(result.trimmedName).toBe(name);
  });

  it('should not call auth update if table update fails', async () => {
    const client = createMockClient({
      tableError: { message: 'table error' },
    });
    await updateProfileDisplayName(client, 'user-1', 'Name');
    expect(client.tableCallArgs.length).toBe(1);
    expect(client.authCallArgs.length).toBe(0);
  });
});
