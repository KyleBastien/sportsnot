# Exporting the 2026 league data from Supabase

## Export status and findings (2026-08-26, in progress)

The export is being done in chunks (the owner's Supabase SQL editor caps results at
100 rows with no way to raise it, so queries page with `ORDER BY league_name,
playoff_round, pick_number ... LIMIT 100 OFFSET 0/100/200`). Raw chunks land in
`incoming/` and are assembled, deduped on (league, round, pick_number), into the final
`app-export-2026__*.csv` files once complete. Facts established so far:

- **Two 2026 leagues exist in the database** and BOTH are being exported, distinguished
  by `league_name`: **The Gemmell Cup** (the historical league: nuttguy, judah18,
  gemmell.levi, bentunigold; IR disabled, 36 picks/round) and **Press Play-offs**
  (nuttguy, Tobi, paul.markhauser, connor.fehr; IR enabled, 44 picks/round). Press
  Play-offs is extra training data for league-agnostic components, not Gemmell
  opponent history.
- **Username mapping** (add to the manager alias file): nuttguy = kyle,
  bentunigold = ben, judah18 = judah, gemmell.levi = levi. Press-only managers keep
  their usernames (tobi, paul.markhauser, connor.fehr).
- **Pick counts** (from `incoming/pick-counts.csv`): each league drafted rounds 1, 2,
  and 3 only — **there is no round-4 draft in the app**, consistent with the league's
  sheet-era tradition of the round-3 draft carrying through the final. Total picks:
  Gemmell 108, Press 132, grand total 240 → query 1 needs 3 chunks.
- **Owner data-quality caveat:** trust the round 3(+4) data; rounds 1–2 in-app data
  may carry artifacts from draft bugs fixed mid-playoffs (see
  `tasks/prd-draft-sorting-and-bugs.md`, `tasks/prd-round-progression-bugs.md`).
  Parsers should validate counts against round 3 and flag—not hard-fail—round 1–2
  anomalies.
- **Query 4 (stats cache) is skipped**: it was optional validation data and the
  pipeline re-derives player stats from the NHL API.

The 2026 season was drafted and scored in the SportsNot app, not the sheets. This
document is the one-time, owner-run procedure to export it into this directory so the
ML pipeline can use 2026 as a fourth training season. The pipeline itself never reads
Supabase — these committed CSVs are the boundary.

Why it's worth it: the app's `draft_picks.pick_number` records the **true pick
sequence**, which the sheet-era seasons lack entirely (rosters were not entered in pick
order). 2026 is therefore the only season the opponent model can learn per-pick
behavior from.

## How to run it

1. Open the Supabase dashboard for the production SportsNot project.
2. Go to **SQL Editor** → **New query**.
3. Paste each query below, one at a time. **Run**, then use the results panel's
   **Export → Download CSV** button.
4. Save with the exact filenames given, drop them into
   `ml/data/raw/league-drafts/`, and commit them to the branch.
5. If your league name isn't unique in the database, tighten the `WHERE l.name` filter
   (or filter by `l.id`) — check with `SELECT id, name, current_round, status FROM
   leagues;` first.

> The queries assume the 2026 league is the only completed league for the 2025–26
> playoffs. Adjust the league filter if you ran test leagues.

## Query 1 — `app-export-2026__draft-picks.csv`

Every pick of every 2026 draft, in true pick order, with resolved names.

```sql
SELECT
  l.name                             AS league_name,
  d.round                            AS playoff_round,
  dp.pick_number,
  u.display_name                     AS manager,
  lm.team_name,
  dp.position,
  dp.player_id,
  ps.player_name,
  dp.team_id,
  ts.team_name                       AS nhl_team_name,
  dp.picked_at
FROM draft_picks dp
JOIN drafts d          ON d.id = dp.draft_id
JOIN leagues l         ON l.id = d.league_id
JOIN league_members lm ON lm.id = dp.league_member_id
JOIN users u           ON u.id = lm.user_id
LEFT JOIN LATERAL (
  SELECT player_name FROM player_stats_cache
  WHERE player_id = dp.player_id AND nhl_season = '20252026'
  ORDER BY playoff_round DESC LIMIT 1
) ps ON TRUE
LEFT JOIN LATERAL (
  SELECT team_name FROM team_stats_cache
  WHERE team_id = dp.team_id AND nhl_season = '20252026'
  ORDER BY playoff_round DESC LIMIT 1
) ts ON TRUE
ORDER BY d.round, dp.pick_number;
```

