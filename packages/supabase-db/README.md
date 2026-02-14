# @sportsnot/supabase-db

Supabase database migrations and edge functions.

## Migrations

- `001_initial_schema.sql` - Tables, indexes, functions, triggers, and RLS policies

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
