import baseConfig from '../../eslint.config.mjs';
import reactHooks from 'eslint-plugin-react-hooks';
import reactCompiler from 'eslint-plugin-react-compiler';

export default [
  ...baseConfig,
  reactHooks.configs['flat'].recommended,
  reactCompiler.configs.recommended,
];