## Query 2 — `app-export-2026__rosters.csv`

Final per-round rosters with earned points and IR activity (the scoring ground truth).

```sql
SELECT
  l.name                             AS league_name,
  r.round                            AS playoff_round,
  u.display_name                     AS manager,
  lm.team_name,
  r.position,
  r.player_id,
  ps.player_name,
  r.team_id,
  ts.team_name                       AS nhl_team_name,
  r.is_active,
  r.points_earned,
  r.activated_from_ir
FROM rosters r
JOIN league_members lm ON lm.id = r.league_member_id
JOIN leagues l         ON l.id = lm.league_id
JOIN users u           ON u.id = lm.user_id
LEFT JOIN LATERAL (
  SELECT player_name FROM player_stats_cache
  WHERE player_id = r.player_id AND nhl_season = '20252026'
  ORDER BY playoff_round DESC LIMIT 1
) ps ON TRUE
LEFT JOIN LATERAL (
  SELECT team_name FROM team_stats_cache
  WHERE team_id = r.team_id AND nhl_season = '20252026'
  ORDER BY playoff_round DESC LIMIT 1
) ts ON TRUE
ORDER BY r.round, u.display_name, r.position;
```

## Query 3 — `app-export-2026__draft-order.csv`

The stored draft order per round (JSONB array of user ids, expanded to names).

```sql
SELECT
  l.name            AS league_name,
  d.round           AS playoff_round,
  ord.idx           AS order_position,
  u.display_name    AS manager
FROM drafts d
JOIN leagues l ON l.id = d.league_id
CROSS JOIN LATERAL jsonb_array_elements_text(d.draft_order)
  WITH ORDINALITY AS ord(user_id, idx)
JOIN users u ON u.id = ord.user_id::uuid
ORDER BY d.round, ord.idx;
```

## Query 4 — `app-export-2026__stats-cache.csv` (optional but recommended)

The app's per-round player stat lines — useful for validating the pipeline's own
NHL-API ingestion against what the league actually scored.

```sql
SELECT nhl_season, playoff_round, player_id, player_name, team_abbreviation,
       position, goals, assists, games_played, is_injured, last_updated
FROM player_stats_cache
WHERE nhl_season = '20252026'
ORDER BY playoff_round, player_name;
```

## After committing

- Add a short `app-export-2026` section to `SCHEMA.md` (column list above is the
  schema; note any surprises).
- Managers map by `display_name` through the same alias file as the sheets
  (canonical ids: ben, judah, kyle, levi).
- Parsers (Ralph story US-006) pick these files up by the `app-export-*.csv` pattern
  and preserve `pick_number`.

## Backfill — the one missing roster row

The roster export lost one row to a pagination-boundary duplicate: **Press Play-offs,
round 3, nuttguy, D, Jalen Chatfield (8478970)** — specifically its `points_earned`
value. Run this (11 rows, no chunking) and paste the result:

```sql
SELECT l.name AS league_name, r.round AS playoff_round, u.display_name AS manager,
       r.position, r.player_id, r.is_active, r.points_earned, r.activated_from_ir
FROM rosters r
JOIN league_members lm ON lm.id = r.league_member_id
JOIN leagues l ON l.id = lm.league_id
JOIN users u ON u.id = lm.user_id
WHERE l.name = 'Press Play-offs' AND r.round = 3 AND u.display_name = 'nuttguy'
ORDER BY r.position, r.player_id;
```
