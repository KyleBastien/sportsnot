# SportsNot - NHL Fantasy Playoff Hockey Platform

## Project Overview

**SportsNot** is a web application for playing NHL Fantasy Playoff Hockey with a unique re-draft mechanic between playoff rounds. Built as an Nx monorepo with React + rspack, using Supabase for backend services.

### Core Gameplay Mechanics

- **Snake draft** at start of each playoff round
- **Full re-draft between rounds** with standings-based order (worst to best, snake pattern)
- **No keepers**: All players return to the pool between rounds
- **Scoring**: Goals = 1pt, Assists = 1pt, Team Wins = 2pts, Shutouts = 4pts
- **Roster**: 5 Forwards, 3 Defensemen, 1 Goalie/Team, 1 IR Forward, 1 IR Defenseman
- **IR Activation**: Retroactive point swap when replacing injured players (same position only)

### Technical Stack

| Layer            | Technology                                                  |
| ---------------- | ----------------------------------------------------------- |
| Monorepo         | Nx                                                          |
| Package Manager  | Yarn 4.x (Berry)                                            |
| Frontend         | React 19 with React Compiler                                |
| Bundler          | rspack                                                      |
| Backend          | Supabase (PostgreSQL, Auth, Realtime)                       |
| UI Library       | Mantine (recommended - modern, accessible, mobile-friendly) |
| Styling          | Vanilla Extract (zero-runtime CSS-in-JS, fully typed)       |
| State Management | TanStack Query (memoization handled by React Compiler)      |
| Real-time        | Supabase Realtime (WebSocket subscriptions)                 |
| Data Source      | NHL Official API                                            |
| Testing          | Rstest + React Testing Library                              |

---

## Phase 1: Project Foundation & Infrastructure

### 1.1 Nx Monorepo Setup

- [ ] Install Node.js 24 LTS and Yarn 4.x (Berry) globally
- [ ] Initialize Nx workspace with `npx create-nx-workspace@latest sportsnot --preset=npm`
- [ ] Configure Yarn Berry with `yarn set version stable`
- [ ] Set up `.yarnrc.yml` with nodeLinker: node-modules
- [ ] Configure Nx workspace settings in `nx.json`
- [ ] Set up path aliases in `tsconfig.base.json`

### 1.2 Application Structure

- [ ] Create React application: `nx g @nx/react:app web --directory=packages/web --bundler=rspack`
- [ ] Create shared UI library: `nx g @nx/react:lib ui --directory=packages/ui`
- [ ] Create shared types library: `nx g @nx/js:lib types --directory=packages/types`
- [ ] Create shared utilities library: `nx g @nx/js:lib utils --directory=packages/utils`
- [ ] Create NHL API client library: `nx g @nx/js:lib nhl-api --directory=packages/nhl-api`
- [ ] Create Supabase client library: `nx g @nx/js:lib supabase --directory=packages/supabase`
- [ ] Configure Nx workspaceLayout in `nx.json` to use `packages/` for all projects

### 1.3 rspack Configuration

- [ ] Configure rspack in `packages/web/rspack.config.js`
- [ ] Set up development server with HMR
- [ ] Configure production build optimizations
- [ ] Set up environment variable handling
- [ ] Configure CSS-in-JS with Vanilla Extract (@vanilla-extract/css)
- [ ] Set up Vanilla Extract rspack plugin (@vanilla-extract/webpack-plugin)
- [ ] Configure theme tokens (colors, spacing, typography) with type safety
- [ ] Set up sprinkles for atomic utility classes
- [ ] Set up asset handling (images, fonts, SVGs)
- [ ] Configure React Compiler (babel-plugin-react-compiler) in rspack
- [ ] Verify React Compiler is optimizing components correctly

### 1.4 Code Quality & Tooling

- [ ] Configure ESLint with Nx recommended rules
- [ ] Configure Prettier for consistent formatting
- [ ] Set up commitlint for conventional commits
- [ ] Configure TypeScript strict mode

