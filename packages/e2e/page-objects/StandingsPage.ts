import { type Page, type Locator } from '@playwright/test';

/**
 * Page object model for the Standings page (/standings/:leagueId).
 */
export class StandingsPage {
  readonly page: Page;
  readonly heading: Locator;
  readonly table: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.getByRole('heading', { name: /Standings/i });
    this.table = page.getByRole('table');
  }

  /** Navigate to the standings page for a given league */
  async goto(leagueId: string) {
    await this.page.goto(`/standings/${leagueId}`);
  }

  /** Get all member rows in the standings table (excluding header) */
  getMemberRows(): Locator {
    return this.table
      .getByRole('row')
      .filter({ has: this.page.getByRole('cell') });
  }

  /** Get the row for the current user (identified by "You" badge) */
  getCurrentUserRow(): Locator {
    return this.table.getByRole('row').filter({ hasText: /You/i });
  }

  /** Click the CSV export button (if present) */
  async exportCSV() {
    await this.page
      .getByRole('button', { name: /Export|CSV|Download/i })
      .click();
  }
}
