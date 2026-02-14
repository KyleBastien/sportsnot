/* eslint-disable no-undef */
import { Badge, Text } from '@mantine/core';
import type { MantineSize } from '@mantine/core';
import { useEffect, useRef, useState } from 'react';

export interface PointsBadgeProps {
  points: number;
  size?: MantineSize;
  animate?: boolean;
  delta?: number;
  variant?: 'filled' | 'outline' | 'subtle';
}

function getColor(points: number): string {
  if (points <= 0) return 'gray';
  return 'blue';
}

export function PointsBadge({
  points,
  size = 'md',
  animate = false,
  delta,
  variant = 'filled',
}: PointsBadgeProps) {
  const [pulsing, setPulsing] = useState(false);
  const prevPoints = useRef(points);

  useEffect(() => {
    if (animate && prevPoints.current !== points) {
      setPulsing(true);
      const timer = window.setTimeout(() => setPulsing(false), 200);
      prevPoints.current = points;
      return () => window.clearTimeout(timer);
    }
    prevPoints.current = points;
    return undefined;
  }, [points, animate]);

  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
      <style>{`
        @keyframes pointsPulse {
          0% { transform: scale(1); }
          50% { transform: scale(1.15); }
          100% { transform: scale(1); }
        }
      `}</style>
      <Badge
        size={size}
        variant={variant}
        color={getColor(points)}
        style={pulsing ? { animation: 'pointsPulse 200ms ease-in-out' } : undefined}
      >
        {points}
      </Badge>
      {delta != null && delta !== 0 && (
        <Text
          size="xs"
          c={delta > 0 ? 'green' : 'red'}
          fw={700}
          style={{ animation: 'deltaFade 2s ease-out forwards' }}
        >
          {delta > 0 ? `+${delta}` : delta}
        </Text>
      )}
    </span>
  );
}
