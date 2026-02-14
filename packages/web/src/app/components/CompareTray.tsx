import { useState } from 'react';
import {
  Affix,
  Badge,
  Button,
  CloseButton,
  Group,
  Paper,
  Text,
  Transition,
  Avatar,
  Stack,
} from '@mantine/core';
import { useCompareContext } from '../context/CompareContext';
import { ComparisonModal } from './ComparisonModal';

export function CompareTray() {
  const { players, removePlayer, clearAll } = useCompareContext();
  const [modalOpened, setModalOpened] = useState(false);

  const visible = players.length > 0;

  return (
    <>
    <ComparisonModal opened={modalOpened} onClose={() => setModalOpened(false)} />
    <Affix position={{ bottom: 80, left: 0, right: 0 }} zIndex={200}>
      <Transition transition="slide-up" mounted={visible}>
        {(styles) => (
          <Paper
            shadow="xl"
            p="sm"
            mx="md"
            radius="md"
            withBorder
            style={styles}
          >
            <Group justify="space-between" wrap="nowrap">
              <Group gap="sm" wrap="nowrap" style={{ overflow: 'auto' }}>
                {players.map((player) => (
                  <Group key={player.playerId} gap={4} wrap="nowrap">
                    <Avatar
                      src={player.headshot}
                      alt={player.name}
                      size="sm"
                      radius="xl"
                    />
                    <Stack gap={0}>
                      <Text size="xs" fw={500} truncate>
                        {player.name}
                      </Text>
                      <Text size="xs" c="dimmed">
                        {player.teamAbbrev}
                      </Text>
                    </Stack>
                    <CloseButton
                      size="xs"
                      aria-label={`Remove ${player.name}`}
                      onClick={() => removePlayer(player.playerId)}
                    />
                  </Group>
                ))}
              </Group>

              <Group gap="xs" wrap="nowrap">
                <Button
                  variant="subtle"
                  size="xs"
                  color="gray"
                  onClick={clearAll}
                >
                  Clear All
                </Button>
                <Button size="xs" disabled={players.length < 2} onClick={() => setModalOpened(true)}>
                  <Group gap={4}>
                    Compare
                    <Badge size="xs" circle>
                      {players.length}
                    </Badge>
                  </Group>
                </Button>
              </Group>
            </Group>
          </Paper>
        )}
      </Transition>
    </Affix>
    </>
  );
}
