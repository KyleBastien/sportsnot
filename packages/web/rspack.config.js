const { NxAppRspackPlugin } = require('@nx/rspack/app-plugin');
const { NxReactRspackPlugin } = require('@nx/rspack/react-plugin');
const { VanillaExtractPlugin } = require('@vanilla-extract/webpack-plugin');
const { DefinePlugin, NormalModuleReplacementPlugin } = require('@rspack/core');
const { join } = require('path');

const baseHref = process.env.BASE_HREF || '/';
const mockStub = join(__dirname, 'src/mock/stubs/mock-noop.ts');

const envVars = {
  VITE_SUPABASE_URL: process.env.VITE_SUPABASE_URL || 'http://localhost:54321',
  VITE_SUPABASE_ANON_KEY:
    process.env.VITE_SUPABASE_ANON_KEY || 'mock-anon-key-for-local-dev',
  VITE_MOCK_MODE: process.env.VITE_MOCK_MODE || 'false',
};

module.exports = {
  output: {
    path: join(__dirname, 'dist'),
    publicPath: baseHref,
  },
  resolve: {
    alias:
      envVars.VITE_MOCK_MODE !== 'true'
        ? {
            '@sportsnot/mock-data': join(
              __dirname,
              'src/mock/mock-data-stub.ts'
            ),
          }
        : {},
  },
  module: {
    rules: [
      {
        test: /[\\/]mock[\\/]/,
        sideEffects: false,
      },
    ],
  },
  devServer: {
    port: 4200,
    historyApiFallback: {
      index: '/index.html',
      disableDotRule: true,
      htmlAcceptHeaders: ['text/html', 'application/xhtml+xml'],
    },
  },
  plugins: [
    new VanillaExtractPlugin(),
    new NxAppRspackPlugin({
      tsConfig: './tsconfig.app.json',
      main: './src/main.tsx',
      index: './src/index.html',
      baseHref: baseHref,
      assets: ['./src/favicon.ico', './src/assets'],
      styles: [],
      outputHashing: process.env['NODE_ENV'] === 'production' ? 'all' : 'none',
      optimization: process.env['NODE_ENV'] === 'production',
    }),
    new NxReactRspackPlugin({
      // Uncomment this line if you don't want to use SVGR
      // See: https://react-svgr.com/
      // svgr: false
    }),
    new DefinePlugin({
      'import.meta.env.VITE_SUPABASE_URL': JSON.stringify(
        envVars.VITE_SUPABASE_URL
      ),
      'import.meta.env.VITE_SUPABASE_ANON_KEY': JSON.stringify(
        envVars.VITE_SUPABASE_ANON_KEY
      ),
      'import.meta.env.VITE_MOCK_MODE': JSON.stringify(envVars.VITE_MOCK_MODE),
      'import.meta.env.BASE_HREF': JSON.stringify(baseHref),
    }),
    ...(envVars.VITE_MOCK_MODE !== 'true'
      ? [
          new NormalModuleReplacementPlugin(
            /[\\/]mock[\\/]hooks[\\/]/,
            mockStub
          ),
          new NormalModuleReplacementPlugin(
            /[\\/]mock[\\/]MockDataProvider/,
            mockStub
          ),
          new NormalModuleReplacementPlugin(/[\\/]mock[\\/]utils/, mockStub),
        ]
      : []),
  ],
};
