import { defineConfig, devices } from '@playwright/test';

const isCI = !!process.env.CI;

export default defineConfig({
  testDir: './tests',
  fullyParallel: true,
  forbidOnly: isCI,
  retries: isCI ? 2 : 0,
  workers: isCI ? 1 : undefined,
  reporter: 'html',
  use: {
    baseURL: 'http://localhost:4200',
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: isCI
    ? {
        command: 'npx serve packages/web/dist -l 4200 --single',
        url: 'http://localhost:4200',
        reuseExistingServer: false,
        cwd: '../..',
        env: {
          VITE_SUPABASE_URL: 'http://localhost:54321',
          VITE_SUPABASE_ANON_KEY: 'mock-anon-key',
        },
      }
    : {
        command: 'npx nx serve @sportsnot/web',
        url: 'http://localhost:4200',
        reuseExistingServer: true,
        cwd: '../..',
        env: {
          VITE_SUPABASE_URL: 'http://localhost:54321',
          VITE_SUPABASE_ANON_KEY: 'mock-anon-key',
        },
      },
});
