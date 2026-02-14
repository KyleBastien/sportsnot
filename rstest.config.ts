import { defineConfig } from '@rstest/core';
import { pluginReact } from '@rsbuild/plugin-react';

export default defineConfig({
  include: ['packages/*/src/**/*.test.ts', 'packages/*/src/**/*.test.tsx'],
  testEnvironment: 'jsdom',
  plugins: [pluginReact()],
  setupFiles: ['./test-setup.ts'],
  source: {
    define: {
      'import.meta.env.VITE_SUPABASE_URL': JSON.stringify(
        'http://localhost:54321'
      ),
      'import.meta.env.VITE_SUPABASE_ANON_KEY': JSON.stringify('test-anon-key'),
    },
  },
  coverage: {
    enabled: true,
    provider: 'istanbul',
    reporters: ['text', 'html', 'json', 'lcov'],
    reportsDirectory: './coverage',
    reportOnFailure: true,
    include: [
      'packages/utils/src/**/*.{ts,tsx}',
      'packages/nhl-api/src/**/*.{ts,tsx}',
      'packages/supabase/src/**/*.{ts,tsx}',
      'packages/ui/src/**/*.{ts,tsx}',
      'packages/web/src/**/*.{ts,tsx}',
    ],
    exclude: [
      '**/*.test.{ts,tsx}',
      '**/*.spec.{ts,tsx}',
      '**/test-setup.ts',
      '**/*.d.ts',
    ],
    // Coverage targets per package
    // Targets: utils=90%, nhl-api=70%, supabase=70%, ui=80%, web=60%
    thresholds: {
      'packages/utils/src/**/*.{ts,tsx}': {
        statements: 90,
        branches: 90,
        functions: 90,
        lines: 90,
      },
      'packages/nhl-api/src/**/*.{ts,tsx}': {
        statements: 35,
        branches: 55,
        functions: 15,
        lines: 35,
      },
      'packages/supabase/src/**/*.{ts,tsx}': {
        statements: 70,
        branches: 50,
        functions: 70,
        lines: 70,
      },
      'packages/ui/src/**/*.{ts,tsx}': {
        statements: 80,
        branches: 80,
        functions: 80,
        lines: 80,
      },
      'packages/web/src/**/*.{ts,tsx}': {
        statements: 13,
        branches: 9,
        functions: 13,
        lines: 13,
      },
    },
  },
});
