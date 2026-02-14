import { type Page, type Locator } from '@playwright/test';

/**
 * Page object model for the Dashboard page (/).
 */
export class DashboardPage {
  readonly page: Page;
  readonly heading: Locator;
  readonly createLeagueCTA: Locator;
  readonly joinLeagueCTA: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.getByRole('heading', { name: /Dashboard/i });
    this.createLeagueCTA = page.getByRole('button', { name: /Create League/i });
    this.joinLeagueCTA = page.getByRole('button', { name: /Join League/i });
  }

  /** Navigate to the dashboard */
  async goto() {
    await this.page.goto('/');
  }

  /** Get all league card elements */
  getLeagueCards(): Locator {
    return this.page.locator('[class*="Card"]').filter({ has: this.page.getByRole('heading', { level: 4 }) });
  }

  /** Get the Create League CTA button */
  getCreateLeagueCTA(): Locator {
    return this.createLeagueCTA;
  }

  /** Get the Join League CTA button */
  getJoinLeagueCTA(): Locator {
    return this.joinLeagueCTA;
  }

  /** Click a league card to navigate to its dashboard */
  async navigateToLeague(leagueName: string) {
    await this.page.getByRole('heading', { name: leagueName, level: 4 }).click();
  }
}
