import { useLocation, useNavigate } from 'react-router-dom';
import { ActionIcon } from '@mantine/core';
import { IconChevronLeft } from '@tabler/icons-react';
import { useIsNativeIOS } from '../hooks/useIsNativeIOS';

/**
 * Given the current pathname, returns the "back" destination or null
 * when no back button should be shown (home, auth, mid-draft, transition).
 */
function getBackDestination(pathname: string): string | null {
  // No back button on home, auth, or draft/transition pages
  if (pathname === '/' || pathname.startsWith('/auth')) return null;

  // /draft/:leagueId (exact) — mid-draft, no back
  // /draft/:leagueId/transition — no back
  const draftMatch = pathname.match(/^\/draft\/([^/]+)(\/.*)?$/);
  if (draftMatch) {
    const suffix = draftMatch[2] ?? '';
    if (suffix === '' || suffix === '/transition') return null;
    // /draft/:leagueId/lobby → league dashboard
    if (suffix === '/lobby') return `/leagues/${draftMatch[1]}`;
    return null;
  }

  // /leagues/create or /leagues/join → dashboard
  if (pathname === '/leagues/create' || pathname === '/leagues/join') {
    return '/';
  }

  // /leagues/:leagueId/settings → league dashboard
  const settingsMatch = pathname.match(/^\/leagues\/([^/]+)\/settings$/);
  if (settingsMatch) return `/leagues/${settingsMatch[1]}`;

  // /leagues/:leagueId → dashboard
  const leagueMatch = pathname.match(/^\/leagues\/([^/]+)$/);
  if (leagueMatch) return '/';

  // /roster/:leagueId/history → roster page
  const rosterHistoryMatch = pathname.match(/^\/roster\/([^/]+)\/history$/);
  if (rosterHistoryMatch) return `/roster/${rosterHistoryMatch[1]}`;

  // /roster/:leagueId/:leagueMemberId? → league dashboard
  const rosterMatch = pathname.match(/^\/roster\/([^/]+)/);
  if (rosterMatch) return `/leagues/${rosterMatch[1]}`;

  // /standings/:leagueId → league dashboard
  const standingsMatch = pathname.match(/^\/standings\/([^/]+)/);
  if (standingsMatch) return `/leagues/${standingsMatch[1]}`;

  // /scoring/:leagueId → league dashboard
  const scoringMatch = pathname.match(/^\/scoring\/([^/]+)/);
  if (scoringMatch) return `/leagues/${scoringMatch[1]}`;

  // /profile → dashboard
  if (pathname === '/profile') return '/';

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
