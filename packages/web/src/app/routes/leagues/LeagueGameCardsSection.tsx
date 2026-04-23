import {
  Alert,
  Card,
  Divider,
  SimpleGrid,
  Skeleton,
  Stack,
  Text,
  Title,
} from '@mantine/core';
import type { WidgetSnapshot } from '@sportsnot/widget-api';
import {
  buildWidgetGameCards,
  formatWidgetGameHeader,
  formatWidgetTeamLines,
} from './widgetScheduleLayout';

interface LeagueGameCardsSectionProps {
  snapshot: WidgetSnapshot | null | undefined;
  isLoading: boolean;
  error: Error | null;
}

export function LeagueGameCardsSection({
  snapshot,
  isLoading,
  error,
}: LeagueGameCardsSectionProps) {
  return (
    <Stack gap="md">
      <Title order={4}>Today's Games</Title>

      {isLoading ? (
        <SimpleGrid cols={{ base: 1, sm: 2, xl: 3 }}>
          {Array.from({ length: 3 }, (_, index) => (
            <Card
              key={`league-game-skeleton-${index}`}
              shadow="sm"
              padding="md"
              radius="md"
              withBorder
            >
              <Stack gap="sm">
                <Skeleton height={16} radius="sm" />
                <Skeleton height={12} radius="sm" />
                <Skeleton height={12} radius="sm" width="75%" />
              </Stack>
            </Card>
          ))}
        </SimpleGrid>
      ) : error ? (
        <Alert color="red" title="Today's games unavailable">
          {error.message}
        </Alert>
      ) : !snapshot || snapshot.games.length === 0 ? (
        <Card shadow="sm" padding="md" radius="md" withBorder>
          <Text c="dimmed">No games today</Text>
        </Card>
      ) : (
        <SimpleGrid cols={{ base: 1, sm: 2, xl: 3 }}>
          {buildWidgetGameCards(snapshot).map((section) => (
            <Card
              key={section.game.id}
              shadow="sm"
              padding="md"
              radius="md"
              withBorder
            >
              <Stack gap="sm">
                <Text fw={700}>{formatWidgetGameHeader(section.game)}</Text>

                {section.fantasyTeams.length === 0 ? (
                  <Text size="sm" c="dimmed">
                    No drafted teams in this game
                  </Text>
                ) : (
                  <Stack gap="sm">
                    {section.fantasyTeams.map((team, index) => (
                      <Stack key={team.name} gap={6}>
                        {index > 0 ? <Divider /> : null}
                        <Text size="sm" fw={600}>
                          {team.name}
                        </Text>
                        {formatWidgetTeamLines(team).map((line, lineIndex) => (
                          <Text
                            key={`${team.name}-${lineIndex}`}
                            size="xs"
                            c="dimmed"
                          >
                            {line}
                          </Text>
                        ))}
                      </Stack>
                    ))}
                  </Stack>
                )}
              </Stack>
            </Card>
          ))}
        </SimpleGrid>
      )}
    </Stack>
  );
}
