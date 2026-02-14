import { describe, it, expect, afterEach } from '@rstest/core';
import { render, screen, cleanup } from '@testing-library/react';
import { MantineProvider } from '@mantine/core';
import { PointsBadge } from './PointsBadge';

afterEach(cleanup);

function renderWithMantine(ui: React.ReactElement) {
  return render(<MantineProvider>{ui}</MantineProvider>);
}

describe('PointsBadge', () => {
  it('renders points value', () => {
    renderWithMantine(<PointsBadge points={42} />);
    expect(screen.getByText('42')).toBeTruthy();
  });

  it('renders zero points', () => {
    renderWithMantine(<PointsBadge points={0} />);
    expect(screen.getByText('0')).toBeTruthy();
  });

  it('renders negative points', () => {
    renderWithMantine(<PointsBadge points={-5} />);
    expect(screen.getByText('-5')).toBeTruthy();
  });

  it('shows positive delta', () => {
    renderWithMantine(<PointsBadge points={10} delta={3} />);
    expect(screen.getByText('+3')).toBeTruthy();
  });

  it('shows negative delta', () => {
    renderWithMantine(<PointsBadge points={10} delta={-2} />);
    expect(screen.getByText('-2')).toBeTruthy();
  });

  it('does not show delta when delta is zero', () => {
    renderWithMantine(<PointsBadge points={10} delta={0} />);
    expect(screen.queryByText('+0')).toBeNull();
  });

  it('does not show delta when not provided', () => {
    renderWithMantine(<PointsBadge points={10} />);
    // No delta text should be present
    expect(screen.queryByText(/^\+/)).toBeNull();
    expect(screen.queryByText(/^-/)).toBeNull();
  });

  it('accepts animate prop without error', () => {
    renderWithMantine(<PointsBadge points={10} animate />);
    expect(screen.getByText('10')).toBeTruthy();
  });

  it('accepts size prop', () => {
    renderWithMantine(<PointsBadge points={5} size="lg" />);
    expect(screen.getByText('5')).toBeTruthy();
  });

  it('accepts variant prop', () => {
    renderWithMantine(<PointsBadge points={5} variant="outline" />);
    expect(screen.getByText('5')).toBeTruthy();
  });
});
