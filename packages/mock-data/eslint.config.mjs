import baseConfig from '../../eslint.config.mjs';
import globals from 'globals';

export default [
  ...baseConfig,
  {
    files: ['src/scripts/**/*.ts'],
    languageOptions: {
      globals: {
        ...globals.node,
      },
    },
  },
];
