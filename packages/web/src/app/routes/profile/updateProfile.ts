import { validateDisplayName } from './profileValidation';

export interface ProfileUpdateClient {
  updateUsersTable: (
    userId: string,
    displayName: string
  ) => Promise<{ error: { message: string } | null }>;
  updateAuthMetadata: (
    displayName: string
  ) => Promise<{ error: { message: string } | null }>;
}

export interface ProfileUpdateResult {
  error: string | null;
  trimmedName: string;
}

export async function updateProfileDisplayName(
  client: ProfileUpdateClient,
  userId: string,
  displayName: string
): Promise<ProfileUpdateResult> {
  const validationError = validateDisplayName(displayName);
  if (validationError) {
    return { error: validationError, trimmedName: '' };
  }

  const trimmedName = displayName.trim();

  const { error: tableError } = await client.updateUsersTable(
    userId,
    trimmedName
  );
  if (tableError) {
    return { error: tableError.message, trimmedName };
  }

  const { error: authError } = await client.updateAuthMetadata(trimmedName);
  if (authError) {
    return { error: authError.message, trimmedName };
  }

  return { error: null, trimmedName };
}
