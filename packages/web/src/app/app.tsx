import { lazy, Suspense, useEffect, type ReactNode } from 'react';
import { Route, Routes, Link, useNavigate } from 'react-router-dom';
import {
  ActionIcon,
  AppShell,
  Group,
  Button,
  Menu,
  Avatar,
  Text,
  UnstyledButton,
  Image,
  useComputedColorScheme,
  useMantineColorScheme,
} from '@mantine/core';
import { IconSun, IconMoon } from '@tabler/icons-react';
import { useAuthContext } from './context/AuthContext';
import logoSrc from '../assets/sportsnot-logo.png';
import { ProtectedRoute } from './components/ProtectedRoute';
import { ErrorBoundary } from './components/ErrorBoundary';
import { initWidgetBridge } from './widget/initWidgetBridge';

const WIDGET_BUNDLE_ID = 'com.sportsnot.app';

// Mock mode — only loaded when VITE_MOCK_MODE is 'true'
const MockModeBanner =
  import.meta.env.VITE_MOCK_MODE === 'true'
    ? lazy(() =>
        import('../mock/MockModeBanner').then((m) => ({
          default: m.MockModeBanner,
        }))
      )
    : null;

const MockDataProvider =
  import.meta.env.VITE_MOCK_MODE === 'true'
    ? lazy(() =>
        import('../mock/MockDataProvider').then((m) => ({
          default: m.MockDataProvider,
        }))
      )
    : null;

const SimulationControlPanel =
  import.meta.env.VITE_MOCK_MODE === 'true'
    ? lazy(() =>
        import('../mock/components/SimulationControlPanel').then((m) => ({
          default: m.SimulationControlPanel,
        }))
      )
    : null;

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
import { ScoringHistoryPage } from './routes/scoring/ScoringHistoryPage';
import { ProfilePage } from './routes/profile/ProfilePage';

function ColorSchemeToggle() {
  const { setColorScheme } = useMantineColorScheme();
  const computedColorScheme = useComputedColorScheme('light');

  return (
    <ActionIcon
      variant="default"
      size="lg"
      aria-label="Toggle color scheme"
      onClick={() =>
        setColorScheme(computedColorScheme === 'dark' ? 'light' : 'dark')
      }
    >
      {computedColorScheme === 'dark' ? (
        <IconSun size={20} />
      ) : (
        <IconMoon size={20} />
      )}
    </ActionIcon>
  );
}

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
        <Menu.Item color="red" onClick={() => signOut()}>
          Sign Out
        </Menu.Item>
      </Menu.Dropdown>
    </Menu>
  );
}

function MockWrapper({ children }: { children: ReactNode }) {
  if (!MockDataProvider) return <>{children}</>;
  return (
    <Suspense fallback={null}>
      <MockDataProvider>
        {children}
        {SimulationControlPanel && (
          <Suspense fallback={null}>
            <SimulationControlPanel />
          </Suspense>
        )}
      </MockDataProvider>
    </Suspense>
  );
}

export function App() {
  useEffect(() => {
    const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
    const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;
    if (!supabaseUrl || !anonKey) return;

    const handlePromise = initWidgetBridge({
      supabaseUrl,
      anonKey,
      bundleId: WIDGET_BUNDLE_ID,
    });

    return () => {
      void handlePromise
        .then((handle) => handle.remove())
        .catch(() => undefined);
    };
  }, []);

  return (
    <ErrorBoundary>
      {MockModeBanner && (
        <Suspense fallback={null}>
          <MockModeBanner />
        </Suspense>
      )}
      <MockWrapper>
        <AppShell
          header={{ height: 'calc(60px + env(safe-area-inset-top))' }}
          padding="md"
        >
          <AppShell.Header>
            <Group h="100%" px="md" justify="space-between">
              <UnstyledButton component={Link} to="/">
                <Image
                  src={logoSrc}
                  alt="SportsNot Fantasy Hockey"
                  h={40}
                  w="auto"
                  fit="contain"
                />
              </UnstyledButton>
              <Group gap="sm">
                <ColorSchemeToggle />
                <UserMenu />
              </Group>
            </Group>
          </AppShell.Header>

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
                path="/roster/:leagueId/:leagueMemberId?"
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
        </AppShell>
      </MockWrapper>
    </ErrorBoundary>
  );
}

export default App;
