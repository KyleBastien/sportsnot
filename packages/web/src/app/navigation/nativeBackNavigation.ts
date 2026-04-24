/**
 * Map of route pattern -> back-destination builder.
 * Patterns are tested in order; first match wins.
 * Capture group 1 is the leagueId where applicable.
 */
const NATIVE_BACK_ROUTES: Array<
  [RegExp, ((match: RegExpMatchArray) => string) | null]
> = [
  [/^\/leagues\/create$/, () => '/'],
  [/^\/leagues\/join$/, () => '/'],
  [/^\/leagues\/([^/]+)\/settings$/, (match) => `/leagues/${match[1]}`],
  [/^\/leagues\/([^/]+)$/, () => '/'],
  [/^\/draft\/([^/]+)\/lobby$/, (match) => `/leagues/${match[1]}`],
  [/^\/draft\//, null],
  [/^\/roster\/([^/]+)\/history$/, (match) => `/roster/${match[1]}`],
  [/^\/roster\/([^/]+)/, (match) => `/leagues/${match[1]}`],
  [/^\/standings\/([^/]+)/, (match) => `/leagues/${match[1]}`],
  [/^\/scoring\/([^/]+)/, (match) => `/leagues/${match[1]}`],
  [/^\/profile$/, () => '/'],
];

/**
 * Returns the native back destination for the current route.
 * Null means native back should be disabled for this pathname.
 */
export function getNativeBackDestination(pathname: string): string | null {
  if (pathname === '/' || pathname.startsWith('/auth')) {
    return null;
  }

  for (const [pattern, builder] of NATIVE_BACK_ROUTES) {
    const match = pathname.match(pattern);
    if (match) {
      return builder ? builder(match) : null;
    }
  }

  return null;
}

export function canNativeSwipeBack(pathname: string): boolean {
  return getNativeBackDestination(pathname) !== null;
}
