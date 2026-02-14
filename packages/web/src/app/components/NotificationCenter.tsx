import { useState } from 'react';
import {
  ActionIcon,
  Box,
  Button,
  Group,
  Indicator,
  Popover,
  ScrollArea,
  Stack,
  Text,
} from '@mantine/core';
import { useNavigate } from 'react-router-dom';
import {
  useNotificationContext,
  type Notification,
  type NotificationType,
} from '../context/NotificationContext';

const ICON_MAP: Record<NotificationType, string> = {
  draft: '📋',
  scoring: '⚡',
  league: '🏒',
  system: '⚙️',
};

function formatTimeAgo(timestamp: number): string {
  const diff = Date.now() - timestamp;
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return 'Just now';
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function getNavigationPath(notification: Notification): string | null {
  const { type, leagueId } = notification;
  if (!leagueId) return null;
  switch (type) {
    case 'draft':
      return `/draft/${leagueId}`;
    case 'scoring':
      return `/roster/${leagueId}`;
    case 'league':
      return `/leagues/${leagueId}`;
    default:
      return null;
  }
}

function NotificationItem({
  notification,
  onSelect,
}: {
  notification: Notification;
  onSelect: (n: Notification) => void;
}) {
  return (
    <Box
      p="xs"
      style={{
        cursor: 'pointer',
        borderLeft: notification.read
          ? '3px solid transparent'
          : '3px solid var(--mantine-color-blue-6)',
        backgroundColor: notification.read
          ? 'transparent'
          : 'var(--mantine-color-blue-light)',
        borderRadius: 4,
      }}
      onClick={() => onSelect(notification)}
    >
      <Group gap="xs" align="flex-start" wrap="nowrap">
        <Text size="lg" style={{ lineHeight: 1 }}>
          {ICON_MAP[notification.type]}
        </Text>
        <Stack gap={2} style={{ flex: 1, minWidth: 0 }}>
          <Text size="sm" fw={notification.read ? 400 : 700} truncate="end">
            {notification.title}
          </Text>
          <Text size="xs" c="dimmed" lineClamp={2}>
            {notification.message}
          </Text>
          <Text size="xs" c="dimmed">
            {formatTimeAgo(notification.timestamp)}
          </Text>
        </Stack>
      </Group>
    </Box>
  );
}

export function NotificationCenter() {
  const { notifications, unreadCount, markAsRead, markAllRead } =
    useNotificationContext();
  const navigate = useNavigate();
  const [opened, setOpened] = useState(false);

  const handleSelect = (notification: Notification) => {
    if (!notification.read) {
      markAsRead(notification.id);
    }
    const path = getNavigationPath(notification);
    if (path) {
      navigate(path);
    }
    setOpened(false);
  };

  return (
    <Popover
      width={360}
      position="bottom-end"
      shadow="md"
      opened={opened}
      onChange={setOpened}
    >
      <Popover.Target>
        <Indicator
          label={unreadCount > 0 ? unreadCount : undefined}
          size={18}
          color="red"
          disabled={unreadCount === 0}
          processing={unreadCount > 0}
        >
          <ActionIcon
            variant="subtle"
            size="lg"
            aria-label="Notifications"
            onClick={() => setOpened((o) => !o)}
          >
            <Text size="lg">🔔</Text>
          </ActionIcon>
        </Indicator>
      </Popover.Target>

      <Popover.Dropdown p={0}>
        <Group justify="space-between" p="sm" pb="xs">
          <Text fw={600} size="sm">
            Notifications
          </Text>
          {unreadCount > 0 && (
            <Button
              variant="subtle"
              size="compact-xs"
              onClick={() => markAllRead()}
            >
              Mark all as read
            </Button>
          )}
        </Group>

        <ScrollArea.Autosize mah={400}>
          {notifications.length === 0 ? (
            <Stack align="center" py="xl" gap="xs">
              <Text size="xl">🔕</Text>
              <Text size="sm" c="dimmed">
                No notifications yet
              </Text>
            </Stack>
          ) : (
            <Stack gap={2} p="xs" pt={0}>
              {notifications.map((n) => (
                <NotificationItem
                  key={n.id}
                  notification={n}
                  onSelect={handleSelect}
                />
              ))}
            </Stack>
          )}
        </ScrollArea.Autosize>
      </Popover.Dropdown>
    </Popover>
  );
}
