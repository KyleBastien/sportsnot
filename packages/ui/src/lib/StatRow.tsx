import { Group, Text } from '@mantine/core';

export interface StatRowProps {
  label: string;
  value: string | number;
  highlight?: boolean;
  trend?: 'up' | 'down' | 'neutral';
  compact?: boolean;
}

const TREND_ARROWS: Record<string, { symbol: string; color: string }> = {
  up: { symbol: '▲', color: 'green' },
  down: { symbol: '▼', color: 'red' },
  neutral: { symbol: '▸', color: 'gray' },
};

export function StatRow({
  label,
  value,
  highlight = false,
  trend,
  compact = false,
}: StatRowProps) {
  return (
    <Group
      justify="space-between"
      gap={compact ? 'xs' : 'md'}
      py={compact ? 2 : 6}
      style={{ width: '100%' }}
    >
      <Text size={compact ? 'xs' : 'sm'} c="dimmed">
        {label}
      </Text>
      <Group gap={4}>
        {trend && (
          <Text size="xs" c={TREND_ARROWS[trend].color}>
            {TREND_ARROWS[trend].symbol}
          </Text>
        )}
        <Text
          size={compact ? 'xs' : 'sm'}
          fw={highlight ? 700 : 500}
          c={highlight ? 'blue' : undefined}
        >
          {value}
        </Text>
      </Group>
    </Group>
  );
}
