import { Route, Routes, Link, useNavigate } from 'react-router-dom';
import {
  AppShell,
  Title,
  Group,
  Button,
  Menu,
  Avatar,
  Text,
  UnstyledButton,
} from '@mantine/core';
import { useMediaQuery } from '@mantine/hooks';
import { useAuthContext } from './context/AuthContext';
import { ProtectedRoute } from './components/ProtectedRoute';
import { ErrorBoundary } from './components/ErrorBoundary';
import { CompareTray } from './components/CompareTray';
import { BottomNav } from './components/BottomNav';
import { NotificationToasts } from './components/NotificationToasts';
import { NotificationCenter } from './components/NotificationCenter';
import { PlayerDetailModal } from './components/PlayerDetailModal';

// Route pages
import { LoginPage } from './routes/auth/LoginPage';
import { AuthCallbackPage } from './routes/auth/AuthCallbackPage';
import { DashboardPage } from './routes/dashboard/DashboardPage';
import { CreateLeaguePage } from './routes/leagues/CreateLeaguePage';
import { JoinLeaguePage } from './routes/leagues/JoinLeaguePage';
import { LeagueDashboardPage } from './routes/leagues/LeagueDashboardPage';
import { LeagueSettingsPage } from './routes/leagues/LeagueSettingsPage';
import { DraftPage } from './routes/draft/DraftPage';
import { DraftLobbyPage } from './routes/draft/DraftLobbyPage';
import { RoundTransitionPage } from './routes/draft/RoundTransitionPage';
import { RosterPage } from './routes/roster/RosterPage';
import { RosterHistoryPage } from './routes/roster/RosterHistoryPage';
import { StandingsPage } from './routes/standings/StandingsPage';
import { ProfilePage } from './routes/profile/ProfilePage';
import { ScoringHistoryPage } from './routes/scoring/ScoringHistoryPage';

function UserMenu() {
  const { user, signOut } = useAuthContext();
  const navigate = useNavigate();

  if (!user) {
    return (
      <Button variant="outline" component={Link} to="/auth/login">
        Sign In
      </Button>
    );
  }

  const displayName =
    user.user_metadata?.['display_name'] ?? user.email?.split('@')[0] ?? 'User';

  return (
    <Menu shadow="md" width={200}>
      <Menu.Target>
        <UnstyledButton>
          <Group gap="xs">
            <Avatar size="sm" radius="xl">
              {displayName[0]?.toUpperCase()}
            </Avatar>
            <Text size="sm" visibleFrom="sm">
              {displayName}
            </Text>
          </Group>
        </UnstyledButton>
      </Menu.Target>
      <Menu.Dropdown>
        <Menu.Item onClick={() => navigate('/')}>Dashboard</Menu.Item>
        <Menu.Item onClick={() => navigate('/profile')}>Profile</Menu.Item>
        <Menu.Divider />
        <Menu.Item
          color="red"
          onClick={async () => {
            await signOut();
            navigate('/auth/login');
          }}
        >
          Sign Out
        </Menu.Item>
      </Menu.Dropdown>
    </Menu>
  );
}

export function App() {
  const isMobile = useMediaQuery('(max-width: 768px)');

  return (
    <ErrorBoundary>
      <AppShell
        header={{ height: 60 }}
        footer={isMobile ? { height: 60 } : undefined}
        padding="md"
      >
        <AppShell.Header>
          <Group h="100%" px="md" justify="space-between">
            <UnstyledButton component={Link} to="/">
              <Title order={3}>🏒 SportsNot</Title>
            </UnstyledButton>
            <Group gap="xs">
              <NotificationCenter />
              <UserMenu />
            </Group>
          </Group>
        </AppShell.Header>

        {isMobile && (
          <AppShell.Footer>
            <BottomNav />
          </AppShell.Footer>
        )}

        <AppShell.Main>
          <Routes>
            {/* Auth routes */}
            <Route path="/auth/login" element={<LoginPage />} />
            <Route path="/auth/callback" element={<AuthCallbackPage />} />

            {/* Protected routes */}
            <Route
              path="/"
              element={
                <ProtectedRoute>
                  <DashboardPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/profile"
              element={
                <ProtectedRoute>
                  <ProfilePage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/leagues/create"
              element={
                <ProtectedRoute>
                  <CreateLeaguePage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/leagues/join"
              element={
                <ProtectedRoute>
                  <JoinLeaguePage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/leagues/:leagueId"
              element={
                <ProtectedRoute>
                  <LeagueDashboardPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/leagues/:leagueId/settings"
              element={
                <ProtectedRoute>
                  <LeagueSettingsPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/draft/:leagueId/lobby"
              element={
                <ProtectedRoute>
                  <DraftLobbyPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/draft/:leagueId"
              element={
                <ProtectedRoute>
                  <DraftPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/draft/:leagueId/transition"
              element={
                <ProtectedRoute>
                  <RoundTransitionPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/roster/:leagueId"
              element={
                <ProtectedRoute>
                  <RosterPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/roster/:leagueId/history"
              element={
                <ProtectedRoute>
                  <RosterHistoryPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/standings/:leagueId"
              element={
                <ProtectedRoute>
                  <StandingsPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/scoring/:leagueId"
              element={
                <ProtectedRoute>
                  <ScoringHistoryPage />
                </ProtectedRoute>
              }
            />
          </Routes>
        </AppShell.Main>

        <CompareTray />
        <PlayerDetailModal />
        <NotificationToasts />
      </AppShell>
    </ErrorBoundary>
  );
}

export default App;
