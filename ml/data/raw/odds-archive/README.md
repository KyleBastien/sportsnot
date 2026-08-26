# Historical NHL odds archive

Committed source data for historical betting odds — the training/backtest side of the
odds feature. The Odds API free tier only serves **current and upcoming** odds (its
historical endpoints are paid), so past seasons come from free public archives,
downloaded once and committed here, in the same pattern as `../league-drafts/`.

## Expected contents (owner-provided; see APP-side prompt)

- One file per NHL season, ideally the sportsbookreviews-style season odds workbook
  (`nhl-odds-<season>.xlsx` or `.csv`, e.g. `nhl-odds-2023-24.xlsx`), covering at
  least the 10 most recent completed seasons — regular season AND playoffs, since the
  per-game win model trains on both.
- `PROVENANCE.md` recording where each file came from (URL, download date, publisher)
  and any known quirks.

## Typical sportsbookreviews format (verify per file, document deviations in PROVENANCE.md)

Two rows per game (visitor then home): `Date` (MMDD), `Rot`, `VH` (V/H/N),
`Team`, period goals (`1st 2nd 3rd`), `Final`, `Open`/`Close` moneylines (American
odds), puck line, totals. Playoff games are the rows after each season's regular-season
end date — there is no explicit playoff flag, so the parser tags them by date against
the NHL schedule.

## Parser guidance (Ralph story US-005)

- Parse every committed season file into the normalized `odds` table; join to
  `team_games` by date + teams (build a team-name → NHL id mapping; names here are
  city/nickname strings, not ids).
- De-vig Open/Close moneyline pairs into implied probabilities (prefer Close).
- Seasons or games without coverage are explicitly flagged, never silently imputed.
- These archives carry game moneylines only (no series prices) — series-price features
  exist only where The Odds API provides them live.
