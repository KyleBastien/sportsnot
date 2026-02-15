/* eslint-disable no-undef */
import { useState } from 'react';
import {
  ActionIcon,
  Badge,
  Button,
  Drawer,
  Group,
  Stack,
  Text,
  Title,
  Divider,
} from '@mantine/core';
import { useMockData } from '../MockDataProvider';

const ROUND_LABELS: Record<number, string> = {
  1: 'Round 1 — First Round',
  2: 'Round 2 — Second Round',
  3: 'Conference Finals',
  4: 'Stanley Cup Final',
};

function formatDate(iso: string): string {
  const d = new Date(iso + 'T12:00:00Z');
  return d.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    timeZone: 'UTC',
  });
}

export function SimulationControlPanel() {
  const { state, dispatch } = useMockData();
  const [opened, setOpened] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);

  const {
    simulationDate,
    currentRound,
    roundComplete,
    seasonComplete,
  } = state;

  const handleAdvanceDay = () => {
    dispatch({ type: 'ADVANCE_DAY' });
  };

  const handleAdvanceRound = () => {
    dispatch({ type: 'ADVANCE_ROUND' });
  };

  const handleReset = () => {
    if (confirmReset) {
      dispatch({ type: 'RESET_ALL' });
      // Clear any mock-mode localStorage entries (defensive cleanup)
      const keysToRemove: string[] = [];
      for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        if (key && key.startsWith('mock-')) {
          keysToRemove.push(key);
        }
      }
      keysToRemove.forEach((key) => localStorage.removeItem(key));
      setConfirmReset(false);
    } else {
      setConfirmReset(true);
      setTimeout(() => setConfirmReset(false), 3000);
    }
  };

  const handleDumpState = () => {
    // eslint-disable-next-line no-console
    console.log(JSON.stringify(state, null, 2));
  };

  return (
    <>
      {/* FAB — bottom-right */}
      <ActionIcon
        size="xl"
        radius="xl"
        color="orange"
        variant="filled"
        onClick={() => setOpened(true)}
        style={{
          position: 'fixed',
          bottom: 24,
          right: 24,
          zIndex: 999,
          width: 56,
          height: 56,
          fontSize: 24,
          boxShadow: '0 4px 12px rgba(0,0,0,0.25)',
        }}
        aria-label="Open simulation controls"
      >
        🧪
      </ActionIcon>

      {/* Drawer panel */}
      <Drawer
        opened={opened}
        onClose={() => setOpened(false)}
        title={
          <Group gap="xs">
            <Title order={4}>Simulation Controls</Title>
            <Badge color="orange" size="sm">
              Mock
            </Badge>
          </Group>
        }
        position="right"
        size="sm"
        overlayProps={{ opacity: 0.3 }}
        styles={{
          body: { paddingTop: 8 },
        }}
      >
        <Stack gap="md">
          {/* Current date */}
          <div>
            <Text size="xs" c="dimmed" tt="uppercase" fw={600}>
              Simulated Date
            </Text>
            <Text size="lg" fw={700}>
              {formatDate(simulationDate)}
            </Text>
          </div>

          {/* Current round */}
          <div>
            <Text size="xs" c="dimmed" tt="uppercase" fw={600}>
              Current Round
            </Text>
            <Text size="md" fw={600}>
              {ROUND_LABELS[currentRound] ?? `Round ${currentRound}`}
            </Text>
          </div>

          {/* Status badges */}
          <Group gap="xs">
            {roundComplete && !seasonComplete && (
              <Badge color="blue" variant="light">
                Round Complete
              </Badge>
            )}
            {seasonComplete && (
              <Badge color="yellow" variant="filled">
                🏆 Season Complete
              </Badge>
            )}
          </Group>

          <Divider />

          {/* Next Day button */}
          <Button
            fullWidth
            size="md"
            color="blue"
            onClick={handleAdvanceDay}
            disabled={roundComplete || seasonComplete}
          >
            {roundComplete && !seasonComplete
              ? 'Round complete — advance to next round'
              : seasonComplete
                ? '🏆 Season Complete'
                : 'Next Day →'}
          </Button>

          {/* Advance Round button */}
          <Button
            fullWidth
            size="md"
            color="teal"
            variant="outline"
            onClick={handleAdvanceRound}
            disabled={!roundComplete || seasonComplete}
          >
            Advance Round →
          </Button>

          <Divider />

          {/* Reset Season */}
          <Button
            fullWidth
            variant="outline"
            color="red"
            onClick={handleReset}
          >
            {confirmReset
              ? 'Click again to confirm reset'
              : 'Reset All Mock Data'}
          </Button>

          {/* Dump State */}
          <Button
            fullWidth
            variant="subtle"
            color="gray"
            onClick={handleDumpState}
          >
            Dump State to Console
          </Button>
        </Stack>
      </Drawer>
    </>
  );
}
