import {
  Card,
  Group,
  Text,
  Avatar,
  Stack,
  ActionIcon,
  Tooltip,
} from '@mantine/core';
import { PositionBadge } from './PositionBadge';
import { PointsBadge } from './PointsBadge';

export type RosterSlotAction = 'compare' | 'activate' | 'details';

export interface RosterSlotPlayer {
  name: string;
  teamAbbrev: string;
  headshot?: string;
  stats?: Record<string, number>;
}

export interface RosterSlotProps {
  position: 'F' | 'D' | 'G' | 'IR_F' | 'IR_D';
  player?: RosterSlotPlayer;
  pointsEarned?: number;
  isActive?: boolean;
  isEmpty?: boolean;
  onAction?: (action: RosterSlotAction) => void;
  actions?: RosterSlotAction[];
}

const ACTION_CONFIG: Record<RosterSlotAction, { label: string; icon: string }> =
  {
    compare: { label: 'Compare', icon: '⚖' },
    activate: { label: 'Activate from IR', icon: '↑' },
    details: { label: 'View details', icon: '…' },
  };

const isIR = (position: string) => position.startsWith('IR_');

export function RosterSlot({
  position,
  player,
  pointsEarned,
  isActive = true,
  isEmpty = !player,
  onAction,
  actions = [],
}: RosterSlotProps) {
  if (isEmpty || !player) {
    return (
      <Card
        padding="sm"
        radius="md"
        withBorder
        style={{
          borderStyle: 'dashed',
          borderColor: isIR(position)
            ? 'var(--mantine-color-red-3)'
            : 'var(--mantine-color-gray-4)',
          backgroundColor: isIR(position)
            ? 'var(--mantine-color-red-0)'
            : undefined,
        }}
      >
        <Group>
          <PositionBadge position={position} />
          <Text c="dimmed" size="sm" fs="italic">
            Empty
          </Text>
        </Group>
      </Card>
    );
  }

  return (
    <Card
      padding="sm"
      radius="md"
      withBorder
      style={{
        borderColor: isIR(position) ? 'var(--mantine-color-red-3)' : undefined,
        backgroundColor: isIR(position)
          ? 'var(--mantine-color-red-0)'
          : undefined,
        opacity: isActive ? 1 : 0.6,
      }}
    >
      <Group>
        <Avatar src={player.headshot} size="md" radius="md">
          {player.name
            .split(' ')
            .map((n) => n[0])
            .join('')}
        </Avatar>
        <Stack gap={2} style={{ flex: 1 }}>
          <Group gap="xs">
            <Text fw={500} size="sm">
              {player.name}
            </Text>
            <PositionBadge position={position} size="xs" />
          </Group>
          <Text size="xs" c="dimmed">
            {player.teamAbbrev}
          </Text>
        </Stack>
        {pointsEarned !== undefined && (
          <PointsBadge points={pointsEarned} size="sm" />
        )}
        {actions.length > 0 && onAction && (
          <Group gap={4}>
            {actions.map((action) => (
              <Tooltip key={action} label={ACTION_CONFIG[action].label}>
                <ActionIcon
                  variant="light"
                  size="sm"
                  color={action === 'activate' ? 'green' : 'gray'}
                  onClick={(e: { stopPropagation: () => void }) => {
                    e.stopPropagation();
                    onAction(action);
                  }}
                  aria-label={ACTION_CONFIG[action].label}
                >
                  {ACTION_CONFIG[action].icon}
                </ActionIcon>
              </Tooltip>
            ))}
          </Group>
        )}
      </Group>
    </Card>
  );
}
