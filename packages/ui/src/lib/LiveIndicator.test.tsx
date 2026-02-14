import { describe, it, expect, afterEach } from '@rstest/core';
import { render, screen, cleanup } from '@testing-library/react';
import { MantineProvider } from '@mantine/core';
import { LiveIndicator } from './LiveIndicator';

afterEach(cleanup);

function renderWithMantine(ui: React.ReactElement) {
  return render(<MantineProvider>{ui}</MantineProvider>);
}

describe('LiveIndicator', () => {
  it('renders LIVE badge when isLive is true', () => {
    renderWithMantine(<LiveIndicator isLive />);
    expect(screen.getByText('LIVE')).toBeTruthy();
  });

  it('renders OFFLINE badge when isLive is false', () => {
    renderWithMantine(<LiveIndicator isLive={false} />);
    expect(screen.getByText('OFFLINE')).toBeTruthy();
  });

  it('does not show LIVE when offline', () => {
    renderWithMantine(<LiveIndicator isLive={false} />);
    expect(screen.queryByText('LIVE')).toBeNull();
  });

  it('does not show OFFLINE when live', () => {
    renderWithMantine(<LiveIndicator isLive />);
    expect(screen.queryByText('OFFLINE')).toBeNull();
  });

  it('shows timestamp when showTimestamp is true and lastUpdated is provided', () => {
    const recent = new Date(Date.now() - 30 * 1000);
    renderWithMantine(
      <LiveIndicator isLive showTimestamp lastUpdated={recent} />
    );
    expect(screen.getByText('Updated just now')).toBeTruthy();
  });

  it('shows minutes ago for older timestamps', () => {
    const fiveMinAgo = new Date(Date.now() - 5 * 60 * 1000);
    renderWithMantine(
      <LiveIndicator isLive showTimestamp lastUpdated={fiveMinAgo} />
    );
    expect(screen.getByText('Updated 5m ago')).toBeTruthy();
  });

  it('shows hours ago for much older timestamps', () => {
    const twoHoursAgo = new Date(Date.now() - 2 * 60 * 60 * 1000);
    renderWithMantine(
      <LiveIndicator isLive showTimestamp lastUpdated={twoHoursAgo} />
    );
    expect(screen.getByText('Updated 2h ago')).toBeTruthy();
  });

  it('hides timestamp when showTimestamp is false', () => {
    const recent = new Date();
    renderWithMantine(
      <LiveIndicator isLive lastUpdated={recent} />
    );
    expect(screen.queryByText(/Updated/)).toBeNull();
  });

  it('hides timestamp when lastUpdated is not provided', () => {
    renderWithMantine(<LiveIndicator isLive showTimestamp />);
    expect(screen.queryByText(/Updated/)).toBeNull();
  });

  it('shows timestamp in offline mode', () => {
    const recent = new Date(Date.now() - 30 * 1000);
    renderWithMantine(
      <LiveIndicator isLive={false} showTimestamp lastUpdated={recent} />
    );
    expect(screen.getByText('Updated just now')).toBeTruthy();
  });
});
