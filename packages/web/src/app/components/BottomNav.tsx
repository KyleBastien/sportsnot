import { UnstyledButton, Stack, Text, Group } from '@mantine/core';
import { useNavigate, useLocation, useParams } from 'react-router-dom';

interface NavTab {
  label: string;
  icon: string;
  path: (leagueId?: string) => string; // eslint-disable-line no-unused-vars
  match: string[];
}

const tabs: NavTab[] = [
  {
    label: 'Home',
    icon: '🏠',
    path: () => '/',
    match: ['/', '/leagues'],
  },
  {
    label: 'Draft',
    icon: '📋',
    path: (id) => (id ? `/draft/${id}` : '/'),
    match: ['/draft'],
  },
  {
    label: 'Roster',
    icon: '👥',
    path: (id) => (id ? `/roster/${id}` : '/'),
    match: ['/roster'],
  },
  {
    label: 'Standings',
    icon: '🏆',
    path: (id) => (id ? `/standings/${id}` : '/'),
    match: ['/standings'],
  },
  {
    label: 'Scoring',
    icon: '📊',
    path: (id) => (id ? `/scoring/${id}` : '/'),
    match: ['/scoring'],
  },
  {
    label: 'Profile',
    icon: '👤',
    path: () => '/profile',
    match: ['/profile'],
  },
];

export function BottomNav() {
  const navigate = useNavigate();
  const location = useLocation();
  const { leagueId } = useParams<{ leagueId: string }>();

  const isActive = (tab: NavTab) =>
    tab.match.some((m) =>
      m === '/' ? location.pathname === '/' : location.pathname.startsWith(m)
    );

  return (
    <Group h="100%" justify="space-around" align="center" wrap="nowrap" px={4}>
      {tabs.map((tab) => {
        const active = isActive(tab);
        const dest = tab.path(leagueId);
        const disabled = dest === '/' && tab.label !== 'Home' && !leagueId;

        return (
          <UnstyledButton
            key={tab.label}
            onClick={() => navigate(dest)}
            disabled={disabled}
            style={{
              flex: 1,
              opacity: disabled ? 0.4 : 1,
            }}
          >
            <Stack align="center" gap={2}>
              <Text size="lg" ta="center" lh={1}>
                {tab.icon}
              </Text>
              <Text
                size="xs"
                ta="center"
                fw={active ? 700 : 400}
                c={active ? 'blue' : 'dimmed'}
              >
                {tab.label}
              </Text>
            </Stack>
          </UnstyledButton>
        );
      })}
    </Group>
  );
}
