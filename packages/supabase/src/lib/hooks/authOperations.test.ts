import { describe, it, expect } from '@rstest/core';
import {
  sendOtpCode,
  verifyOtpCode,
  type OtpAuthClient,
} from './authOperations';

function createMockClient(overrides?: {
  signInError?: { message: string } | null;
  verifyError?: { message: string } | null;
  verifyData?: { user: unknown; session: unknown } | null;
}): OtpAuthClient & {
  signInCalls: { email: string; options: { shouldCreateUser: boolean } }[];
  verifyCalls: { email: string; token: string; type: 'email' }[];
} {
  const signInCalls: {
    email: string;
    options: { shouldCreateUser: boolean };
  }[] = [];
  const verifyCalls: { email: string; token: string; type: 'email' }[] = [];

  return {
    signInCalls,
    verifyCalls,
    signInWithOtp: async (params) => {
      signInCalls.push(params);
      return { error: overrides?.signInError ?? null };
    },
    verifyOtp: async (params) => {
      verifyCalls.push(params);
      return {
        data:
          overrides?.verifyError != null
            ? (overrides?.verifyData ?? null)
            : (overrides?.verifyData ?? { user: { id: 'u1' }, session: {} }),
        error: overrides?.verifyError ?? null,
      };
    },
  };
}

describe('sendOtpCode', () => {
  it('should call signInWithOtp with shouldCreateUser true', async () => {
    const client = createMockClient();
    await sendOtpCode(client, 'test@example.com');
    expect(client.signInCalls.length).toBe(1);
    expect(client.signInCalls[0]?.email).toBe('test@example.com');
    expect(client.signInCalls[0]?.options.shouldCreateUser).toBe(true);
  });

  it('should NOT pass emailRedirectTo in options', async () => {
    const client = createMockClient();
    await sendOtpCode(client, 'test@example.com');
    const callOptions = client.signInCalls[0]?.options;
    expect(Object.keys(callOptions as object)).toEqual(['shouldCreateUser']);
  });

  it('should return null error on success', async () => {
    const client = createMockClient();
    const result = await sendOtpCode(client, 'test@example.com');
    expect(result.error).toBeNull();
  });

  it('should return error when signInWithOtp fails', async () => {
    const client = createMockClient({
      signInError: { message: 'Rate limit exceeded' },
    });
    const result = await sendOtpCode(client, 'test@example.com');
    expect(result.error).not.toBeNull();
    expect(result.error?.message).toBe('Rate limit exceeded');
  });
});

describe('verifyOtpCode', () => {
  it('should call verifyOtp with email, token, and type email', async () => {
    const client = createMockClient();
    await verifyOtpCode(client, 'test@example.com', '123456');
    expect(client.verifyCalls.length).toBe(1);
    expect(client.verifyCalls[0]?.email).toBe('test@example.com');
    expect(client.verifyCalls[0]?.token).toBe('123456');
    expect(client.verifyCalls[0]?.type).toBe('email');
  });

  it('should return data and null error on success', async () => {
    const mockData = { user: { id: 'user-1' }, session: { token: 'abc' } };
    const client = createMockClient({ verifyData: mockData });
    const result = await verifyOtpCode(client, 'test@example.com', '123456');
    expect(result.error).toBeNull();
    expect(result.data).toEqual(mockData);
  });

  it('should return error on invalid code', async () => {
    const client = createMockClient({
      verifyError: { message: 'Invalid OTP code' },
      verifyData: null,
    });
    const result = await verifyOtpCode(client, 'test@example.com', '000000');
    expect(result.error?.message).toBe('Invalid OTP code');
    expect(result.data).toBeNull();
  });

  it('should return error on expired code', async () => {
    const client = createMockClient({
      verifyError: { message: 'Token has expired' },
      verifyData: null,
    });
    const result = await verifyOtpCode(client, 'test@example.com', '999999');
    expect(result.error?.message).toBe('Token has expired');
  });
});
