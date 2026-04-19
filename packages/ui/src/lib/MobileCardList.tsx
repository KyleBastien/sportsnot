import { Stack, Text } from '@mantine/core';
import type { ReactNode } from 'react';

export interface MobileCardListProps {
  children: ReactNode;
  emptyMessage?: string;
  gap?: string | number;
}

export function MobileCardList({
  children,
  emptyMessage = 'No data available',
  gap = 'xs',
}: MobileCardListProps) {
  const hasChildren = Array.isArray(children)
    ? children.filter(Boolean).length > 0
    : !!children;

  if (!hasChildren) {
    return (
      <Text c="dimmed" ta="center" py="md">
        {emptyMessage}
      </Text>
    );
  }

  return <Stack gap={gap}>{children}</Stack>;
}
