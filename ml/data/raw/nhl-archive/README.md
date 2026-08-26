# NHL API historical archive

Committed snapshot of the NHL stats needed for training, so model training and
backtests are fully reproducible from the repo with zero network access — the same
pattern as `../odds-archive/` and `../league-drafts/`. The live NHL API remains the
source for current-season refreshes and anything not snapshotted here (US-003/US-004
build the real typed client; this archive is their historical cache).

## Expected contents (owner's local session provides; see prompt)

One gzipped CSV per season per table, seasons **2015-16 through 2025-26**, regular
season AND playoffs (gameType 2 and 3), plus `PROVENANCE.md` documenting endpoints,
fetch dates, row counts, verification results, and any gaps:

| File pattern | One row per | Required columns (verify names against actual API fields; document mapping) |
|---|---|---|
| `skater-games-<season>.csv.gz` | skater per game | game id, game date, gameType, season, player id, player name, position code, team, opponent, home/road, goals, assists, points, shots, TOI, PP goals/points where available |
| `team-games-<season>.csv.gz` | team per game | game id, date, gameType, season, team, opponent, home/road, goals for, goals against, win/loss, OT/SO flag |
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
- Brackets: `https://api-web.nhle.com/v1/playoff-bracket/{year}`.

## Verification bar (record results in PROVENANCE.md)

- Per-season game counts sanity: ~1,271–1,353 regular-season games x 2 team-rows;
  playoff games 87–105 per season (2019-20 bubble and 2020-21 are irregular — verify
  against the bracket, not a fixed number).
- Skater goals/assists must reconcile: sum of skater goals per game ≈ team goals for
  that game (empty-netters etc. make it exact; document any mismatch).
- 2026 playoffs must be present and must reconcile with the app's scoring: e.g.
  Carolina winning the final in 6.
- No imputation ever: missing fields stay empty and get documented.
