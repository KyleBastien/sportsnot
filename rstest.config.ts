import { defineConfig } from '@rstest/core';
import { pluginReact } from '@rsbuild/plugin-react';

export default defineConfig({
  include: ['packages/*/src/**/*.test.ts', 'packages/*/src/**/*.test.tsx'],
  testEnvironment: 'jsdom',
  plugins: [pluginReact()],
  setupFiles: ['./test-setup.ts'],
});
