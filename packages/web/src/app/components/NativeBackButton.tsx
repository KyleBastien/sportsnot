import { useLocation, useNavigate } from 'react-router-dom';
import { ActionIcon } from '@mantine/core';
import { IconChevronLeft } from '@tabler/icons-react';
import { useIsNativeIOS } from '../hooks/useIsNativeIOS';

/**
 * Map of route pattern → back-destination builder.
 * Patterns are tested in order; first match wins.
 * Capture group 1 is the leagueId where applicable.
 */
const BACK_ROUTES = new Map<RegExp, ((m: RegExpMatchArray) => string) | null>([
  [/^\/leagues\/create$/, () => '/'],
  [/^\/leagues\/join$/, () => '/'],
  [/^\/leagues\/([^/]+)\/settings$/, (m) => `/leagues/${m[1]}`],
  [/^\/leagues\/([^/]+)$/, () => '/'],
  [/^\/draft\/([^/]+)\/lobby$/, (m) => `/leagues/${m[1]}`],
  [/^\/draft\//, null],
  [/^\/roster\/([^/]+)\/history$/, (m) => `/roster/${m[1]}`],
  [/^\/roster\/([^/]+)/, (m) => `/leagues/${m[1]}`],
  [/^\/standings\/([^/]+)/, (m) => `/leagues/${m[1]}`],
  [/^\/scoring\/([^/]+)/, (m) => `/leagues/${m[1]}`],
  [/^\/profile$/, () => '/'],
]);

/**
 * Given the current pathname, returns the "back" destination or null
 * when no back button should be shown (home, auth, mid-draft, transition).
 */
function getBackDestination(pathname: string): string | null {
  if (pathname === '/' || pathname.startsWith('/auth')) return null;

  for (const [pattern, builder] of BACK_ROUTES) {
    const match = pathname.match(pattern);
    if (match) return builder ? builder(match) : null;
  }

  return null;
}

export function NativeBackButton() {
  const isNativeIOS = useIsNativeIOS();
  const { pathname } = useLocation();
  const navigate = useNavigate();

  if (!isNativeIOS) return null;

  const destination = getBackDestination(pathname);
  if (!destination) return null;

  return (
    <ActionIcon
      variant="subtle"
      size="lg"
      aria-label="Go back"
      onClick={() => navigate(destination)}
    >
      <IconChevronLeft size={24} />
    </ActionIcon>
  );
}
