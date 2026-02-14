import { describe, it, expect, afterEach } from '@rstest/core';
import { render, screen, cleanup } from '@testing-library/react';
import { MantineProvider } from '@mantine/core';
import { PositionBadge } from './PositionBadge';

afterEach(cleanup);

function renderWithMantine(ui: React.ReactElement) {
  return render(<MantineProvider>{ui}</MantineProvider>);
}

describe('PositionBadge', () => {
  it('renders F position badge', () => {
    renderWithMantine(<PositionBadge position="F" />);
    expect(screen.getByText('F')).toBeTruthy();
  });

  it('renders D position badge', () => {
    renderWithMantine(<PositionBadge position="D" />);
    expect(screen.getByText('D')).toBeTruthy();
  });

  it('renders G position badge', () => {
    renderWithMantine(<PositionBadge position="G" />);
    expect(screen.getByText('G')).toBeTruthy();
  });

  it('renders IR_F position badge', () => {
    renderWithMantine(<PositionBadge position="IR_F" />);
    expect(screen.getByText('IR_F')).toBeTruthy();
  });

  it('renders IR_D position badge', () => {
    renderWithMantine(<PositionBadge position="IR_D" />);
    expect(screen.getByText('IR_D')).toBeTruthy();
  });

  it('renders C position badge', () => {
    renderWithMantine(<PositionBadge position="C" />);
    expect(screen.getByText('C')).toBeTruthy();
  });

  it('renders LW position badge', () => {
    renderWithMantine(<PositionBadge position="LW" />);
    expect(screen.getByText('LW')).toBeTruthy();
  });

  it('renders RW position badge', () => {
    renderWithMantine(<PositionBadge position="RW" />);
    expect(screen.getByText('RW')).toBeTruthy();
  });

  it('applies light variant by default', () => {
    const { container } = renderWithMantine(<PositionBadge position="F" />);
    const badge = container.querySelector('.mantine-Badge-root');
    expect(badge).toBeTruthy();
    expect((badge as HTMLElement).getAttribute('data-variant')).toBe('light');
  });

  it('applies filled variant when specified', () => {
    const { container } = renderWithMantine(
      <PositionBadge position="F" variant="filled" />
    );
    const badge = container.querySelector('.mantine-Badge-root');
    expect((badge as HTMLElement).getAttribute('data-variant')).toBe('filled');
  });

  it('applies outline variant when specified', () => {
    const { container } = renderWithMantine(
      <PositionBadge position="D" variant="outline" />
    );
    const badge = container.querySelector('.mantine-Badge-root');
    expect((badge as HTMLElement).getAttribute('data-variant')).toBe('outline');
  });
});
