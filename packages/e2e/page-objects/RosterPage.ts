import { type Page, type Locator } from '@playwright/test';

/**
 * Page object model for the Roster page (/roster/:leagueId).
 */
export class RosterPage {
  readonly page: Page;
  readonly heading: Locator;
  readonly totalPointsCard: Locator;
  readonly activateIRModal: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.getByRole('heading', { name: /My Roster/i });
    this.totalPointsCard = page.getByText(/Total Points/i).locator('..');
    this.activateIRModal = page.getByRole('dialog');
  }

  /** Navigate to the roster page for a given league */
  async goto(leagueId: string) {
    await this.page.goto(`/roster/${leagueId}`);
  }

  /** Get active position slot sections (Forward, Defenseman, Goalie) */
  getActiveSlots(): Locator {
    return this.page.getByRole('heading', { name: /^(Forward|Defenseman|Goalie)$/i }).locator('..');
  }

  /** Get IR slot sections (IR Forward, IR Defenseman) */
  getIRSlots(): Locator {
    return this.page.getByRole('heading', { name: /^IR /i }).locator('..');
  }

  /** Get the total points display text */
  getTotalPoints(): Locator {
    return this.totalPointsCard;
  }

  /** Click the "Activate IR" button for a given player slot */
  async activateIR(playerName: string) {
    const row = this.page.getByRole('row').filter({ hasText: playerName });
    await row.getByRole('button', { name: /Activate IR/i }).click();
  }
}
