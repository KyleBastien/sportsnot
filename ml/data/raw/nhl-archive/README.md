# NHL API historical archive

Committed snapshot of the NHL stats needed for training, so model training and
backtests are fully reproducible from the repo with zero network access — the same
pattern as `../odds-archive/` and `../league-drafts/`. The live NHL API remains the
source for current-season refreshes and anything not snapshotted here (US-003/US-004
build the real typed client; this archive is their historical cache).

## Expected contents (owner's local session provides; see prompt)

One gzipped CSV per season per table, seasons **2007-08 through 2025-26**, regular
season AND playoffs (gameType 2 and 3), plus `PROVENANCE.md` documenting endpoints,
fetch dates, row counts, verification results, and any gaps:

| File pattern | One row per | Required columns (verify names against actual API fields; document mapping) |
|---|---|---|
| `skater-games-<season>.csv.gz` | skater per game | game id, game date, gameType, season, player id, player name, position code, team, opponent, home/road, goals, assists, points, shots, TOI, PP goals/points where available |
| `team-games-<season>.csv.gz` | team per game | game id, date, gameType, season, team, opponent, home/road, goals for, goals against, win/loss, OT/SO flag |
| `game-times-<season>.csv.gz` | game per season | gameId, seasonId, gameTypeId, gameDate, startTimeUTC, venue, venueCity, homeAbbrev, awayAbbrev, neutralSite |
| `bracket-<year>.json` | playoff bracket | raw `/v1/playoff-bracket/{year}` response, verbatim |
| `skater-bios-<season>.csv.gz` | skater per season | player id, name, birth date, position, shoots — for the age feature |

## Source endpoints

- Bulk per-game skater rows: `https://api.nhle.com/stats/rest/en/skater/summary` with
  `isGame=true` (paginated, `limit`/`start`), `cayenneExp=seasonId=<yyyyYYYY> and
  gameTypeId=<2|3>`. If per-game TOI/PP fields are missing from the summary report,
  also capture the `timeonice` and/or `powerplay` reports for the same spans and
  document which report supplies which column.
- Bios: `https://api.nhle.com/stats/rest/en/skater/bios` per season.
- Team results: `https://api.nhle.com/stats/rest/en/team/summary` with `isGame=true`
  per season+gameType (or `api-web.nhle.com/v1/score/{date}` per day as fallback).
- Game times: `https://api-web.nhle.com/v1/club-schedule-season/{teamAbbrev}/{season}`;
  for neutral-site games, `venueCity` is filled from
  `https://api-web.nhle.com/v1/gamecenter/{gameId}/landing` because the season schedule
  payload omits `venueLocation`.
- Brackets: `https://api-web.nhle.com/v1/playoff-bracket/{year}`.

## Verification bar (record results in PROVENANCE.md)

- Per-season game counts sanity: 1,230 regular-season games for 30-team 82-game
  seasons, 1,271 for 31-team seasons, 1,312 for 32-team seasons, 720 for the 2012-13
  lockout season, 1,082 for the 2019-20 COVID-shortened season, and 868 for the
  2020-21 56-game season; playoff games are usually 84–105, with 2020 at 130 because
  the bubble qualifying round is included in `gameTypeId=3`.
- Skater goals/assists must reconcile: sum of skater goals per game ≈ team goals for
  that game (empty-netters etc. make it exact; document any mismatch).
- 2026 playoffs must be present and must reconcile with the app's scoring: e.g.
  Carolina winning the final in 6.
- No imputation ever: missing fields stay empty and get documented.
