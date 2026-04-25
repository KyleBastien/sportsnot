import { Link, useNavigate } from 'react-router-dom';
import {
  Avatar,
  Button,
  Group,
  Menu,
  Skeleton,
  Text,
  UnstyledButton,
} from '@mantine/core';
import { useAuthContext } from './context/AuthContext';

export function UserMenu() {
  const { user, loading, signOut } = useAuthContext();
  const navigate = useNavigate();

  if (loading) {
    return (
      <Group gap="xs" data-testid="user-menu-skeleton">
        <Skeleton circle height={28} />
        <Skeleton height={14} width={70} visibleFrom="sm" />
      </Group>
    );
  }

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
