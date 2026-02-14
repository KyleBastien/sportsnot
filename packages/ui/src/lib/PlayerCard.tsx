import { Card, Group, Text, Badge, Avatar, Stack } from '@mantine/core';
import type { NHLPlayer } from '@sportsnot/types';

export interface PlayerCardProps {
  player: NHLPlayer;
  points?: number;
  isSelected?: boolean;
  onSelect?: (player: NHLPlayer) => void;
}

export function PlayerCard({
  player,
  points,
  isSelected = false,
  onSelect,
}: PlayerCardProps) {
  return (
    <Card
      shadow="sm"
      padding="sm"
      radius="md"
      withBorder
      style={{
        cursor: onSelect ? 'pointer' : 'default',
        borderColor: isSelected ? 'var(--mantine-color-blue-6)' : undefined,
        borderWidth: isSelected ? 2 : 1,
      }}
      onClick={() => onSelect?.(player)}
    >
      <Group>
        <Avatar src={player.headshot} size="lg" radius="md">
          {player.firstName[0]}
          {player.lastName[0]}
        </Avatar>
        <Stack gap={2} style={{ flex: 1 }}>
          <Group justify="space-between">
            <Text fw={500}>
              {player.firstName} {player.lastName}
            </Text>
            <Badge variant="light">{player.primaryPosition.abbreviation}</Badge>
          </Group>
          <Group gap="xs">
            {player.currentTeam && (
              <Text size="sm" c="dimmed">
                {player.currentTeam.abbreviation}
              </Text>
            )}
            {player.primaryNumber && (
              <Text size="sm" c="dimmed">
                #{player.primaryNumber}
              </Text>
            )}
          </Group>
        </Stack>
        {points !== undefined && (
          <Badge size="lg" variant="filled" color="green">
            {points} pts
          </Badge>
        )}
      </Group>
    </Card>
  );
}
