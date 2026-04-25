import { defineConfig } from '@rstest/core';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

const rootDir = dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  include: ['src/**/*.test.ts', 'src/**/*.test.tsx'],
  passWithNoTests: true,
  testEnvironment: 'jsdom',
  setupFiles: [resolve(rootDir, 'src/test-utils/setup.ts')],
  source: {
    tsconfigPath: resolve(rootDir, 'tsconfig.spec.json'),
    define: {
      'import.meta.env.VITE_SUPABASE_URL': JSON.stringify('http://test.local'),
      'import.meta.env.VITE_SUPABASE_ANON_KEY': JSON.stringify('test-anon-key'),
      'import.meta.env.VITE_MOCK_MODE': JSON.stringify('false'),
    },
  },
  resolve: {
    alias: {
      '@sportsnot/widget-bridge': resolve(
        rootDir,
        '../widget-bridge/src/index.ts'
      ),
      '@sportsnot/widget-api': resolve(rootDir, '../widget-api/src/index.ts'),
      '@sportsnot/ui': resolve(rootDir, 'src/test-utils/uiStub.tsx'),
    },
  },
  tools: {
    swc: {
      jsc: {
        transform: {
          react: {
            runtime: 'automatic',
          },
        },
      },
    },
  },
});
