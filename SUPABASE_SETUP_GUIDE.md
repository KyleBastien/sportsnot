# SportsNot — Supabase Setup Guide for the 2026 NHL Playoffs

This is a step-by-step guide to set up a production Supabase project so SportsNot is ready for the 2026 NHL Playoff season. Follow every section in order. Each section explains **what** to do, **why**, and **what NOT to do** so you don't get tripped up.

---

## Table of Contents

1. [Create Your Supabase Project](#1-create-your-supabase-project)
2. [Run the Database Migrations](#2-run-the-database-migrations)
3. [Verify Tables, Functions & Triggers](#3-verify-tables-functions--triggers)
4. [Enable Realtime](#4-enable-realtime)
5. [Configure Authentication](#5-configure-authentication)
6. [Configure Auth Email Templates](#6-configure-auth-email-templates)
7. [Set Up the Edge Function (sync-nhl-stats)](#7-set-up-the-edge-function-sync-nhl-stats)
8. [Schedule the Stats Sync Cron Job](#8-schedule-the-stats-sync-cron-job)
9. [Connect the App (.env Configuration)](#9-connect-the-app-env-configuration)
10. [Test the Full Flow](#10-test-the-full-flow)
11. [Production Hardening Checklist](#11-production-hardening-checklist)
12. [Common Mistakes to Avoid](#12-common-mistakes-to-avoid)

---

## 1. Create Your Supabase Project

### Steps

1. Go to [https://supabase.com/dashboard](https://supabase.com/dashboard) and sign in (or create an account).
2. Click **"New Project"**.
3. Fill in the form:
   - **Organization:** Pick your org or create one (e.g., `sportsnot`).
   - **Project name:** `sportsnot-2026` (or whatever you prefer).
   - **Database password:** Use a strong, random password. **Save this somewhere safe** (e.g., password manager). You'll need it if you ever connect via direct Postgres, but the app itself uses the anon key, not this password.
   - **Region:** Pick the region closest to your users. For North American NHL fans, `us-east-1` (N. Virginia) or `ca-central-1` (Canada) are good choices. **Do NOT change this later** — Supabase doesn't support region migration.
   - **Pricing plan:** The free tier works for testing. For a real playoff season with multiple leagues, consider the **Pro plan** ($25/mo) for better connection limits, daily backups, and no pause-after-inactivity.
4. Click **"Create new project"** and wait for provisioning (~2 minutes).

### After Creation — Grab Your Keys

Once the project is ready, go to **Settings → API** and note:

| Value | Where to find it | What it's for |
|---|---|---|
| **Project URL** | `Settings → API → Project URL` | `VITE_SUPABASE_URL` in your `.env` |
| **anon / public key** | `Settings → API → Project API keys → anon public` | `VITE_SUPABASE_ANON_KEY` in your `.env` |
| **service_role key** | `Settings → API → Project API keys → service_role secret` | Used by the edge function only (server-side) |

> ⚠️ **NEVER** put the `service_role` key in your `.env` file or expose it to the browser. It bypasses Row Level Security. The edge function accesses it automatically through `Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')` — Supabase injects it for you at runtime.

---

## 2. Run the Database Migrations

SportsNot has four migration files that must be run **in order**:

1. `packages/supabase-db/migrations/001_initial_schema.sql` — Creates all tables, indexes, functions, triggers, and RLS policies.
2. `packages/supabase-db/migrations/002_standings_columns.sql` — Adds standings breakdown columns and the `refresh_league_standings` function.
3. `packages/supabase-db/migrations/003_regular_season_stats_cache.sql` — Creates the `regular_season_stats_cache` table for Round 1 draft player rankings.
4. `packages/supabase-db/migrations/004_fix_league_members_rls_recursion.sql` — Fixes infinite recursion in `league_members` RLS policies by introducing a `SECURITY DEFINER` helper function.

### Option A: Supabase Dashboard SQL Editor (Recommended for first-time setup)

1. Go to your Supabase project → **SQL Editor** (left sidebar).
2. Click **"New query"**.
3. Open `packages/supabase-db/migrations/001_initial_schema.sql` from your local repo, copy the **entire** contents, and paste it into the SQL Editor.
4. Click **"Run"** (or press Ctrl+Enter / Cmd+Enter).
5. You should see `Success. No rows returned.` This is correct — DDL statements don't return rows.
6. Repeat for `002_standings_columns.sql`, `003_regular_season_stats_cache.sql`, and `004_fix_league_members_rls_recursion.sql` — each in a new query tab, one at a time.

> ⚠️ **DO NOT** run all files in a single query. Run them **one at a time, in order**. Each migration depends on the previous ones.

> ⚠️ **DO NOT** run a migration file more than once. If you accidentally re-run 001, you'll get errors like `relation "users" already exists`. If this happens, the tables are already there — just move on. The `CREATE OR REPLACE FUNCTION` statements are idempotent, but `CREATE TABLE` is not.

### Option B: Supabase CLI (if you have it installed)

If you have the Supabase CLI installed and linked to your project:

```bash
supabase link --project-ref your-project-ref
supabase db push
```

However, note that `supabase db push` expects migrations in the standard Supabase directory structure (`supabase/migrations/`). Since SportsNot keeps migrations in `packages/supabase-db/migrations/`, you may need to copy/symlink them or just use Option A.

### What the Migrations Create

**Tables (9 total):**

| Table | Purpose |
|---|---|
| `users` | User profiles (extends Supabase `auth.users`) |
| `leagues` | Fantasy hockey leagues |
| `league_members` | Users joined to leagues (with points & standings) |
| `drafts` | One draft per league per playoff round |
| `draft_picks` | Individual pick records within a draft |
| `rosters` | Active roster slots per member per round |
| `player_stats_cache` | Cached NHL player stats (goals, assists, GP) |
| `team_stats_cache` | Cached NHL team stats (wins, shutouts) |
| `regular_season_stats_cache` | Cached regular season stats for Round 1 draft rankings |

**Functions (7 total):**
- `handle_updated_at()` — Auto-updates `updated_at` timestamps
- `handle_new_user()` — Auto-creates a user profile row when someone signs up via Supabase Auth
- `calculate_member_points()` — Sums points for a member's active roster
- `validate_roster_composition()` — Ensures roster limits (5F, 3D, 1G)
- `activate_ir_player()` — Handles IR activation with position validation
- `refresh_league_standings()` — Aggregates roster points into league member standings (from migration 002)
- `get_user_league_ids()` — `SECURITY DEFINER` helper that returns league IDs for the current user, used by RLS policies to avoid infinite recursion (from migration 004)

**Triggers (3 total):**
- `set_updated_at_users` — On `users` table updates
- `set_updated_at_leagues` — On `leagues` table updates
- `on_auth_user_created` — On `auth.users` insert → creates `public.users` row

---

## 3. Verify Tables, Functions & Triggers

After running all four migrations, verify everything is in place.

### Check Tables

Go to **Table Editor** (left sidebar). You should see all 9 tables listed:
- `users`
- `leagues`
- `league_members`
- `drafts`
- `draft_picks`
- `rosters`
- `player_stats_cache`
- `team_stats_cache`
- `regular_season_stats_cache`

Click into `league_members` and verify it has columns `player_points`, `goalie_points`, and `round_points` (added by migration 002).

### Check Functions

Go to **Database → Functions** (left sidebar). You should see:
- `handle_updated_at`
- `handle_new_user`
- `calculate_member_points`
- `validate_roster_composition`
- `activate_ir_player`
- `refresh_league_standings`
- `get_user_league_ids`

### Check Triggers

Go to **SQL Editor** and run:

```sql
SELECT trigger_name, event_object_table, action_timing, event_manipulation
FROM information_schema.triggers
WHERE trigger_schema = 'public'
ORDER BY event_object_table;
```

You should see:
| trigger_name | table | timing | event |
|---|---|---|---|
| `set_updated_at_leagues` | `leagues` | BEFORE | UPDATE |
| `set_updated_at_users` | `users` | BEFORE | UPDATE |

And for the auth trigger, run:

```sql
SELECT trigger_name, event_object_table
FROM information_schema.triggers
WHERE trigger_name = 'on_auth_user_created';
```

You should see `on_auth_user_created` on the `users` table in the `auth` schema.

### Check RLS Policies

Go to **Authentication → Policies** (or **Table Editor → select a table → RLS Policies tab**). Every table should have RLS **enabled** (the toggle should be ON). Check that each table has its policies:

| Table | Expected Policies |
|---|---|
| `users` | "Users can read own profile", "Users can update own profile", "Users can read other users in same league" |
| `leagues` | "League members can read their leagues", "Anyone can read league by invite code", "Authenticated users can create leagues", "Commissioners can update their leagues" |
| `league_members` | "Members can read league members", "Users can join leagues", "Users can leave leagues" |
| `drafts` | "League members can read drafts", "Commissioners can manage drafts" |
| `draft_picks` | "League members can read draft picks", "Members can insert own draft picks" |
| `rosters` | "League members can read rosters", "Members can manage own rosters" |
| `player_stats_cache` | "Authenticated users can read player stats" |
| `team_stats_cache` | "Authenticated users can read team stats" |

> ⚠️ **DO NOT** disable RLS on any table "just to test things." This is the #1 mistake people make. RLS is critical — without it, any user can read/write any data. If something isn't working, the issue is almost always a missing policy, not RLS itself.

---

## 4. Enable Realtime

The migration already adds tables to the `supabase_realtime` publication, but you need to **verify Realtime is enabled** in the dashboard.

1. Go to **Database → Publications** (left sidebar, under the **Database** section).
2. You should see a publication called **`supabase_realtime`**. Click on it.
3. You'll see a list of your tables with toggles. Verify these tables are toggled **ON**:
   - `drafts`
   - `draft_picks`
   - `rosters`
   - `league_members`

If any are missing, you can add them via the dashboard or run in SQL Editor:

```sql
ALTER PUBLICATION supabase_realtime ADD TABLE public.drafts;
ALTER PUBLICATION supabase_realtime ADD TABLE public.draft_picks;
ALTER PUBLICATION supabase_realtime ADD TABLE public.rosters;
ALTER PUBLICATION supabase_realtime ADD TABLE public.league_members;
```

### Why Realtime Matters

SportsNot uses Supabase Realtime subscriptions for the **live draft experience**. When one user makes a pick, all other league members see it instantly via `postgres_changes` events (see `useDraft.ts`). Without Realtime enabled for these tables, drafts will only update on the 5-second polling interval, which creates a laggy UX.

> ⚠️ **DO NOT** enable Realtime for `player_stats_cache` or `team_stats_cache`. These are updated by the edge function on a schedule and are read via normal queries. Enabling Realtime for them would waste connection resources.

---

## 5. Configure Authentication

SportsNot uses **Magic Link (email OTP)** authentication — no passwords. Users enter their email, receive a link, click it, and they're signed in.

### Step 5a: Enable Email Auth Provider

1. Go to **Authentication → Providers** (left sidebar).
2. **Email** should already be enabled by default. Click on it to expand.
3. Verify these settings:
   - **Enable Email provider:** ✅ ON
   - **Confirm email:** ✅ ON (users must click the magic link to complete sign-in — this is the critical one)

> ⚠️ **DO NOT** enable password-based sign-in alongside magic link unless you specifically want it. SportsNot's auth flow is built entirely around `signInWithOtp()` (magic link). Adding password auth creates a confusing UX with two sign-in paths.

### Step 5b: Disable Unused Auth Providers

Go through the provider list and make sure everything else is **disabled** unless you specifically want social login:
- Google: OFF (unless you plan to add it)
- GitHub: OFF
- Apple: OFF
- Discord: OFF
- etc.

### Step 5c: Configure Site URL & Redirect URLs

This is **critical** for magic links to work. The magic link email contains a redirect URL that must match your app's domain.

1. Go to **Authentication → URL Configuration**.
2. Set:
   - **Site URL:** Your app's production URL (e.g., `https://sportsnot.app`) or for testing: `http://localhost:4200`
   - **Redirect URLs:** Add all allowed callback URLs. You need **at least**:
     - `http://localhost:4200/auth/callback` (local development)
     - `https://your-production-domain.com/auth/callback` (production)
     - Any preview/staging URLs if applicable

The magic link flow works like this:
1. User enters email on the login page
2. SportsNot calls `supabase.auth.signInWithOtp({ email, options: { emailRedirectTo: '${window.location.origin}/auth/callback' } })`
3. Supabase sends an email with a link pointing to your Site URL + `/auth/callback`
4. User clicks link → lands on `/auth/callback` → app picks up the session tokens from the URL hash → redirects to dashboard

> ⚠️ **The #1 reason magic links don't work:** The redirect URL in the email doesn't match any entry in your Redirect URLs allow-list. If the link opens to a blank page or Supabase error, this is almost certainly the issue.

> ⚠️ **DO NOT** leave Site URL as `http://localhost:3000` (the Supabase default) if your dev server runs on port 4200. SportsNot uses port 4200.

### Step 5d: Configure Rate Limits

Go to **Authentication → Rate Limits** and set reasonable values:

- **Email rate limit:** 4 emails per 60 seconds (default is fine)
- **SMS rate limit:** N/A (not used)
- **Token refresh rate limit:** Leave as default

For the playoffs, you may have bursts of users signing up. If you're on the Pro plan, these limits are higher by default.

---

## 6. Configure Auth Email Templates

Supabase sends default emails for magic links that look generic. Customize them for a better experience.

1. Go to **Authentication → Email Templates**.
2. Click on **"Magic Link"**.
3. Customize the template. Here's a recommended template:

**Subject:**
```
Your SportsNot Login Link 🏒
```

**Body (HTML):**
```html
<div style="text-align: center; margin-bottom: 24px;">
  <img src="https://www.sportsnot.net/sportsnot-logo.f136dd23d873e889.png" alt="SportsNot" width="120" style="display: inline-block;" />
</div>
<h2 style="text-align: center;">Welcome to SportsNot!</h2>
<p>Click the link below to sign in to your NHL Playoff Fantasy Hockey account:</p>
<p><a href="{{ .ConfirmationURL }}">Sign In to SportsNot</a></p>
<p>This link expires in 1 hour. If you didn't request this, you can safely ignore this email.</p>
<p>Good luck in the 2026 Playoffs! 🏆</p>
```

> **Logo URL:** The logo is hosted at `https://www.sportsnot.net/sportsnot-logo.f136dd23d873e889.png` and is already set in the template above.

4. Click **"Save"**.

> ⚠️ **DO NOT** remove `{{ .ConfirmationURL }}` from the template. This is the magic link itself. Without it, users can't sign in.

> ⚠️ **DO NOT** modify the "Confirm signup" template to remove the confirmation link if you have email confirmation enabled. The `on_auth_user_created` trigger fires when the user is created in `auth.users`, which happens after email confirmation.

### Custom SMTP (Recommended for Production)

Supabase's built-in email sending only delivers to **project team members' email addresses** and has a rate limit of **2 emails per hour**. For a real playoff season, you must set up custom SMTP. We recommend **Resend** — it's the easiest to integrate with Supabase.

#### Step-by-Step: Setting Up Resend as Your SMTP Provider

**1. Create a Resend account**
   - Go to [https://resend.com](https://resend.com) and sign up.
   - Free tier: 100 emails/day, 3,000 emails/month — more than enough for SportsNot.

**2. Verify your domain**
   - Go to [https://resend.com/domains](https://resend.com/domains) and click **"Add Domain"**.
   - Enter your domain (e.g., `sportsnot.net`).
   - Resend will give you **DNS records** to add (MX, TXT for SPF, and CNAME for DKIM). Add these records at your domain registrar (e.g., Cloudflare, Namecheap, GoDaddy).
   - Wait for verification (usually a few minutes, sometimes up to 24 hours).
   - **Why this matters:** Without domain verification, emails may go to spam or not send at all. Supabase requires the sender email to match a verified domain.

> ⚠️ **DO NOT** skip domain verification and use Resend's `onboarding@resend.dev` test address. It will not work with Supabase in production — your users' magic link emails will be rejected or filtered as spam.

**3. Create an API key**
   - Go to [https://resend.com/api-keys](https://resend.com/api-keys).
   - Click **"Create API Key"**.
   - Name it something like `supabase-sportsnot`.
   - Permission: **Sending access** is sufficient.
   - Copy the key immediately — you won't see it again.

**4. Configure SMTP in Supabase**
   - In your Supabase dashboard, go to **Authentication** (left sidebar).
   - Click **Email** under the **Notifications** section.
   - Click **SMTP Settings** and toggle it **ON**.
   - Fill in the following values exactly:

   | Setting | Value |
   |---|---|
   | **Sender email** | `noreply@sportsnot.net` (must match your verified Resend domain) |
   | **Sender name** | `SportsNot` |
   | **Host** | `smtp.resend.com` |
   | **Port** | `465` |
   | **Username** | `resend` (literally the word "resend" — not your email) |
   | **Password** | Your Resend API key (the `re_` prefixed key you copied) |

   - Click **Save**.

> ⚠️ **Common mistakes with Resend setup:**
> - **Wrong username:** The username is literally `resend`, not your Resend account email.
> - **Wrong port:** Use `465` (SSL). Port `587` (STARTTLS) also works but `465` is what Resend recommends.
> - **Sender email doesn't match verified domain:** If your domain is `sportsnot.net`, the sender must be `something@sportsnot.net`. Using `noreply@gmail.com` will fail.
> - **API key copied wrong:** The key starts with `re_`. Make sure there are no extra spaces.

**5. Test it**
   - After saving, go to your app and try signing in with a real email address (not just project team members — that restriction is now lifted).
   - Check that the email arrives from `noreply@sportsnot.net` (or whatever you set) and not from `noreply@mail.app.supabase.io`.
   - Check spam/junk if it doesn't appear within a minute.
   - You can also monitor delivery in the Resend dashboard at [https://resend.com/emails](https://resend.com/emails).

**6. Adjust rate limits in Supabase**
   - After configuring custom SMTP, Supabase defaults to 30 emails/hour.
   - Go to **Authentication → Rate Limits** and increase if needed for your expected user count.
   - Resend's free tier allows 100/day, so set your Supabase rate limit to stay within that.

#### Alternative SMTP Providers

If you prefer not to use Resend, these also work with the same Supabase SMTP settings page:

| Provider | Host | Port | Username | Password | Free Tier |
|---|---|---|---|---|---|
| **Postmark** | `smtp.postmarkapp.com` | `587` | Your Postmark Server API Token | Same token | 100 test emails |
| **SendGrid** | `smtp.sendgrid.net` | `587` | `apikey` (literal) | Your SendGrid API key | 100 emails/day |
| **AWS SES** | `email-smtp.us-east-1.amazonaws.com` | `587` | SMTP credential username | SMTP credential password | 200 emails/day (in sandbox) |

> ⚠️ **Without custom SMTP, Supabase will only send emails to project team members and caps at 2/hour.** This is the #1 issue people hit when going live. Set up SMTP before inviting any real users.

---

## 7. Set Up the Edge Function (sync-nhl-stats)

The `sync-nhl-stats` edge function fetches live NHL playoff stats and updates the cache tables. It's located at `packages/supabase-db/functions/sync-nhl-stats/index.ts`.

### What it Does

1. Reads all active roster entries for a given playoff round
2. Fetches player game logs from the NHL API (`api-web.nhle.com`)
3. Fetches team scores from the NHL API
4. Upserts stats into `player_stats_cache` and `team_stats_cache`
5. Calculates fantasy points using the scoring rules:
   - **Goal:** 1 point
   - **Assist:** 1 point
   - **Team Win:** 2 points (goalie slots)
   - **Shutout:** 4 points (goalie slots — replaces the 2-point win, so a shutout = 4, not 6)
6. Updates `rosters.points_earned` for each slot
7. Calls `refresh_league_standings()` to aggregate into `league_members`

### Deploy via Supabase CLI

You need the Supabase CLI installed. If you don't have it:

```bash
# macOS
brew install supabase/tap/supabase

# Windows (scoop)
scoop bucket add supabase https://github.com/supabase/scoop-bucket.git
scoop install supabase

# npm (any platform)
npm install -g supabase
```

Then deploy:

```bash
# Link to your project (only needed once)
supabase login
supabase link --project-ref your-project-ref

# Deploy the function
# Run from the repo root — the function source is at packages/supabase-db/functions/sync-nhl-stats/index.ts
supabase functions deploy sync-nhl-stats --project-ref your-project-ref
```

> ⚠️ **Important:** Supabase expects edge functions in a specific directory structure. The `supabase functions deploy` command looks for `supabase/functions/<function-name>/index.ts` by default. Since SportsNot keeps functions in `packages/supabase-db/functions/`, you may need to either:
>
> **Option A (recommended):** Create a symlink so Supabase CLI finds the function without duplicating files. Run these commands from the **repo root** (`sportsnot/`):
> ```bash
> mkdir -p supabase/functions
> # Windows PowerShell (from repo root — requires Administrator or Developer Mode)
> New-Item -ItemType SymbolicLink -Path supabase\functions\sync-nhl-stats -Target (Resolve-Path packages\supabase-db\functions\sync-nhl-stats).Path
> # macOS/Linux (from repo root)
> ln -s ../../packages/supabase-db/functions/sync-nhl-stats supabase/functions/sync-nhl-stats
> supabase functions deploy sync-nhl-stats
> ```
> The symlink keeps a single source of truth — edits to `packages/supabase-db/functions/sync-nhl-stats/index.ts` are automatically picked up by the CLI.
>
> **Option B:** Use the `--legacy-bundle` or specify the source directory if your Supabase CLI version supports it.

### Verify Deployment

1. Go to **Edge Functions** in the Supabase dashboard (left sidebar).
2. You should see `sync-nhl-stats` listed with status **Active**.
3. Note the function URL — it will be something like:
   `https://<your-project-ref>.supabase.co/functions/v1/sync-nhl-stats`

### Test It Manually

In the dashboard under **Edge Functions → sync-nhl-stats**, click **"Invoke"** or use curl:

```bash
curl -X POST https://<your-project-ref>.supabase.co/functions/v1/sync-nhl-stats \
  -H "Authorization: Bearer <your-service-role-key>" \
  -H "Content-Type: application/json" \
  -d '{"season": "20252026", "playoff_round": 1}'
```

If no rosters exist yet, you'll get: `{"message": "No active rosters to sync"}` — this is correct.

> ⚠️ **DO NOT** call the edge function with the `anon` key. It needs the `service_role` key because it reads/writes across all users' data. The function accesses this automatically via `Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')`.

### RLS Note for the Edge Function

The edge function uses `createClient` with the `service_role` key, which **bypasses RLS**. This is intentional — it needs to read all rosters and update all stats regardless of which user owns them. The `player_stats_cache` and `team_stats_cache` tables only have SELECT policies for authenticated users, not INSERT/UPDATE — so the edge function is the only thing that writes to them.

> ⚠️ **DO NOT** add INSERT/UPDATE RLS policies to `player_stats_cache` or `team_stats_cache` for the `anon` role. Only the edge function (via `service_role`) should write to these tables.

---

## 8. Schedule the Stats Sync Cron Job

During the playoffs, you want stats to update automatically. Set up a cron job to invoke the edge function on a schedule.

### Option A: Supabase Cron (pg_cron) — Recommended

Supabase includes `pg_cron` for scheduling. Go to **SQL Editor** and run:

```sql
-- Enable the pg_cron and pg_net extensions if not already enabled
CREATE EXTENSION IF NOT EXISTS pg_cron;
CREATE EXTENSION IF NOT EXISTS pg_net;

-- Off-season: schedule a weekly health-check sync (every Sunday at midnight UTC)
-- This keeps the function warm and verifies the pipeline works before playoffs start.
-- When the playoffs begin, update to every 15 minutes (see below).
SELECT cron.schedule(
  'sync-nhl-stats',
  '0 0 * * 0',  -- Every Sunday at midnight UTC
  $$
  SELECT net.http_post(
    url := 'https://<your-project-ref>.supabase.co/functions/v1/sync-nhl-stats',
    headers := jsonb_build_object(
      'Content-Type', 'application/json',
      'Authorization', 'Bearer ' || current_setting('app.settings.service_role_key', true)
    ),
    body := jsonb_build_object(
      'season', '20252026',
      'playoff_round', 1
    )
  );
  $$
);
```

> **When the playoffs start,** switch to every 15 minutes:
> ```sql
> SELECT cron.unschedule('sync-nhl-stats');
> SELECT cron.schedule(
>   'sync-nhl-stats',
>   '*/15 * * * *',  -- Every 15 minutes
>   $$
>   SELECT net.http_post(
>     url := 'https://<your-project-ref>.supabase.co/functions/v1/sync-nhl-stats',
>     headers := jsonb_build_object(
>       'Content-Type', 'application/json',
>       'Authorization', 'Bearer ' || current_setting('app.settings.service_role_key', true)
>     ),
>     body := jsonb_build_object(
>       'season', '20252026',
>       'playoff_round', 1
>     )
>   );
>   $$
> );
> ```

> **Note:** You'll need to update the `playoff_round` value in the cron body as the playoffs progress (1 → 2 → 3 → 4). You can also pass `round_start_date` and `round_end_date` to filter stats to a specific round's date range.

To update the cron for a new round:

```sql
-- Unschedule the old cron
SELECT cron.unschedule('sync-nhl-stats');

-- Reschedule for Round 2
SELECT cron.schedule(
  'sync-nhl-stats',
  '*/15 * * * *',
  $$
  SELECT net.http_post(
    url := 'https://<your-project-ref>.supabase.co/functions/v1/sync-nhl-stats',
    headers := jsonb_build_object(
      'Content-Type', 'application/json',
      'Authorization', 'Bearer ' || current_setting('app.settings.service_role_key', true)
    ),
    body := jsonb_build_object(
      'season', '20252026',
      'playoff_round', 2
    )
  );
  $$
);
```

### Option B: External Cron (if pg_cron doesn't work for you)

Use any external cron service (GitHub Actions, cron-job.org, AWS EventBridge, etc.):

```bash
# Example: curl invoked by an external cron every 15 minutes
curl -X POST https://<your-project-ref>.supabase.co/functions/v1/sync-nhl-stats \
  -H "Authorization: Bearer <service-role-key>" \
  -H "Content-Type: application/json" \
  -d '{"season": "20252026", "playoff_round": 1}'
```

### Frequency Recommendations

| Period | Frequency | Why |
|---|---|---|
| During active games (7 PM - 1 AM ET) | Every 10-15 minutes | Players are scoring; users want fresh stats |
| Between games / off-days | Every 1-2 hours or manual | Nothing is changing; save API calls |
| Off-season | Disabled | No data to sync |

> ⚠️ **DO NOT** set the cron to run every minute. The NHL API isn't real-time anyway (there's a delay), and you'll burn through edge function invocations and potentially get rate-limited by the NHL API.

---

## 9. Connect the App (.env & GitHub Actions Configuration)

Now connect SportsNot to your Supabase project — both for local development and for the deployed production site.

### 9a. Local Development — Edit `.env` in the Repo Root

Open the `.env` file in the root of the repository and update:

```env
# Supabase Configuration
VITE_SUPABASE_URL=https://<your-project-ref>.supabase.co
VITE_SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...your-anon-key...

# Mock Mode — set to 'false' for real Supabase
VITE_MOCK_MODE=false
```

### 9b. Production Deployment — Set GitHub Actions Secrets

The CI workflow (`.github/workflows/ci.yml`) already reads Supabase credentials from **GitHub Actions secrets** during the production build. You need to add them to your repo:

1. Make sure you have the [GitHub CLI](https://cli.github.com/) installed and authenticated (`gh auth login`).
2. Run these commands from the repo root:

   ```bash
   gh secret set VITE_SUPABASE_URL --body "https://<your-project-ref>.supabase.co"
   gh secret set VITE_SUPABASE_ANON_KEY --body "your-anon-key-here"
   ```

3. Verify the secrets were added:

   ```bash
   gh secret list
   ```

   You should see `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` listed.

4. That's it. The next push to `main` (or manual workflow dispatch) will build and deploy with your real Supabase credentials.

> **How it works:** The CI workflow builds the app twice:
> - **Production build** — uses `VITE_MOCK_MODE: 'false'` and injects your Supabase secrets. This becomes the main site at `sportsnot.net`.
> - **Demo build** — uses `VITE_MOCK_MODE: 'true'` and ignores Supabase entirely. This becomes the demo at `sportsnot.net/demo/`.
>
> You do NOT need to add `VITE_MOCK_MODE` as a secret — the workflow hardcodes it to `'false'` for production and `'true'` for demo.

> ⚠️ **DO NOT** add secrets via a `.env` file committed to git. GitHub Actions secrets are the correct way — they're encrypted and never exposed in logs.

> ⚠️ **DO NOT** put the `service_role` key in GitHub Actions secrets. The deployed app never needs it — only the edge function does (and Supabase injects it automatically at runtime).

### Where to Find the Values

- **VITE_SUPABASE_URL:** Dashboard → Settings → API → Project URL
- **VITE_SUPABASE_ANON_KEY:** Dashboard → Settings → API → Project API keys → `anon` `public`

### Important Notes

- Set `VITE_MOCK_MODE=false` in your local `.env` to use real Supabase instead of the in-memory mock data.
- The `VITE_` prefix is required — it's how Rspack (the bundler) exposes env vars to the browser. Without the prefix, the values won't be available at runtime.

> ⚠️ **DO NOT** put the `service_role` key in `.env`. It's only needed by edge functions (which get it automatically) and the cron schedule (which is configured in the database, not the app).

> ⚠️ **DO NOT** commit `.env` to git. It's already in `.gitignore`. If you're sharing the project, use `.env.example` as the template (it already exists in the repo).

### Verify the Connection

```bash
# Start the dev server
yarn nx serve @sportsnot/web
```

Open `http://localhost:4200`. You should see the login page. Enter an email — if Supabase is configured correctly, you'll get a magic link email (or see "Check your email" confirmation UI).

---

## 10. Test the Full Flow

Before the playoffs start, walk through the entire user journey to make sure everything works:

### Test 1: Authentication

1. Open the app → see login page
2. Enter a real email address you can check
3. Receive magic link email
4. Click the link → redirected to `/auth/callback` → then to the dashboard
5. Verify your profile appears in the `users` table (Table Editor → `users`)

### Test 2: League Creation

1. Create a new league (give it a name, set max participants)
2. Verify the league appears in the `leagues` table
3. Verify you auto-joined as a league member in `league_members`
4. Note the invite code

### Test 3: Joining a League

1. Open the app in an incognito window / different browser
2. Sign up with a different email
3. Join the league using the invite code
4. Verify the new member appears in `league_members`

### Test 4: Draft

1. As the commissioner, start a draft
2. Make picks from both accounts
3. Verify `drafts`, `draft_picks`, and `rosters` tables are populated
4. Verify Realtime works — picks made in one browser appear instantly in the other

### Test 5: Stats Sync

1. After making picks, manually invoke the edge function:
   ```bash
   curl -X POST https://<your-project-ref>.supabase.co/functions/v1/sync-nhl-stats \
     -H "Authorization: Bearer <service-role-key>" \
     -H "Content-Type: application/json" \
     -d '{"season": "20252026", "playoff_round": 1}'
   ```
2. Check `player_stats_cache` and `team_stats_cache` for data
3. Check `rosters.points_earned` is updated
4. Check `league_members.total_points`, `player_points`, `goalie_points` are updated

> **Note:** If the 2026 playoffs haven't started yet, the NHL API will return empty game logs. This is expected. The sync will work correctly once real playoff games begin.

---

## 11. Production Hardening Checklist

Before the first puck drop, go through this checklist:

### Database

- [ ] All 8 tables created and verified
- [ ] All 6 functions exist
- [ ] All 3 triggers active
- [ ] RLS enabled on ALL tables (no exceptions)
- [ ] All RLS policies created and verified
- [ ] Realtime enabled for `drafts`, `draft_picks`, `rosters`, `league_members`
- [ ] Realtime NOT enabled for `player_stats_cache`, `team_stats_cache`

### Authentication

- [ ] Email provider enabled with magic link
- [ ] Site URL set to production domain
- [ ] Redirect URLs include both localhost:4200 AND production domain `/auth/callback`
- [ ] Custom SMTP configured (strongly recommended for production)
- [ ] Email templates customized
- [ ] Unused auth providers disabled

### Edge Function

- [ ] `sync-nhl-stats` deployed and showing Active status
- [ ] Manual invocation returns expected response
- [ ] Cron job scheduled for playoff game times

### App Configuration

- [ ] `.env` has correct `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY`
- [ ] `VITE_MOCK_MODE=false` for production
- [ ] `.env` is NOT committed to git

### Backups & Monitoring

- [ ] Database backups enabled (automatic on Pro plan)
- [ ] Monitor edge function logs: Dashboard → Edge Functions → sync-nhl-stats → Logs
- [ ] Monitor auth logs: Dashboard → Authentication → Logs
- [ ] Monitor database usage: Dashboard → Reports

---

## 12. Common Mistakes to Avoid

| Mistake | Why It's Bad | Fix |
|---|---|---|
| Running migrations out of order | 002 depends on tables from 001 | Always run 001 first, then 002, 003, 004 in order |
| Running migrations twice | `CREATE TABLE` fails if table exists | If it errors, tables already exist — just move on |
| Disabling RLS "to test" | Any user can read/modify all data | Never disable. Fix policies instead |
| Putting `service_role` key in `.env` | Exposes it to the browser; bypasses all RLS | Only use in edge functions and server-side cron |
| Wrong Site URL in Auth settings | Magic links redirect to wrong place; users can't log in | Must match your app's actual domain + port |
| Missing `/auth/callback` in Redirect URLs | Supabase rejects the redirect; auth fails silently | Add both localhost and production callback URLs |
| Forgetting to set `VITE_MOCK_MODE=false` | App uses in-memory mock data instead of Supabase | Set to `false` in `.env` for production |
| Leaving `VITE_SUPABASE_URL` as `http://localhost:54321` | App tries to connect to local Supabase (which doesn't exist) | Set to your real project URL |
| Setting cron to every minute | Burns edge function invocations, may hit NHL rate limits | Every 10-15 minutes during games is plenty |
| Forgetting to update `playoff_round` in cron | Stats sync for wrong round; points don't update | Update cron body when each round starts |
| Not setting up custom SMTP | Magic link emails hit rate limits or go to spam | Use Resend, Postmark, SendGrid, or AWS SES |
| Adding INSERT policies to stats cache tables | Users could write fake stats | Only the edge function (service_role) writes to these |
| Enabling Realtime on stats cache tables | Wastes database connections for infrequently-updated data | Only enable Realtime for draft/roster tables |
| Not setting up `regular_season_stats_cache` | Round 1 draft can't show regular season stats for player rankings | Run migration 003 and deploy `sync-regular-season-stats` edge function |
| "Infinite recursion detected in policy for relation 'league_members'" | Self-referencing RLS policy causes Postgres to loop infinitely | Run migration 004 to fix the policy with a `SECURITY DEFINER` helper function |

### Setting Up `regular_season_stats_cache` (Required for Round 1 Draft)

The `useRegularSeasonPlayers` hook queries a `regular_season_stats_cache` table to show regular season performance (goals, assists, points) next to each player during the Round 1 draft. This helps your league members make informed picks.

#### Step 1: Run Migration 003

A new migration file exists at `packages/supabase-db/migrations/003_regular_season_stats_cache.sql`. Run it the same way you ran the others — paste the contents into the **SQL Editor** and click **Run**.

This creates the table with:
- `player_id`, `nhl_season` — unique key per player per season
- `player_name`, `team_abbreviation`, `position` — display fields
- `goals`, `assists`, `points`, `games_played` — aggregated regular season totals
- RLS policy: authenticated users can read, only `service_role` (edge function) can write

#### Step 2: Deploy the `sync-regular-season-stats` Edge Function

A new edge function exists at `packages/supabase-db/functions/sync-regular-season-stats/index.ts`. Deploy it the same way you deployed `sync-nhl-stats`:

```bash
# Create symlink (from repo root)
# Windows PowerShell
New-Item -ItemType SymbolicLink -Path supabase\functions\sync-regular-season-stats -Target (Resolve-Path packages\supabase-db\functions\sync-regular-season-stats).Path
# macOS/Linux
ln -s ../../packages/supabase-db/functions/sync-regular-season-stats supabase/functions/sync-regular-season-stats

# Deploy
supabase functions deploy sync-regular-season-stats
```

#### What the Function Does

1. Determines which teams to sync — either from the `team_abbreviations` you provide, or by fetching the playoff bracket from the NHL API
2. Fetches the full roster for each team
3. For every player, fetches their **regular season** game log (game type `2`, not playoffs `3`)
4. Aggregates goals, assists, points, and games played across the full regular season
5. Upserts into `regular_season_stats_cache`

It processes players in batches of 5 with a 500ms delay between batches to avoid NHL API rate limits. For 16 teams (~400 players), it takes approximately 1-2 minutes to complete.

#### Step 3: Run the Sync

This function only needs to be run **once before the Round 1 draft** (and optionally again if you want updated stats as the regular season wraps up). It's NOT scheduled on a cron — regular season stats are mostly static by playoff time.

**Before the playoff bracket is published** (you must provide team abbreviations manually):

```bash
curl -X POST https://<your-project-ref>.supabase.co/functions/v1/sync-regular-season-stats \
  -H "Authorization: Bearer <your-service-role-key>" \
  -H "Content-Type: application/json" \
  -d '{
    "season": "20252026",
    "team_abbreviations": ["TOR","FLA","TBL","BOS","OTT","MTL","BUF","DET","NYR","NJD","CAR","WSH","PIT","CBJ","NYI","PHI","WPG","DAL","COL","MIN","STL","NSH","CHI","UTA","VAN","EDM","CGY","LAK","VGK","SEA","SJS","ANA"]
  }'
```

> **Tip:** You don't need to know the exact playoff teams yet. Sync all 32 teams — extra data doesn't hurt, and the draft board only shows players from teams in the bracket anyway.

**After the playoff bracket is published** (function auto-discovers teams):

```bash
curl -X POST https://<your-project-ref>.supabase.co/functions/v1/sync-regular-season-stats \
  -H "Authorization: Bearer <your-service-role-key>" \
  -H "Content-Type: application/json" \
  -d '{"season": "20252026"}'
```

Expected response:
```json
{
  "message": "Regular season stats synced",
  "teams": 16,
  "playersFound": 384,
  "playersSynced": 380,
  "playersFailed": 4
}
```

A few failures (usually minor leaguers with no NHL game log) is normal.

#### Step 4: Verify

Go to **Table Editor → `regular_season_stats_cache`** and confirm rows exist with goals, assists, and points populated. You can also run:

```sql
SELECT player_name, team_abbreviation, goals, assists, points, games_played
FROM regular_season_stats_cache
WHERE nhl_season = '20252026'
ORDER BY points DESC
LIMIT 20;
```

> ⚠️ **DO NOT** skip this setup. Without it, the Round 1 draft board won't show the "Reg. Season Pts" column, making it harder for your league members to evaluate players.

---

## Quick Reference Card

| What | Value |
|---|---|
| **Supabase Dashboard** | `https://supabase.com/dashboard/project/<your-ref>` |
| **Project URL** | `https://<your-ref>.supabase.co` |
| **App Dev URL** | `http://localhost:4200` |
| **Auth Callback Path** | `/auth/callback` |
| **Auth Method** | Magic Link (email OTP) |
| **Edge Functions** | `sync-nhl-stats`, `sync-regular-season-stats` |
| **NHL Season Code** | `20252026` |
| **Playoff Rounds** | 1 (First Round), 2 (Second Round), 3 (Conference Finals), 4 (Stanley Cup Final) |
| **Scoring: Goal** | 1 point |
| **Scoring: Assist** | 1 point |
| **Scoring: Team Win** | 2 points |
| **Scoring: Shutout** | 4 points (replaces win points) |
| **Roster Limits** | 5F, 3D, 1G + IR slots (IR_F, IR_D) |

---

*Last updated: February 2026. Ready for the 2026 NHL Playoffs!* 🏒
