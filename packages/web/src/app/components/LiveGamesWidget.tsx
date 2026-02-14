import { useState, useMemo } from 'react';
import {
  Title,
  Text,
  Group,
  ScrollArea,
  SimpleGrid,
  Loader,
  Center,
  Collapse,
  Badge,
} from '@mantine/core';
import { useMediaQuery } from '@mantine/hooks';
import { useQuery } from '@tanstack/react-query';
import { getScoresNow } from '@sportsnot/nhl-api';
import { supabase } from '@sportsnot/supabase';
import { GameCard } from '@sportsnot/ui';
import type { NHLGame } from '@sportsnot/types';
import { useAuthContext } from '../context/AuthContext';

interface RosteredPlayer {
  playerName: string;
  teamAbbrev: string;
  position: string;
}

function mapGameStatus(
  state: NHLGame['gameState']
): 'upcoming' | 'live' | 'final' {
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

/** Fetches the current user's rostered players with team abbreviations for a given league. */
function useRosteredPlayers(leagueId: string | undefined) {
  const { user } = useAuthContext();

  return useQuery({
    queryKey: ['rostered-players-teams', leagueId, user?.id],
    queryFn: async () => {
      // Get league member ID and current round
      const { data: member } = await supabase
        .from('league_members')
        .select('id')
        .eq('league_id', leagueId!)
        .eq('user_id', user!.id)
        .single();
      if (!member) return [];

      const { data: league } = await supabase
        .from('leagues')
        .select('current_round')
        .eq('id', leagueId!)
        .single();
      if (!league) return [];

      const currentSeason = '20242025'; // TODO: derive from NHL API

      // Get roster slots with player IDs
      const { data: roster } = await supabase
        .from('rosters')
        .select('player_id, team_id, position')
        .eq('league_member_id', member.id)
        .eq('round', league.current_round)
        .eq('is_active', true);
      if (!roster?.length) return [];

      const playerIds = roster
        .filter((r) => r.player_id != null)
        .map((r) => r.player_id!);
      if (!playerIds.length) return [];

      // Get player names and team abbreviations from cache
      const { data: players } = await supabase
        .from('player_stats_cache')
        .select('player_id, player_name, team_abbreviation, position')
        .eq('nhl_season', currentSeason)
        .eq('playoff_round', league.current_round)
        .in('player_id', playerIds);

      return (players ?? []).map((p) => ({
        playerName: p.player_name ?? 'Unknown',
        teamAbbrev: p.team_abbreviation ?? '',
        position: p.position ?? '',
      })) as RosteredPlayer[];
    },
    enabled: !!leagueId && !!user,
    staleTime: 1000 * 60 * 2,
  });
}

interface LiveGamesWidgetProps {
  leagueId?: string;
}

export function LiveGamesWidget({ leagueId }: LiveGamesWidgetProps) {
  const isMobile = useMediaQuery('(max-width: 768px)');
  const [expandedGameId, setExpandedGameId] = useState<number | null>(null);

  const { data: games, isLoading } = useQuery({
    queryKey: ['nhl-scores-now'],
    queryFn: getScoresNow,
    refetchInterval: 30000,
  });

  const { data: rosteredPlayers } = useRosteredPlayers(leagueId);

  // Build a map of team abbreviation → rostered players in that team
  const teamPlayersMap = useMemo(() => {
    const map = new Map<string, RosteredPlayer[]>();
    if (!rosteredPlayers) return map;
    for (const p of rosteredPlayers) {
      const existing = map.get(p.teamAbbrev) ?? [];
      existing.push(p);
      map.set(p.teamAbbrev, existing);
    }
    return map;
  }, [rosteredPlayers]);

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

  // Determine rostered players per game
  function getRosteredPlayersForGame(game: NHLGame): RosteredPlayer[] {
    const homePlayers = teamPlayersMap.get(game.homeTeam.abbreviation) ?? [];
    const awayPlayers = teamPlayersMap.get(game.awayTeam.abbreviation) ?? [];
    return [...homePlayers, ...awayPlayers];
  }

  const gameCards = games.map((game) => {
    const gamePlayers = getRosteredPlayersForGame(game);
    const hasRosteredPlayers = gamePlayers.length > 0;
    const isExpanded = expandedGameId === game.id;

    return (
      <div key={game.id}>
        <GameCard
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
          startTime={
            game.gameState === 'FUT' || game.gameState === 'PRE'
              ? new Date(game.startTimeUTC)
              : undefined
          }
          highlight={hasRosteredPlayers}
          highlightReason={
            hasRosteredPlayers
              ? `${gamePlayers.length} rostered player${gamePlayers.length > 1 ? 's' : ''}`
              : undefined
          }
          onClick={
            hasRosteredPlayers
              ? () => setExpandedGameId(isExpanded ? null : game.id)
              : undefined
          }
        />
        {hasRosteredPlayers && (
          <Collapse in={isExpanded}>
            <div
              style={{
                padding: '8px 12px',
                borderLeft: '2px solid var(--mantine-color-blue-5)',
                marginTop: 4,
                borderRadius: 4,
              }}
            >
              <Text size="xs" fw={600} mb={4}>
                Your rostered players:
              </Text>
              {gamePlayers.map((p) => (
                <Group key={p.playerName} gap={4} mb={2}>
                  <Badge size="xs" variant="light">
                    {p.position}
                  </Badge>
                  <Text size="xs">
                    {p.playerName} ({p.teamAbbrev})
                  </Text>
                </Group>
              ))}
            </div>
          </Collapse>
        )}
      </div>
    );
  });

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
