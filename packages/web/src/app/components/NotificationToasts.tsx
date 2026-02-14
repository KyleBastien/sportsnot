import { useEffect, useRef } from 'react';
import { notifications } from '@mantine/notifications';
import { useNavigate } from 'react-router-dom';
import {
  useNotificationContext,
  type Notification,
  type NotificationType,
} from '../context/NotificationContext';

const COLOR_MAP: Record<NotificationType, string> = {
  draft: 'blue',
  scoring: 'green',
  league: 'yellow',
  system: 'gray',
};

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

export function NotificationToasts() {
  const { notifications: items, markAsRead } = useNotificationContext();
  const navigate = useNavigate();
  const shownIdsRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    // Show toasts only for new notifications we haven't displayed yet
    for (const item of items) {
      if (item.read || shownIdsRef.current.has(item.id)) continue;

      shownIdsRef.current.add(item.id);

      const path = getNavigationPath(item);
      const notificationId = item.id;

      notifications.show({
        id: notificationId,
        title: item.title,
        message: item.message,
        color: COLOR_MAP[item.type],
        autoClose: 5000,
        withCloseButton: true,
        onClick: () => {
          markAsRead(notificationId);
          if (path) {
            navigate(path);
          }
          notifications.hide(notificationId);
        },
      });
    }
  }, [items, markAsRead, navigate]);

  // Cleanup stale IDs when notifications list is cleared
  useEffect(() => {
    const currentIds = new Set(items.map((n) => n.id));
    for (const id of shownIdsRef.current) {
      if (!currentIds.has(id)) {
        shownIdsRef.current.delete(id);
      }
    }
  }, [items]);

  return null;
}
