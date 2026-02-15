import { type Page, type Locator } from '@playwright/test';

/**
 * Page object model for the Draft page (/draft/:leagueId).
 */
export class DraftPage {
  readonly page: Page;
  readonly heading: Locator;
  readonly searchInput: Locator;
  readonly confirmPickModal: Locator;
  readonly confirmPickButton: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.getByRole('heading', { name: /Draft Room/i });
    this.searchInput = page.getByPlaceholder(/Search players/i);
    this.confirmPickModal = page.getByRole('dialog');
    this.confirmPickButton = page.getByRole('button', {
      name: /Confirm Pick/i,
    });
  }

  /** Navigate to the draft page for a given league */
  async goto(leagueId: string) {
    await this.page.goto(`/draft/${leagueId}`);
  }

  /** Get all available player rows from the skaters and teams tables */
  getAvailablePlayers(): Locator {
    return this.page.getByRole('table').getByRole('row');
  }

  /** Filter the player list by position via SegmentedControl */
  async filterByPosition(position: 'All' | 'Forwards' | 'Defense' | 'Goalies') {
    await this.page.getByRole('radio', { name: position }).click();
  }

  /** Search for a player by name */
  async searchPlayer(name: string) {
    await this.searchInput.fill(name);
  }

  /** Click the "Draft" button next to a player to open the confirm modal, then confirm */
  async pickPlayer(playerName: string) {
    const row = this.page.getByRole('row').filter({ hasText: playerName });
    await row.getByRole('button', { name: /Draft/i }).click();
    await this.confirmPickButton.click();
  }

  /** Get the user's roster sidebar showing picked players */
  getMyRoster(): Locator {
    return this.page.getByText(/Draft History/i).locator('..');
  }

  /** Get the compare tray element (if visible) */
  getCompareTray(): Locator {
    return this.page.getByText(/Compare/i).locator('..');
  }
}
