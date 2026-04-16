export interface OtpAuthClient {
  signInWithOtp: (params: {
    email: string;
    options: { shouldCreateUser: boolean };
  }) => Promise<{ error: { message: string } | null }>;
  verifyOtp: (params: {
    email: string;
    token: string;
    type: 'email';
  }) => Promise<{
    data: { user: unknown; session: unknown } | null;
    error: { message: string } | null;
  }>;
}

export async function sendOtpCode(
  client: OtpAuthClient,
  email: string
): Promise<{ error: { message: string } | null }> {
  const { error } = await client.signInWithOtp({
    email,
    options: { shouldCreateUser: true },
  });
  return { error };
}

export async function verifyOtpCode(
  client: OtpAuthClient,
  email: string,
  token: string
): Promise<{
  data: { user: unknown; session: unknown } | null;
  error: { message: string } | null;
}> {
  const { data, error } = await client.verifyOtp({
    email,
    token,
    type: 'email',
  });
  return { data, error };
}