### 1.5 CI/CD Pipeline (GitHub Actions)

- [ ] Create workflow for PR validation (lint, test, build)
- [ ] Create workflow for GitHub Pages deployment on main branch
- [ ] Configure GitHub Pages in repository settings (Actions source)
- [ ] Set up Nx affected commands for efficient CI
- [ ] Add build artifact upload for Pages deployment

---

## Phase 2: Supabase Backend Setup

### 2.1 Supabase Project Configuration

- [ ] Create Supabase project in dashboard
- [ ] Initialize Supabase CLI in `packages/supabase-db/` with `supabase init`
- [ ] Configure authentication providers (magic link email)
- [ ] Set up custom SMTP for branded emails
- [ ] Configure auth email templates
- [ ] Set up Row Level Security (RLS) policies

### 2.2 Database Schema Design

#### Users Table

```sql
CREATE TABLE users (
  id UUID PRIMARY KEY REFERENCES auth.users(id),
  email TEXT NOT NULL UNIQUE,
  display_name TEXT NOT NULL,
  avatar_url TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

#### Leagues Table

```sql
CREATE TABLE leagues (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  commissioner_id UUID REFERENCES users(id) NOT NULL,
  invite_code TEXT UNIQUE NOT NULL,
  max_participants INTEGER DEFAULT 12 CHECK (max_participants BETWEEN 2 AND 12),
  current_round INTEGER DEFAULT 0,
  status TEXT DEFAULT 'setup' CHECK (status IN ('setup', 'drafting', 'active', 'completed')),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

#### League Members Table

```sql
CREATE TABLE league_members (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  league_id UUID REFERENCES leagues(id) ON DELETE CASCADE,
  user_id UUID REFERENCES users(id) ON DELETE CASCADE,
  team_name TEXT NOT NULL,
  total_points INTEGER DEFAULT 0,
  joined_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(league_id, user_id)
);
```

#### Drafts Table

```sql
CREATE TABLE drafts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  league_id UUID REFERENCES leagues(id) ON DELETE CASCADE,
  round INTEGER NOT NULL,
  status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'active', 'completed')),
  current_pick INTEGER DEFAULT 1,
  draft_order JSONB NOT NULL, -- Array of user_ids in pick order
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  UNIQUE(league_id, round)
);
```

#### Draft Picks Table

```sql
CREATE TABLE draft_picks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  draft_id UUID REFERENCES drafts(id) ON DELETE CASCADE,
  league_member_id UUID REFERENCES league_members(id) ON DELETE CASCADE,
  pick_number INTEGER NOT NULL,
  player_id INTEGER, -- NHL API player ID (NULL for goalie/team picks)
  team_id INTEGER, -- NHL API team ID (for goalie picks)
  position TEXT NOT NULL CHECK (position IN ('F', 'D', 'G', 'IR_F', 'IR_D')),
  picked_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(draft_id, pick_number)
);
```

#### Rosters Table (Current Round Active Roster)

```sql
CREATE TABLE rosters (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  league_member_id UUID REFERENCES league_members(id) ON DELETE CASCADE,
  round INTEGER NOT NULL,
  player_id INTEGER,
  team_id INTEGER,
  position TEXT NOT NULL CHECK (position IN ('F', 'D', 'G', 'IR_F', 'IR_D')),
  is_active BOOLEAN DEFAULT TRUE, -- FALSE if on IR
  points_earned INTEGER DEFAULT 0,
  activated_from_ir BOOLEAN DEFAULT FALSE,
  UNIQUE(league_member_id, round, position, player_id)
);
```

#### Player Stats Cache Table

```sql
CREATE TABLE player_stats_cache (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  player_id INTEGER NOT NULL,
  nhl_season TEXT NOT NULL,
  playoff_round INTEGER NOT NULL,
  goals INTEGER DEFAULT 0,
  assists INTEGER DEFAULT 0,
  games_played INTEGER DEFAULT 0,
  is_injured BOOLEAN DEFAULT FALSE,
  last_updated TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(player_id, nhl_season, playoff_round)
);
```

#### Team Stats Cache Table

```sql
CREATE TABLE team_stats_cache (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  team_id INTEGER NOT NULL,
  nhl_season TEXT NOT NULL,
  playoff_round INTEGER NOT NULL,
  wins INTEGER DEFAULT 0,
  shutouts INTEGER DEFAULT 0,
  last_updated TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(team_id, nhl_season, playoff_round)
);
```

### 2.3 Database Functions & Triggers

- [ ] Create function to auto-update `updated_at` timestamps
- [ ] Create function to generate unique invite codes
- [ ] Create function to calculate snake draft order
- [ ] Create function to calculate re-draft order based on standings
- [ ] Create function to calculate member points from roster
- [ ] Create function to handle IR activation with retroactive points
- [ ] Create function to validate roster composition

### 2.4 Row Level Security Policies

- [ ] Users can read their own data, update display_name/avatar
- [ ] League members can read league data they belong to
- [ ] Commissioners can update their league settings
- [ ] Draft picks visible to all league members
- [ ] Roster changes only by roster owner during valid windows

### 2.5 Realtime Subscriptions

- [ ] Configure realtime for `drafts` table (draft status changes)
- [ ] Configure realtime for `draft_picks` table (new picks)
- [ ] Configure realtime for `rosters` table (roster changes)
- [ ] Configure realtime for `league_members` table (points updates)

### 2.6 Edge Functions

- [ ] Create edge function to sync NHL API player data
- [ ] Create edge function to update player/team stats
- [ ] Create scheduled function to poll NHL API during games
- [ ] Create edge function to process round completion

---

## Phase 3: NHL API Integration

### 3.1 NHL API Client Library

- [ ] Research NHL API endpoints (https://api-web.nhle.com)
- [ ] Create TypeScript types for NHL API responses
- [ ] Implement player search/lookup endpoints
- [ ] Implement team roster endpoints
- [ ] Implement game schedule endpoints
- [ ] Implement live game stats endpoints
- [ ] Implement playoff bracket/series endpoints

### 3.2 Data Sync Service

- [ ] Create service to fetch all playoff-eligible players
- [ ] Create service to fetch current playoff bracket
- [ ] Create service to track eliminated teams/players
- [ ] Create service to poll live game stats
- [ ] Implement caching strategy to minimize API calls
- [ ] Handle API rate limiting gracefully

### 3.3 Player/Team Data Models

- [ ] Define Player interface with NHL API fields
- [ ] Define Team interface with NHL API fields
- [ ] Define Game interface for schedule tracking
- [ ] Define PlayoffSeries interface for bracket tracking
- [ ] Create utility functions for data transformation

---

## Phase 4: Authentication & User Management

### 4.1 Auth Context & Hooks

- [ ] Create Supabase auth client wrapper
- [ ] Create `useAuth` hook for auth state
- [ ] Create `useUser` hook for user profile
- [ ] Implement magic link sign-in flow
- [ ] Implement sign-out flow
- [ ] Handle auth state persistence

### 4.2 Auth UI Components

- [ ] Create `LoginPage` with magic link form
- [ ] Create `AuthCallback` page for magic link redirect
- [ ] Create email input validation
- [ ] Create "check your email" confirmation UI
- [ ] Create loading states for auth operations

### 4.3 User Profile

- [ ] Create `ProfilePage` component
- [ ] Create display name edit form
- [ ] Create avatar upload (Supabase Storage)
- [ ] Create account deletion flow

### 4.4 Protected Routes

- [ ] Create `ProtectedRoute` wrapper component
- [ ] Implement redirect to login for unauthenticated users
- [ ] Create auth loading skeleton
- [ ] Handle expired sessions gracefully

---

## Phase 5: Core UI Components (Mantine-based)

### 5.1 Layout Components

- [ ] Create `AppShell` with responsive navigation
- [ ] Create `Header` with user menu and logo
- [ ] Create `MobileNav` with bottom navigation
- [ ] Create `PageContainer` with consistent padding
- [ ] Create `LoadingScreen` component
- [ ] Create `ErrorBoundary` with fallback UI

### 5.2 Common Components

- [ ] Create `PlayerCard` component (photo, name, team, stats)
- [ ] Create `TeamCard` component (logo, name, record)
- [ ] Create `PointsBadge` component
- [ ] Create `RosterSlot` component (empty/filled states)
- [ ] Create `DraftPick` component for draft history
- [ ] Create `StandingsRow` component
- [ ] Create `CountdownTimer` component

### 5.3 Form Components

- [ ] Create `LeagueForm` for creating/editing leagues
- [ ] Create `TeamNameForm` for league members
- [ ] Create `InviteCodeInput` for joining leagues
- [ ] Create form validation with Mantine form hooks

### 5.4 Modal Components

- [ ] Create `PlayerDetailModal` with full stats
- [ ] Create `ConfirmationModal` for destructive actions
- [ ] Create `InviteMembersModal` with share options
- [ ] Create `DraftPlayerModal` for pick confirmation

---

## Phase 6: League Management Features

### 6.1 League Creation

- [ ] Create `CreateLeaguePage` component
- [ ] Implement league name input with validation
- [ ] Implement max participants selector (2-12)
- [ ] Generate unique invite code on creation
- [ ] Auto-join creator as commissioner
- [ ] Navigate to league dashboard after creation

### 6.2 League Dashboard

- [ ] Create `LeagueDashboardPage` component
- [ ] Display league name, status, and round
- [ ] Show member list with points
- [ ] Show current standings
- [ ] Display commissioner controls (if applicable)
- [ ] Show invite code with copy button

### 6.3 Join League Flow

- [ ] Create `JoinLeaguePage` component
- [ ] Implement invite code input
- [ ] Validate code and show league preview
- [ ] Prompt for team name
- [ ] Handle already-joined and full-league cases
- [ ] Navigate to league dashboard after joining

### 6.4 League Settings (Commissioner)

- [ ] Create `LeagueSettingsPage` component
- [ ] Edit league name
- [ ] Regenerate invite code
- [ ] Remove members (before draft starts)
- [ ] Start draft button
- [ ] Advance to next round controls

### 6.5 My Leagues List

- [ ] Create `MyLeaguesPage` component
- [ ] List all leagues user belongs to
- [ ] Show league status and user's rank
- [ ] Quick actions (view, leave)
- [ ] Create new league CTA

---

## Phase 7: Draft System

### 7.1 Draft Preparation

- [ ] Create `DraftLobbyPage` component
- [ ] Show all league members with ready status
- [ ] Display draft order (snake visualization)
- [ ] Show countdown to draft start
- [ ] Commissioner "Start Draft" button
- [ ] Real-time member presence indicators

### 7.2 Draft Board

- [ ] Create `DraftBoardPage` component
- [ ] Display available players grid/list
- [ ] Filter by position (F, D, G/Team)
- [ ] Search players by name
- [ ] Sort by stats (goals, assists, points)
- [ ] Show eliminated players as unavailable
- [ ] Highlight injured players

### 7.3 Draft Interface

- [ ] Create `DraftRoom` component
- [ ] Show current pick number and drafter
- [ ] Display pick timer (if implemented)
- [ ] Show "Your Turn" prominent notification
- [ ] One-click draft button on player cards
- [ ] Confirmation modal before finalizing pick

### 7.4 Roster Builder (During Draft)

- [ ] Create `MyDraftRoster` sidebar component
- [ ] Show filled/empty roster slots
- [ ] Visual indication of position requirements
- [ ] Running total of picks made
- [ ] Position requirement indicators

### 7.5 Draft History

- [ ] Create `DraftHistory` component
- [ ] Show all picks in chronological order
- [ ] Filter by round/team
- [ ] Highlight user's picks
- [ ] Real-time updates via Supabase subscription

### 7.6 Re-Draft Flow (Between Rounds)

- [ ] Create `RoundTransitionPage` component
- [ ] Show previous round final standings
- [ ] Display new draft order (worst to best, snake)
- [ ] Clear all rosters for new round
- [ ] Remove eliminated players from draft pool
- [ ] Commissioner triggers new round draft

### 7.7 Real-time Draft Sync

- [ ] Subscribe to draft status changes
- [ ] Subscribe to new pick events
- [ ] Handle pick conflicts gracefully
- [ ] Auto-advance when pick is made
- [ ] Reconnection handling

---

## Phase 8: Roster Management

### 8.1 My Roster Page

- [ ] Create `MyRosterPage` component
- [ ] Display current round roster
- [ ] Show each player with current round stats
- [ ] Show point totals per player
- [ ] Show total team points

### 8.2 IR Activation Flow

- [ ] Create `IRActivationModal` component
- [ ] Detect injured players on roster
- [ ] Show eligible IR replacements
- [ ] Display point differential preview
- [ ] Confirm activation with retroactive calculation
- [ ] Update roster and points in database

### 8.3 Roster Validation

- [ ] Validate 5F, 3D, 1G composition
- [ ] Prevent duplicate players
- [ ] Block picks of eliminated players
- [ ] Enforce position matching for IR

### 8.4 Historical Rosters

- [ ] Create `RosterHistoryPage` component
- [ ] View rosters from previous rounds
- [ ] Show points earned per round
- [ ] Compare roster performance across rounds

---

## Phase 9: Scoring & Standings

### 9.1 Points Calculation Engine

- [ ] Create scoring calculation functions
- [ ] Player goals: 1 point each
- [ ] Player assists: 1 point each
- [ ] Team wins: 2 points each
- [ ] Team shutouts: 4 points (replaces win points)
- [ ] Handle IR activation point swaps

### 9.2 Standings Page

- [ ] Create `StandingsPage` component
- [ ] Show league members ranked by points
- [ ] Display points breakdown (player pts, goalie pts)
- [ ] Show round-by-round points
- [ ] Highlight current user's position

### 9.3 Live Scoring Updates

- [ ] Subscribe to player stats changes
- [ ] Subscribe to team stats changes
- [ ] Real-time point updates during games
- [ ] Visual notifications for scoring events

### 9.4 Scoring History

- [ ] Create `ScoringHistoryPage` component
- [ ] Show all scoring events
- [ ] Filter by player/team/date
- [ ] Export scoring data (CSV)

---

## Phase 10: Dashboard & Home

### 10.1 Main Dashboard

- [ ] Create `DashboardPage` component
- [ ] Show active leagues summary
- [ ] Display upcoming drafts
- [ ] Show live scoring if games in progress
- [ ] Quick links to all leagues

### 10.2 Live Games Widget

- [ ] Create `LiveGamesWidget` component
- [ ] Show games currently in progress
- [ ] Highlight players on user's rosters
- [ ] Real-time score updates

### 10.3 Notifications

- [ ] Draft starting soon alerts
- [ ] Your turn to pick alerts
- [ ] Scoring milestone notifications
- [ ] Round completion notifications

---

## Phase 11: Mobile Optimization

### 11.1 Responsive Layouts

- [ ] Test all pages on mobile viewports
- [ ] Implement collapsible sections
- [ ] Optimize touch targets (min 44px)
- [ ] Implement swipe gestures where appropriate

### 11.2 Mobile-Specific Components

- [ ] Create mobile draft interface
- [ ] Create mobile roster view
- [ ] Create mobile-friendly player selection
- [ ] Bottom sheet modals for mobile

### 11.3 Performance Optimization

- [ ] Implement virtualized lists for large data
- [ ] Lazy load images
- [ ] Optimize bundle size
- [ ] Implement service worker for offline support

---

## Phase 12: Testing

### 12.1 Unit Tests (Rstest)

- [ ] Configure Rstest (@rstest/core) for Nx workspace
- [ ] Leverage rspack integration for fast test transforms
- [ ] Test scoring calculation functions
- [ ] Test draft order generation
- [ ] Test IR activation logic
- [ ] Test roster validation
- [ ] Test NHL API client functions
- [ ] Test utility functions

### 12.2 Component Tests (React Testing Library)

- [ ] Configure @testing-library/react with Rstest
- [ ] Test auth flow components
- [ ] Test league creation/join forms
- [ ] Test draft board interactions
- [ ] Test roster management UI
- [ ] Test standings display

### 12.3 Integration Tests

- [ ] Test Supabase client integration
- [ ] Test real-time subscriptions
- [ ] Test NHL API data sync
- [ ] Test auth session handling

---

## Phase 13: Deployment & DevOps

### 13.1 Environment Configuration

- [ ] Set up development environment variables
- [ ] Set up production environment variables
- [ ] Configure Supabase project for production
- [ ] Create `.env.example` with required variables

### 13.2 GitHub Pages Hosting

- [ ] Configure rspack for static SPA output
- [ ] Set up base URL/public path for GitHub Pages subdirectory
- [ ] Create 404.html redirect for SPA client-side routing
- [ ] Configure custom domain (optional)
- [ ] Set up CNAME file for custom domain

### 13.3 GitHub Actions Deployment Pipeline

- [ ] Create `.github/workflows/ci.yml` for PR checks
  - [ ] Checkout code
  - [ ] Set up Node.js and Yarn
  - [ ] Install dependencies with caching
  - [ ] Run lint, test, and build
- [ ] Create `.github/workflows/deploy.yml` for production
  - [ ] Trigger on push to main branch
  - [ ] Build production bundle with rspack
  - [ ] Upload artifact with `actions/upload-pages-artifact`
  - [ ] Deploy with `actions/deploy-pages`
- [ ] Configure GitHub repository Pages settings
  - [ ] Source: GitHub Actions
  - [ ] Enable HTTPS enforcement

### 13.4 Monitoring & Analytics

- [ ] Configure Supabase usage monitoring

### 13.5 Database Management

- [ ] Set up database migrations workflow
- [ ] Configure database backups
- [ ] Plan for data retention policies
- [ ] Document recovery procedures

---

## Folder Structure

```
sportsnot/
├── packages/
│   ├── web/                          # Main React application
│   │   ├── src/
│   │   │   ├── app/
│   │   │   │   ├── routes/           # Page components
│   │   │   │   │   ├── auth/
│   │   │   │   │   ├── dashboard/
│   │   │   │   │   ├── leagues/
│   │   │   │   │   ├── draft/
│   │   │   │   │   ├── roster/
│   │   │   │   │   └── standings/
│   │   │   │   ├── components/       # App-specific components
│   │   │   │   ├── hooks/            # App-specific hooks
│   │   │   │   ├── stores/           # Zustand stores
│   │   │   │   ├── context/          # React context providers
│   │   │   │   └── app.tsx
│   │   │   ├── assets/
│   │   │   ├── styles/
│   │   │   │   ├── theme.css.ts       # Vanilla Extract theme tokens
│   │   │   │   ├── sprinkles.css.ts   # Atomic utility styles
│   │   │   │   └── global.css.ts      # Global styles
│   │   │   └── main.tsx
│   │   ├── rspack.config.js
│   │   └── project.json
│   ├── ui/                           # Shared UI components
│   │   └── src/
│   │       ├── components/
│   │       │   ├── PlayerCard/
│   │       │   │   ├── PlayerCard.tsx
│   │       │   │   ├── PlayerCard.css.ts  # Co-located styles
│   │       │   │   └── index.ts
│   │       │   ├── TeamCard/
│   │       │   ├── RosterSlot/
│   │       │   └── ...
│   │       ├── styles/
│   │       │   ├── tokens.css.ts      # Shared design tokens
│   │       │   ├── recipes.css.ts     # Reusable style recipes
│   │       │   └── sprinkles.css.ts   # Shared atomic utilities
│   │       └── index.ts
│   ├── types/                        # Shared TypeScript types
│   │   └── src/
│   │       ├── user.ts
│   │       ├── league.ts
│   │       ├── draft.ts
│   │       ├── roster.ts
│   │       ├── nhl.ts
│   │       └── index.ts
│   ├── utils/                        # Shared utilities
│   │   └── src/
│   │       ├── scoring.ts
│   │       ├── draft-order.ts
│   │       ├── validation.ts
│   │       └── index.ts
│   ├── supabase/                     # Supabase client & hooks
│   │   └── src/
│   │       ├── client.ts
│   │       ├── hooks/
│   │       │   ├── useAuth.ts
│   │       │   ├── useLeague.ts
│   │       │   ├── useDraft.ts
│   │       │   └── useRoster.ts
│   │       ├── queries/
│   │       └── index.ts
│   ├── supabase-db/                  # Supabase migrations & edge functions
│   │   ├── migrations/
│   │   ├── functions/
│   │   ├── config.toml
│   │   └── project.json
│   └── nhl-api/                      # NHL API client
│       └── src/
│           ├── client.ts
│           ├── endpoints/
│           ├── types/
│           └── index.ts
├── tools/                            # Nx generators & executors
├── .github/
│   └── workflows/
├── nx.json
├── tsconfig.base.json
├── package.json
└── yarn.lock
```

---

## MVP Feature Checklist

### Must Have (MVP)

- [x] ~~Define requirements~~ (Completed in planning)
- [ ] Nx monorepo with rspack + React
- [ ] Supabase auth (magic link)
- [ ] Create/join private leagues
- [ ] Real-time snake draft
- [ ] Roster display (5F, 3D, 1G, IR slots)
- [ ] Basic scoring (goals, assists, wins, shutouts)
- [ ] Standings page
- [ ] Re-draft between rounds
- [ ] IR activation flow
- [ ] Mobile-responsive design
- [ ] Player comparison tools

### Nice to Have (Post-MVP)

- [ ] Push notifications
- [ ] Draft auto-pick (timeout)
- [ ] Historical league archives
- [ ] Advanced stats display
- [ ] Social sharing
- [ ] Multiple scoring formats
- [ ] Commissioner trade tools
- [ ] Public leagues

---

## Risk Mitigation

| Risk                         | Mitigation                                               |
| ---------------------------- | -------------------------------------------------------- |
| NHL API changes/instability  | Cache data aggressively, implement fallback manual entry |
| Real-time draft sync issues  | Implement optimistic updates with conflict resolution    |
| Supabase rate limits         | Batch operations, implement client-side caching          |
| Mobile performance           | Virtualization, lazy loading, bundle optimization        |
| Playoff schedule uncertainty | Flexible round detection, commissioner override controls |

---

## Notes & Considerations

1. **NHL API**: The official NHL API is undocumented but stable. Consider building abstraction layer for potential future API changes.

2. **Time Zones**: All draft times should be stored in UTC, displayed in user's local timezone.

3. **Concurrent Drafts**: Each league's draft is independent. Supabase RLS ensures data isolation.

4. **Eliminated Players**: Players on eliminated teams become undraftable. Need to track playoff bracket state.

5. **Goalie/Team Confusion**: UI should clearly communicate that "drafting a goalie" means drafting the team's goaltending, that means we shouldn't show individual goalie names in the roster or draft interface.

6. **Point Retroactivity**: IR activation retroactive points require storing all scoring events, not just totals.

7. **Round Transitions**: Make it clear when a round ends and all players return to the pool for re-draft.
