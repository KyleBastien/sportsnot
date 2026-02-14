import { describe, it, expect, afterEach } from '@rstest/core';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { MantineProvider } from '@mantine/core';
import { ResponsiveTable } from './ResponsiveTable';
import type { ResponsiveTableColumn } from './ResponsiveTable';

afterEach(cleanup);

function renderWithMantine(ui: React.ReactElement) {
  return render(<MantineProvider>{ui}</MantineProvider>);
}

const columns: ResponsiveTableColumn[] = [
  { key: 'name', label: 'Name', sortable: true },
  { key: 'points', label: 'Points', sortable: true },
  { key: 'team', label: 'Team' },
];

const data = [
  { name: 'McDavid', points: 120, team: 'EDM' },
  { name: 'Matthews', points: 90, team: 'TOR' },
  { name: 'Draisaitl', points: 110, team: 'EDM' },
];

describe('ResponsiveTable – desktop (table view)', () => {
  it('renders column headers', () => {
    renderWithMantine(
      <ResponsiveTable columns={columns} data={data} />
    );
    expect(screen.getByText('Name')).toBeTruthy();
    expect(screen.getByText('Points')).toBeTruthy();
    expect(screen.getByText('Team')).toBeTruthy();
  });

  it('renders all data rows', () => {
    renderWithMantine(
      <ResponsiveTable columns={columns} data={data} />
    );
    expect(screen.getByText('McDavid')).toBeTruthy();
    expect(screen.getByText('Matthews')).toBeTruthy();
    expect(screen.getByText('Draisaitl')).toBeTruthy();
  });

  it('renders cell values', () => {
    renderWithMantine(
      <ResponsiveTable columns={columns} data={data} />
    );
    expect(screen.getByText('120')).toBeTruthy();
    // EDM appears twice in data (McDavid and Draisaitl)
    expect(screen.getAllByText('EDM').length).toBe(2);
  });

  it('calls onRowClick when a row is clicked', () => {
    let clickedRow: Record<string, unknown> | null = null;
    renderWithMantine(
      <ResponsiveTable
        columns={columns}
        data={data}
        onRowClick={(row) => { clickedRow = row; }}
      />
    );
    fireEvent.click(screen.getByText('McDavid'));
    expect(clickedRow).toEqual(data[0]);
  });

  it('renders custom cells via renderCell', () => {
    renderWithMantine(
      <ResponsiveTable
        columns={columns}
        data={data}
        renderCell={(key, value) =>
          key === 'points' ? <strong>{String(value)} pts</strong> : String(value ?? '')
        }
      />
    );
    expect(screen.getByText('120 pts')).toBeTruthy();
  });

  it('shows em-dash for null values', () => {
    const sparse = [{ name: 'Test', points: null, team: null }];
    renderWithMantine(
      <ResponsiveTable columns={columns} data={sparse as unknown as Record<string, unknown>[]} />
    );
    expect(screen.getAllByText('—').length).toBe(2);
  });

  it('sorts data when sortable header is clicked', () => {
    const { container } = renderWithMantine(
      <ResponsiveTable columns={columns} data={data} sortable />
    );
    // Click Points header to sort ascending
    fireEvent.click(screen.getByText(/Points/));
    const cells = container.querySelectorAll('td');
    // After ascending sort by points: Matthews(90), Draisaitl(110), McDavid(120)
    const pointsCells = Array.from(cells).filter((_, i) => i % 3 === 1);
    expect(pointsCells[0].textContent).toBe('90');
    expect(pointsCells[1].textContent).toBe('110');
    expect(pointsCells[2].textContent).toBe('120');
  });

  it('reverses sort direction on second click', () => {
    const { container } = renderWithMantine(
      <ResponsiveTable columns={columns} data={data} sortable />
    );
    fireEvent.click(screen.getByText(/Points/));
    fireEvent.click(screen.getByText(/Points/));
    const cells = container.querySelectorAll('td');
    const pointsCells = Array.from(cells).filter((_, i) => i % 3 === 1);
    expect(pointsCells[0].textContent).toBe('120');
    expect(pointsCells[1].textContent).toBe('110');
    expect(pointsCells[2].textContent).toBe('90');
  });
});

describe('ResponsiveTable – mobile (card view)', () => {
  // Override matchMedia to simulate mobile viewport
  const originalMatchMedia = window.matchMedia;

  function setMobile() {
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: (query: string) => ({
        matches: query === '(max-width: 62em)',
        media: query,
        onchange: null,
        addListener: () => {},
        removeListener: () => {},
        addEventListener: () => {},
        removeEventListener: () => {},
        dispatchEvent: () => false,
      }),
    });
  }

  function restoreDesktop() {
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: originalMatchMedia,
    });
  }

  afterEach(() => {
    restoreDesktop();
  });

  it('renders cards instead of table rows on mobile', () => {
    setMobile();
    const { container } = renderWithMantine(
      <ResponsiveTable columns={columns} data={data} />
    );
    // Should not render a <table> element
    expect(container.querySelector('table')).toBeNull();
    // Should render data values
    expect(screen.getByText('McDavid')).toBeTruthy();
    expect(screen.getByText('120')).toBeTruthy();
  });

  it('renders column labels on each card in mobile view', () => {
    setMobile();
    renderWithMantine(
      <ResponsiveTable columns={columns} data={[data[0]]} />
    );
    expect(screen.getByText('Name')).toBeTruthy();
    expect(screen.getByText('Points')).toBeTruthy();
    expect(screen.getByText('Team')).toBeTruthy();
  });

  it('calls onRowClick when card is clicked on mobile', () => {
    setMobile();
    let clickedRow: Record<string, unknown> | null = null;
    renderWithMantine(
      <ResponsiveTable
        columns={columns}
        data={[data[0]]}
        onRowClick={(row) => { clickedRow = row; }}
      />
    );
    fireEvent.click(screen.getByText('McDavid'));
    expect(clickedRow).toEqual(data[0]);
  });

  it('shows sort buttons on mobile when sortable', () => {
    setMobile();
    renderWithMantine(
      <ResponsiveTable columns={columns} data={data} sortable />
    );
    // Only sortable columns should have sort buttons
    // Name and Points are sortable, Team is not
    const sortButtons = screen.getAllByText(/↕/);
    expect(sortButtons.length).toBe(2);
  });
});
