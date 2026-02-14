import { describe, it, expect, afterEach } from '@rstest/core';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { MantineProvider } from '@mantine/core';
import { PlayerCard } from './PlayerCard';
import type { NHLPlayer } from '@sportsnot/types';

afterEach(cleanup);

function makePlayer(overrides: Partial<NHLPlayer> = {}): NHLPlayer {
  return {
    id: 1,
    fullName: 'Connor McDavid',
    firstName: 'Connor',
    lastName: 'McDavid',
    primaryNumber: '97',
    birthDate: '1997-01-13',
    currentAge: 29,
    nationality: 'CA',
    height: '6\'1"',
    weight: 193,
    shootsCatches: 'L',
    primaryPosition: {
      code: 'C',
      name: 'Center',
      type: 'Forward',
      abbreviation: 'C',
    },
    currentTeam: { id: 22, name: 'Edmonton Oilers', abbreviation: 'EDM' },
    headshot: 'https://example.com/mcdavid.jpg',
    ...overrides,
  };
}

function renderWithMantine(ui: React.ReactElement) {
  return render(<MantineProvider>{ui}</MantineProvider>);
}

describe('PlayerCard', () => {
  it('renders player name and position', () => {
    const player = makePlayer();
    renderWithMantine(<PlayerCard player={player} />);
    expect(screen.getByText('Connor McDavid')).toBeTruthy();
    expect(screen.getByText('C')).toBeTruthy();
  });

  it('renders team abbreviation and jersey number', () => {
    const player = makePlayer();
    renderWithMantine(<PlayerCard player={player} />);
    expect(screen.getByText('EDM')).toBeTruthy();
    expect(screen.getByText('#97')).toBeTruthy();
  });

  it('handles missing team data', () => {
    const player = makePlayer({ currentTeam: undefined });
    renderWithMantine(<PlayerCard player={player} />);
    expect(screen.getByText('Connor McDavid')).toBeTruthy();
    expect(screen.queryByText('EDM')).toBeNull();
  });

  it('handles missing jersey number', () => {
    const player = makePlayer({ primaryNumber: undefined });
    renderWithMantine(<PlayerCard player={player} />);
    expect(screen.getByText('Connor McDavid')).toBeTruthy();
    expect(screen.queryByText('#97')).toBeNull();
  });

  it('shows points when provided', () => {
    const player = makePlayer();
    renderWithMantine(<PlayerCard player={player} points={42} />);
    expect(screen.getByText('42 pts')).toBeTruthy();
  });

  it('does not show points badge when not provided', () => {
    const player = makePlayer();
    renderWithMantine(<PlayerCard player={player} />);
    expect(screen.queryByText(/pts/)).toBeNull();
  });

  it('calls onSelect when card is clicked', () => {
    const player = makePlayer();
    let calledWith: NHLPlayer | null = null;
    const onSelect = (p: NHLPlayer) => {
      calledWith = p;
    };
    renderWithMantine(<PlayerCard player={player} onSelect={onSelect} />);
    fireEvent.click(screen.getByText('Connor McDavid'));
    expect(calledWith).toEqual(player);
  });

  it('renders compare button when onCompareToggle is provided', () => {
    const player = makePlayer();
    renderWithMantine(
      <PlayerCard player={player} onCompareToggle={() => {}} />
    );
    expect(screen.getByLabelText('Add to compare')).toBeTruthy();
  });

  it('shows remove label when player is in compare', () => {
    const player = makePlayer();
    renderWithMantine(
      <PlayerCard
        player={player}
        onCompareToggle={() => {}}
        isInCompare={true}
      />
    );
    expect(screen.getByLabelText('Remove from compare')).toBeTruthy();
  });
});
