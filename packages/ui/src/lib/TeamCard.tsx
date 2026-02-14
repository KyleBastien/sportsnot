import { Card, Group, Text, Badge, Avatar, Stack } from '@mantine/core';

export interface TeamCardProps {
  teamName: string;
  teamAbbrev: string;
  logoUrl?: string;
  record?: { wins: number; losses: number };
  points?: number;
  isEliminated?: boolean;
  onClick?: () => void;
  size?: 'sm' | 'md' | 'lg';
}

const sizeMap = {
  sm: {
    padding: 'xs' as const,
    avatar: 'md' as const,
    titleSize: 'sm',
    gap: 2,
  },
  md: {
    padding: 'sm' as const,
    avatar: 'lg' as const,
    titleSize: 'md',
    gap: 4,
  },
  lg: {
    padding: 'md' as const,
    avatar: 'xl' as const,
    titleSize: 'lg',
    gap: 6,
  },
};

export function TeamCard({
  teamName,
  teamAbbrev,
  logoUrl,
  record,
  points,
  isEliminated = false,
  onClick,
  size = 'md',
}: TeamCardProps) {
  const s = sizeMap[size];

  return (
    <Card
      shadow="sm"
      padding={s.padding}
      radius="md"
      withBorder
      style={{
        cursor: onClick ? 'pointer' : 'default',
        opacity: isEliminated ? 0.5 : 1,
      }}
      onClick={onClick}
    >
      <Group>
        <Avatar src={logoUrl} size={s.avatar} radius="md">
          {teamAbbrev}
        </Avatar>
        <Stack gap={s.gap} style={{ flex: 1 }}>
          <Text
            fw={500}
            size={s.titleSize}
            td={isEliminated ? 'line-through' : undefined}
          >
            {teamName}
          </Text>
          <Group gap="xs">
            <Text size="sm" c="dimmed">
              {teamAbbrev}
            </Text>
            {record && (
              <Text size="sm" c="dimmed">
                {record.wins}W–{record.losses}L
              </Text>
            )}
          </Group>
        </Stack>
        {points !== undefined && (
          <Badge
            size="lg"
            variant="filled"
            color={isEliminated ? 'gray' : 'green'}
          >
            {points} pts
          </Badge>
        )}
      </Group>
    </Card>
  );
}
