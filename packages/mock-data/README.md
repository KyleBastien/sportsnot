# @sportsnot/mock-data

Fixture data for SportsNot Mock Mode — replays 2025 NHL Playoff data offline.

## Downloading Fixture Data

Run the download script to fetch real 2025 NHL Playoff data from the NHL API:

```bash
nx download mock-data
```

This will fetch:

1. **Playoff bracket** — all series with team seeds and results
2. **Team rosters** — all 16 playoff team rosters
3. **Playoff schedule** — all games split by round (R1, R2, CF, SCF)
4. **Player game logs** — per-game playoff stats for every player

### Output Files

All files are written to `packages/mock-data/src/data/`:

| File                  | Export           | Description                                     |
| --------------------- | ---------------- | ----------------------------------------------- |
| `teams.ts`            | `teams`          | `NHLTeam[]` — 16 playoff teams                  |
| `players.ts`          | `players`        | `Record<string, NHLPlayer[]>` — rosters by team |
| `bracket.ts`          | `bracket`        | `NHLPlayoffSeries[]` — bracket/series data      |
| `games-r1.ts`         | `gamesR1`        | `NHLGame[]` — Round 1 games                     |
| `games-r2.ts`         | `gamesR2`        | `NHLGame[]` — Round 2 games                     |
| `games-cf.ts`         | `gamesCf`        | `NHLGame[]` — Conference Finals games           |
| `games-scf.ts`        | `gamesScf`       | `NHLGame[]` — Stanley Cup Final games           |
| `player-game-logs.ts` | `playerGameLogs` | `Record<number, NHLPlayerStats[]>` — game logs  |

### Notes

- The script is **idempotent** — running it again overwrites existing files.
- Rate limited: max 10 concurrent requests, 100ms delay between batches.
- Requires network access to `api-web.nhle.com`.
- Generated `.ts` files are committed to the repo so other developers don't need to re-download.

## Production Bundle Exclusion

Mock mode code is **excluded from production builds** when `VITE_MOCK_MODE` is not `'true'`. This is enforced by three mechanisms:

1. **Build-time guard** — All mock imports in `app.tsx` and `main.tsx` use `import.meta.env.VITE_MOCK_MODE === 'true'` with `React.lazy()` + dynamic `import()`. Rspack's DefinePlugin replaces the env var at build time, and the minifier eliminates dead code branches.

2. **`sideEffects: false`** — The `@sportsnot/mock-data` package and web package mock files are marked as side-effect-free (`package.json` and rspack module rule), allowing Rspack to tree-shake unused imports of mock hooks and fixture data.

3. **`resolve.alias`** — When `VITE_MOCK_MODE` is not `'true'`, Rspack aliases `@sportsnot/mock-data` to an empty module (`false`), guaranteeing zero fixture data in the bundle.

### Verification

Run the CI check after building to verify no mock code is in the production bundle:

```bash
nx build web
node scripts/verify-no-mock-in-bundle.mjs
```

This script scans the `packages/web/dist/` JS output for 32+ known mock identifiers (component names, hook names, action types, fixture team names) and exits with code 1 if any are found.

### What the script checks

- Mock component names: `MockDataProvider`, `MockModeBanner`, `SimulationControlPanel`, etc.
- Mock hook names: `useMockDraft`, `useMockLeagues`, `useMockRoster`, etc.
- Reducer action types: `ADVANCE_DAY`, `ADVANCE_ROUND`, `RESET_ALL`, etc.
- Fixture data markers: team names from stub data (`Edmonton Oilers`, `Florida Panthers`, etc.)
- Mock user identifiers: `mock-user-001`
