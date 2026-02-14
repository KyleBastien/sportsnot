import { Badge } from '@mantine/core';
import type { MantineSize } from '@mantine/core';

export type PositionType =
  | 'F'
  | 'D'
  | 'G'
  | 'IR_F'
  | 'IR_D'
  | 'C'
  | 'LW'
  | 'RW';

export interface PositionBadgeProps {
  position: PositionType;
  size?: MantineSize;
  variant?: 'filled' | 'outline' | 'light';
}

const POSITION_COLORS: Record<PositionType, string> = {
  F: 'blue',
  D: 'green',
  G: 'orange',
  IR_F: 'red',
  IR_D: 'red',
  C: 'indigo',
  LW: 'cyan',
  RW: 'teal',
};

export function PositionBadge({
  position,
  size = 'sm',
  variant = 'light',
}: PositionBadgeProps) {
  return (
    <Badge size={size} variant={variant} color={POSITION_COLORS[position]}>
      {position}
    </Badge>
  );
}
