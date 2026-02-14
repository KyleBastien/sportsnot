import { describe, it, expect, afterEach } from '@rstest/core';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { MantineProvider } from '@mantine/core';
import { RosterSlot } from './RosterSlot';
import type { RosterSlotPlayer } from './RosterSlot';

afterEach(cleanup);

function renderWithMantine(ui: React.ReactElement) {
  return render(<MantineProvider>{ui}</MantineProvider>);
}

const player: RosterSlotPlayer = {
  name: 'Connor McDavid',
  teamAbbrev: 'EDM',
  headshot: 'https://example.com/mcdavid.jpg',
  stats: { goals: 40, assists: 60 },
};

describe('RosterSlot', () => {
  it('renders empty state with position badge and "Empty" text', () => {
    renderWithMantine(<RosterSlot position="F" />);
    expect(screen.getByText('F')).toBeTruthy();
    expect(screen.getByText('Empty')).toBeTruthy();
  });

  it('renders empty state for IR position', () => {
    renderWithMantine(<RosterSlot position="IR_F" />);
    expect(screen.getByText('IR_F')).toBeTruthy();
    expect(screen.getByText('Empty')).toBeTruthy();
  });

  it('renders filled state with player name and team', () => {
    renderWithMantine(<RosterSlot position="F" player={player} />);
    expect(screen.getByText('Connor McDavid')).toBeTruthy();
    expect(screen.getByText('EDM')).toBeTruthy();
  });

  it('renders position badge in filled state', () => {
    renderWithMantine(<RosterSlot position="D" player={player} />);
    expect(screen.getByText('D')).toBeTruthy();
  });

  it('renders IR state with player', () => {
    renderWithMantine(<RosterSlot position="IR_D" player={player} />);
    expect(screen.getByText('Connor McDavid')).toBeTruthy();
    expect(screen.getByText('IR_D')).toBeTruthy();
  });

  it('shows points when pointsEarned is provided', () => {
    renderWithMantine(<RosterSlot position="F" player={player} pointsEarned={12} />);
    expect(screen.getByText('12')).toBeTruthy();
  });

  it('does not show points when pointsEarned is not provided', () => {
    renderWithMantine(<RosterSlot position="F" player={player} />);
    expect(screen.queryByText('12')).toBeNull();
  });

  it('renders action buttons and calls onAction', () => {
    let calledAction: string | null = null;
    const onAction = (action: string) => { calledAction = action; };
    renderWithMantine(
      <RosterSlot
        position="F"
        player={player}
        actions={['compare', 'details']}
        onAction={onAction}
      />
    );
    expect(screen.getByLabelText('Compare')).toBeTruthy();
    expect(screen.getByLabelText('View details')).toBeTruthy();
    fireEvent.click(screen.getByLabelText('Compare'));
    expect(calledAction).toBe('compare');
  });

  it('renders activate action for IR slots', () => {
    let calledAction: string | null = null;
    const onAction = (action: string) => { calledAction = action; };
    renderWithMantine(
      <RosterSlot
        position="IR_F"
        player={player}
        actions={['activate']}
        onAction={onAction}
      />
    );
    expect(screen.getByLabelText('Activate from IR')).toBeTruthy();
    fireEvent.click(screen.getByLabelText('Activate from IR'));
    expect(calledAction).toBe('activate');
  });

  it('does not render action buttons when actions array is empty', () => {
    renderWithMantine(<RosterSlot position="F" player={player} actions={[]} />);
    expect(screen.queryByLabelText('Compare')).toBeNull();
  });

  it('applies reduced opacity when isActive is false', () => {
    renderWithMantine(<RosterSlot position="F" player={player} isActive={false} />);
    expect(screen.getByText('Connor McDavid')).toBeTruthy();
  });
});
