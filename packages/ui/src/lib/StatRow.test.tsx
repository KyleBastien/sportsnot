import { describe, it, expect, afterEach } from '@rstest/core';
import { render, screen, cleanup } from '@testing-library/react';
import { MantineProvider } from '@mantine/core';
import { StatRow } from './StatRow';

afterEach(cleanup);

function renderWithMantine(ui: React.ReactElement) {
  return render(<MantineProvider>{ui}</MantineProvider>);
}

describe('StatRow', () => {
  it('renders label and string value', () => {
    renderWithMantine(<StatRow label="Goals" value="40" />);
    expect(screen.getByText('Goals')).toBeTruthy();
    expect(screen.getByText('40')).toBeTruthy();
  });

  it('renders label and numeric value', () => {
    renderWithMantine(<StatRow label="Points" value={99} />);
    expect(screen.getByText('Points')).toBeTruthy();
    expect(screen.getByText('99')).toBeTruthy();
  });

  it('renders with highlight state (bold and blue)', () => {
    renderWithMantine(<StatRow label="Goals" value={50} highlight />);
    expect(screen.getByText('50')).toBeTruthy();
    expect(screen.getByText('Goals')).toBeTruthy();
  });

  it('renders up trend icon', () => {
    renderWithMantine(<StatRow label="Goals" value={10} trend="up" />);
    expect(screen.getByText('▲')).toBeTruthy();
  });

  it('renders down trend icon', () => {
    renderWithMantine(<StatRow label="Goals" value={10} trend="down" />);
    expect(screen.getByText('▼')).toBeTruthy();
  });

  it('renders neutral trend icon', () => {
    renderWithMantine(<StatRow label="Goals" value={10} trend="neutral" />);
    expect(screen.getByText('▸')).toBeTruthy();
  });

  it('does not render trend icon when trend is not provided', () => {
    renderWithMantine(<StatRow label="Goals" value={10} />);
    expect(screen.queryByText('▲')).toBeNull();
    expect(screen.queryByText('▼')).toBeNull();
    expect(screen.queryByText('▸')).toBeNull();
  });

  it('renders in compact mode', () => {
    renderWithMantine(<StatRow label="Assists" value={30} compact />);
    expect(screen.getByText('Assists')).toBeTruthy();
    expect(screen.getByText('30')).toBeTruthy();
  });
});
