import { useMediaQuery } from '@mantine/hooks';

/**
 * Returns true when viewport is below the Mantine `sm` breakpoint (768px).
 * SSR-safe — returns false on first render to avoid hydration mismatches.
 */
export function useIsMobile(): boolean {
  const matches = useMediaQuery('(max-width: 48em)');
  return matches ?? false;
}
