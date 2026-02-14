import { Badge, Group, Text } from '@mantine/core';
import type { MantineSize } from '@mantine/core';

export interface LiveIndicatorProps {
  isLive: boolean;
  lastUpdated?: Date;
  showTimestamp?: boolean;
  size?: 'sm' | 'md';
}

function formatTimeAgo(date: Date): string {
  const seconds = Math.floor((Date.now() - date.getTime()) / 1000);
  if (seconds < 60) return 'just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ago`;
}

const SIZE_MAP: Record<'sm' | 'md', { badge: MantineSize; text: MantineSize }> =
  {
    sm: { badge: 'sm', text: 'xs' },
    md: { badge: 'lg', text: 'xs' },
  };

export function LiveIndicator({
  isLive,
  lastUpdated,
  showTimestamp = false,
  size = 'md',
}: LiveIndicatorProps) {
  const { badge, text } = SIZE_MAP[size];

  if (!isLive) {
    return (
      <Group gap={4} align="center">
        <Badge color="gray" variant="dot" size={badge}>
          OFFLINE
        </Badge>
        {showTimestamp && lastUpdated && (
          <Text size={text} c="dimmed">
            Updated {formatTimeAgo(lastUpdated)}
          </Text>
        )}
      </Group>
    );
  }

  return (
    <Group gap={4} align="center">
      <style>{`
        @keyframes livePulse {
          0% { opacity: 1; }
          50% { opacity: 0.5; }
          100% { opacity: 1; }
        }
      `}</style>
      <Badge
        color="green"
        variant="dot"
        size={badge}
        styles={{
          root: {
            animation: 'livePulse 2s ease-in-out infinite',
          },
        }}
      >
        LIVE
      </Badge>
      {showTimestamp && lastUpdated && (
        <Text size={text} c="dimmed">
          Updated {formatTimeAgo(lastUpdated)}
        </Text>
      )}
    </Group>
  );
}
