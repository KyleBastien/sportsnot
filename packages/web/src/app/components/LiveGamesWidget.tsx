import {
  Title,
  Text,
  Group,
  ScrollArea,
  SimpleGrid,
  Loader,
  Center,
} from '@mantine/core';
import { useMediaQuery } from '@mantine/hooks';
import { useQuery } from '@tanstack/react-query';
import { getScoresNow } from '@sportsnot/nhl-api';
import { GameCard } from '@sportsnot/ui';
import type { NHLGame } from '@sportsnot/types';

function mapGameStatus(state: NHLGame['gameState']): 'upcoming' | 'live' | 'final' {
  if (state === 'LIVE') return 'live';
  if (state === 'FINAL' || state === 'OFF') return 'final';
  return 'upcoming';
}

function formatPeriod(period?: number): string | undefined {
  if (!period) return undefined;
  if (period === 1) return '1st';
  if (period === 2) return '2nd';
  if (period === 3) return '3rd';
  return `OT${period > 4 ? period - 3 : ''}`;
}

export function LiveGamesWidget() {
  const isMobile = useMediaQuery('(max-width: 768px)');
  const { data: games, isLoading } = useQuery({
    queryKey: ['nhl-scores-now'],
    queryFn: getScoresNow,
    refetchInterval: 30000,
  });

  if (isLoading) {
    return (
      <Center py="md">
        <Loader size="sm" />
      </Center>
    );
  }

  if (!games?.length) {
    return null;
  }

  const gameCards = games.map((game) => (
    <GameCard
      key={game.id}
      homeTeam={{
        abbrev: game.homeTeam.abbreviation,
        score: game.homeTeam.score ?? 0,
      }}
      awayTeam={{
        abbrev: game.awayTeam.abbreviation,
        score: game.awayTeam.score ?? 0,
      }}
      status={mapGameStatus(game.gameState)}
      period={formatPeriod(game.period)}
      timeRemaining={game.periodTimeRemaining}
      startTime={game.gameState === 'FUT' || game.gameState === 'PRE' ? new Date(game.startTimeUTC) : undefined}
    />
  ));

  return (
    <div>
      <Group justify="space-between" mb="sm">
        <Title order={4}>NHL Scores</Title>
        <Text size="xs" c="dimmed">
          Updates every 30s
        </Text>
      </Group>

      {isMobile ? (
        <ScrollArea type="auto">
          <Group gap="sm" wrap="nowrap" style={{ minWidth: 'max-content' }}>
            {gameCards.map((card, i) => (
              <div key={i} style={{ minWidth: 200 }}>
                {card}
              </div>
            ))}
          </Group>
        </ScrollArea>
      ) : (
        <SimpleGrid cols={{ base: 2, sm: 3, md: 4, lg: 5 }}>
          {gameCards}
        </SimpleGrid>
      )}
    </div>
  );
}
