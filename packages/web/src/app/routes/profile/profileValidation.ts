export const DISPLAY_NAME_MAX_LENGTH = 30;

export function validateDisplayName(name: string): string | null {
  if (!name.trim()) {
    return 'Display name is required';
  }
  return null;
}
