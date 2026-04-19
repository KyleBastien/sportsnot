# @sportsnot/supabase-db

Supabase database migrations and edge functions.

## Migrations

Migration files use Supabase CLI timestamp naming: `{YYYYMMDDHHmmss}_{name}.sql`.

Migrations auto-deploy to production when CI+E2E pass on main. The CI workflow copies files to `supabase/migrations/` and runs `supabase db push`.

**Adding a new migration:**

1. Generate a timestamp: `date +%Y%m%d%H%M%S`
2. Create `migrations/{timestamp}_{name}.sql`
3. Open a PR and merge to main

**Existing migrations:**

- `20260401000001_initial_schema.sql` — Tables, indexes, functions, triggers, and RLS policies
- `20260401000002_standings_columns.sql` — Standings breakdown columns and refresh function
- `20260401000003_regular_season_stats_cache.sql` — Regular season stats table for Round 1 draft

## Setup

1. Create a Supabase project at [supabase.com](https://supabase.com)
2. Run the migration in the Supabase SQL editor or via the CLI:
   ```bash
   supabase db push
   ```
3. Configure environment variables in `.env`:
   ```
   VITE_SUPABASE_URL=your-project-url
   VITE_SUPABASE_ANON_KEY=your-anon-key
   ```
