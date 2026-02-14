import { describe, it, expect, afterEach } from '@rstest/core';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { MantineProvider } from '@mantine/core';
import { TeamCard } from './TeamCard';

afterEach(cleanup);

function renderWithMantine(ui: React.ReactElement) {
  return render(<MantineProvider>{ui}</MantineProvider>);
}

describe('TeamCard', () => {
  it('renders team name and abbreviation', () => {
    renderWithMantine(
      <TeamCard teamName="Edmonton Oilers" teamAbbrev="EDM" />
    );
    expect(screen.getByText('Edmonton Oilers')).toBeTruthy();
    expect(screen.getAllByText('EDM').length).toBeGreaterThan(0);
  });

  it('renders record when provided', () => {
    renderWithMantine(
      <TeamCard
        teamName="Edmonton Oilers"
        teamAbbrev="EDM"
        record={{ wins: 10, losses: 4 }}
      />
    );
    expect(screen.getByText('10W–4L')).toBeTruthy();
  });

  it('does not render record when not provided', () => {
    renderWithMantine(
      <TeamCard teamName="Edmonton Oilers" teamAbbrev="EDM" />
    );
    expect(screen.queryByText(/W–/)).toBeNull();
  });

  it('renders points when provided', () => {
    renderWithMantine(
      <TeamCard teamName="Edmonton Oilers" teamAbbrev="EDM" points={24} />
    );
    expect(screen.getByText('24 pts')).toBeTruthy();
  });

  it('shows eliminated state with reduced opacity', () => {
    const { container } = renderWithMantine(
      <TeamCard
        teamName="Edmonton Oilers"
        teamAbbrev="EDM"
        isEliminated={true}
      />
    );
    const card = container.querySelector('.mantine-Card-root');
    expect(card).toBeTruthy();
    expect((card as HTMLElement).style.opacity).toBe('0.5');
  });

  it('shows line-through text when eliminated', () => {
    renderWithMantine(
      <TeamCard
        teamName="Edmonton Oilers"
        teamAbbrev="EDM"
        isEliminated={true}
      />
    );
    const nameEl = screen.getByText('Edmonton Oilers');
    expect(nameEl.style.textDecoration).toContain('line-through');
  });

  it('calls onClick when card is clicked', () => {
    let called = false;
    const onClick = () => { called = true; };
    renderWithMantine(
      <TeamCard
        teamName="Edmonton Oilers"
        teamAbbrev="EDM"
        onClick={onClick}
      />
    );
    fireEvent.click(screen.getByText('Edmonton Oilers'));
    expect(called).toBe(true);
  });

  it('has pointer cursor when onClick is provided', () => {
    const { container } = renderWithMantine(
      <TeamCard
        teamName="Edmonton Oilers"
        teamAbbrev="EDM"
        onClick={() => {}}
      />
    );
    const card = container.querySelector('.mantine-Card-root');
    expect((card as HTMLElement).style.cursor).toBe('pointer');
  });

  it('has default cursor when no onClick', () => {
    const { container } = renderWithMantine(
      <TeamCard teamName="Edmonton Oilers" teamAbbrev="EDM" />
    );
    const card = container.querySelector('.mantine-Card-root');
    expect((card as HTMLElement).style.cursor).toBe('default');
  });
});
