import { defineConfig } from '@rstest/core';
import { pluginReact } from '@rsbuild/plugin-react';

export default defineConfig({
  include: ['packages/*/src/**/*.test.ts', 'packages/*/src/**/*.test.tsx'],
  testEnvironment: 'jsdom',
  plugins: [pluginReact()],
  setupFiles: ['./test-setup.ts'],
  source: {
    define: {
      'import.meta.env.VITE_SUPABASE_URL': JSON.stringify('http://localhost:54321'),
      'import.meta.env.VITE_SUPABASE_ANON_KEY': JSON.stringify('test-anon-key'),
    },
  },
});
