import type { ReactNode } from 'react';

export function PlayerCard(props: { children?: ReactNode }) {
  return <div>{props.children}</div>;
}

export function MobileCardList(props: { children?: ReactNode }) {
  return <div data-testid="mobile-card-list">{props.children}</div>;
}

export function DataRow(props: { label: string; value?: ReactNode }) {
  return (
    <div>
      <span>{props.label}</span>
      <span>{props.value}</span>
    </div>
  );
}

export function useIsMobile() {
  return false;
}

export const vars = new Proxy(
  {},
  {
    get: () => '',
  }
) as unknown as Record<string, string>;

export const sprinkles = (() => '') as unknown as (
  ...args: unknown[]
) => string;
