import baseConfig from '../../eslint.config.mjs';
import playwright from 'eslint-plugin-playwright';
import globals from 'globals';

export default [
  ...baseConfig,
  playwright.configs['flat/recommended'],
  {
    files: ['*.config.ts', 'fixtures/**/*.ts'],
    languageOptions: { globals: { ...globals.node } },
  },
];
