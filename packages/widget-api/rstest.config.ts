import { defineConfig } from '@rstest/core';

export default defineConfig({
  include: ['src/**/*.test.ts', 'src/**/*.test.tsx'],
  passWithNoTests: true,
});
