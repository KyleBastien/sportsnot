import { Group, Text } from '@mantine/core';
import type { ReactNode } from 'react';

export interface DataRowProps {
  label: string;
  value: ReactNode;
}

export function DataRow({ label, value }: DataRowProps) {
  return (
    <Group justify="space-between" gap="xs">
      <Text size="sm" c="dimmed">
        {label}
      </Text>
      {typeof value === 'string' || typeof value === 'number' ? (
        <Text size="sm" fw={500}>
          {value}
        </Text>
      ) : (
        value
      )}
    </Group>
  );
}
