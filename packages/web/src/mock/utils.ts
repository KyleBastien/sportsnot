export function isMockMode(): boolean {
  return import.meta.env.VITE_MOCK_MODE === 'true';
}
