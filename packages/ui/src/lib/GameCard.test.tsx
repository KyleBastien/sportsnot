import { describe, it, expect, afterEach } from '@rstest/core';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { MantineProvider } from '@mantine/core';
import { GameCard } from './GameCard';
import type { GameCardProps, GameCardTeam } from './GameCard';

afterEach(cleanup);

function renderWithMantine(ui: React.ReactElement) {
  return render(<MantineProvider>{ui}</MantineProvider>);
}

function makeTeam(overrides: Partial<GameCardTeam> = {}): GameCardTeam {
  return { abbrev: 'EDM', score: 3, ...overrides };
}

function makeProps(overrides: Partial<GameCardProps> = {}): GameCardProps {
  return {
    homeTeam: makeTeam({ abbrev: 'TOR', score: 2 }),
    awayTeam: makeTeam({ abbrev: 'EDM', score: 3 }),
    status: 'final',
    ...overrides,
  };
}

describe('GameCard', () => {
  it('renders both team abbreviations', () => {
    renderWithMantine(<GameCard {...makeProps()} />);
    expect(screen.getAllByText('EDM').length).toBeGreaterThan(0);
    expect(screen.getAllByText('TOR').length).toBeGreaterThan(0);
  });

  it('renders team scores', () => {
    renderWithMantine(<GameCard {...makeProps()} />);
    expect(screen.getByText('3')).toBeTruthy();
    expect(screen.getByText('2')).toBeTruthy();
  });

  it('shows FINAL badge for final status', () => {
    renderWithMantine(<GameCard {...makeProps({ status: 'final' })} />);
    expect(screen.getByText('FINAL')).toBeTruthy();
  });

  it('shows LIVE indicator for live status', () => {
    renderWithMantine(
      <GameCard {...makeProps({ status: 'live' })} />
    );
    expect(screen.getByText('LIVE')).toBeTruthy();
  });

  it('shows period and time remaining for live games', () => {
    renderWithMantine(
      <GameCard
        {...makeProps({
          status: 'live',
          period: '2nd',
          timeRemaining: '12:34',
        })}
      />
    );
    expect(screen.getByText('2nd')).toBeTruthy();
    expect(screen.getByText('12:34')).toBeTruthy();
  });

  it('shows start time for upcoming games', () => {
    const startTime = new Date(2026, 1, 14, 19, 0);
    renderWithMantine(
      <GameCard
        {...makeProps({ status: 'upcoming', startTime })}
      />
    );
    expect(screen.getByText(/7:00/)).toBeTruthy();
  });

  it('does not show FINAL or LIVE for upcoming games', () => {
    const startTime = new Date(2026, 1, 14, 19, 0);
    renderWithMantine(
      <GameCard {...makeProps({ status: 'upcoming', startTime })} />
    );
    expect(screen.queryByText('FINAL')).toBeNull();
    expect(screen.queryByText('LIVE')).toBeNull();
  });

  it('applies highlight border styling when highlight is true', () => {
    const { container } = renderWithMantine(
      <GameCard {...makeProps({ highlight: true })} />
    );
    const { container: containerNoHighlight } = renderWithMantine(
      <GameCard {...makeProps({ highlight: false })} />
    );
    // The highlighted card should render differently than non-highlighted
    const highlightedHTML = container.innerHTML;
    const normalHTML = containerNoHighlight.innerHTML;
    expect(highlightedHTML).not.toBe(normalHTML);
  });

  it('shows highlight reason when provided', () => {
    renderWithMantine(
      <GameCard
        {...makeProps({ highlight: true, highlightReason: 'Your player scored!' })}
      />
    );
    expect(screen.getByText('Your player scored!')).toBeTruthy();
  });

  it('does not show highlight reason without highlight', () => {
    renderWithMantine(
      <GameCard
        {...makeProps({ highlight: false, highlightReason: 'Your player scored!' })}
      />
    );
    expect(screen.queryByText('Your player scored!')).toBeNull();
  });

  it('calls onClick when card is clicked', () => {
    let clicked = false;
    renderWithMantine(
      <GameCard {...makeProps({ onClick: () => { clicked = true; } })} />
    );
    fireEvent.click(screen.getByText('FINAL'));
    expect(clicked).toBe(true);
  });
});
