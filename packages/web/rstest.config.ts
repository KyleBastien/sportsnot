import { defineConfig } from '@rstest/core';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

const rootDir = dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  include: ['src/**/*.test.ts', 'src/**/*.test.tsx'],
  passWithNoTests: true,
  testEnvironment: 'jsdom',
  resolve: {
    alias: {
      '@sportsnot/widget-bridge': resolve(
        rootDir,
        '../widget-bridge/src/index.ts'
      ),
      '@sportsnot/widget-api': resolve(rootDir, '../widget-api/src/index.ts'),
    },
  },
});
