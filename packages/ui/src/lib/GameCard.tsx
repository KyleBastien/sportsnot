import { Card, Group, Text, Badge, Stack, Avatar } from '@mantine/core';
import { LiveIndicator } from './LiveIndicator';

export interface GameCardTeam {
  abbrev: string;
  score: number;
  logoUrl?: string;
}

export interface GameCardProps {
  homeTeam: GameCardTeam;
  awayTeam: GameCardTeam;
  status: 'upcoming' | 'live' | 'final';
  period?: string;
  timeRemaining?: string;
  startTime?: Date;
  highlight?: boolean;
  highlightReason?: string;
  onClick?: () => void;
}

function formatStartTime(date: Date): string {
  return date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
}

function TeamRow({
  team,
  isWinner,
}: {
  team: GameCardTeam;
  isWinner: boolean;
}) {
  return (
    <Group gap="xs">
      <Avatar src={team.logoUrl} size="sm" radius="sm">
        {team.abbrev}
      </Avatar>
      <Text fw={isWinner ? 700 : 400} size="sm" style={{ flex: 1 }}>
        {team.abbrev}
      </Text>
      <Text fw={isWinner ? 700 : 400} size="sm">
        {team.score}
      </Text>
    </Group>
  );
}

export function GameCard({
  homeTeam,
  awayTeam,
  status,
  period,
  timeRemaining,
  startTime,
  highlight = false,
  highlightReason,
  onClick,
}: GameCardProps) {
  const awayWins = status === 'final' && awayTeam.score > homeTeam.score;
  const homeWins = status === 'final' && homeTeam.score > awayTeam.score;

  return (
    <Card
      shadow="sm"
      padding="sm"
      radius="md"
      withBorder
      style={{
        cursor: onClick ? 'pointer' : 'default',
        borderColor: highlight ? 'var(--mantine-color-blue-5)' : undefined,
        borderWidth: highlight ? 2 : undefined,
      }}
      onClick={onClick}
    >
      <Stack gap={6}>
        <TeamRow team={awayTeam} isWinner={awayWins} />
        <TeamRow team={homeTeam} isWinner={homeWins} />

        <Group gap="xs" justify="center" mt={4}>
          {status === 'live' && (
            <>
              <LiveIndicator isLive size="sm" />
              {period && (
                <Text size="xs" c="dimmed">
                  {period}
                </Text>
              )}
              {timeRemaining && (
                <Text size="xs" c="dimmed">
                  {timeRemaining}
                </Text>
              )}
            </>
          )}

          {status === 'final' && (
            <Badge color="gray" variant="light" size="sm">
              FINAL
            </Badge>
          )}

          {status === 'upcoming' && startTime && (
            <Text size="xs" c="dimmed">
              {formatStartTime(startTime)}
            </Text>
          )}
        </Group>

        {highlight && highlightReason && (
          <Text size="xs" c="blue" ta="center">
            {highlightReason}
          </Text>
        )}
      </Stack>
    </Card>
  );
}
