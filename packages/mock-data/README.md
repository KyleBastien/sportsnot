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

| File                  | Export              | Description                                      |
| --------------------- | ------------------- | ------------------------------------------------ |
| `teams.ts`            | `teams`             | `NHLTeam[]` — 16 playoff teams                  |
| `players.ts`          | `players`           | `Record<string, NHLPlayer[]>` — rosters by team  |
| `bracket.ts`          | `bracket`           | `NHLPlayoffSeries[]` — bracket/series data       |
| `games-r1.ts`         | `gamesR1`           | `NHLGame[]` — Round 1 games                     |
| `games-r2.ts`         | `gamesR2`           | `NHLGame[]` — Round 2 games                     |
| `games-cf.ts`         | `gamesCf`           | `NHLGame[]` — Conference Finals games            |
| `games-scf.ts`        | `gamesScf`          | `NHLGame[]` — Stanley Cup Final games            |
| `player-game-logs.ts` | `playerGameLogs`    | `Record<number, NHLPlayerStats[]>` — game logs   |

### Notes

- The script is **idempotent** — running it again overwrites existing files.
- Rate limited: max 10 concurrent requests, 100ms delay between batches.
- Requires network access to `api-web.nhle.com`.
- Generated `.ts` files are committed to the repo so other developers don't need to re-download.
