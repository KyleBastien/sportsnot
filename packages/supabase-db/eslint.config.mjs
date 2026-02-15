import baseConfig from '../../eslint.config.mjs';

export default [
  ...baseConfig,
  {
    files: ['functions/**/*.ts'],
    languageOptions: {
      globals: {
        Deno: 'readonly',
        Response: 'readonly',
        fetch: 'readonly',
      },
    },
  },
];
