const { NxAppRspackPlugin } = require('@nx/rspack/app-plugin');
const { NxReactRspackPlugin } = require('@nx/rspack/react-plugin');
const { VanillaExtractPlugin } = require('@vanilla-extract/webpack-plugin');
const { InjectManifest } = require('workbox-webpack-plugin');
const { join } = require('path');

const isProduction = process.env['NODE_ENV'] === 'production';

module.exports = {
  output: {
    path: join(__dirname, 'dist'),
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
      baseHref: '/',
      assets: ['./src/favicon.ico', './src/assets', './public/offline.html'],
      styles: [],
      outputHashing: isProduction ? 'all' : 'none',
      optimization: isProduction,
    }),
    new NxReactRspackPlugin({
      // Uncomment this line if you don't want to use SVGR
      // See: https://react-svgr.com/
      // svgr: false
    }),
    ...(isProduction
      ? [
          new InjectManifest({
            swSrc: join(__dirname, 'src/sw.ts'),
            swDest: 'sw.js',
            maximumFileSizeToCacheInBytes: 5 * 1024 * 1024,
            additionalManifestEntries: [
              { url: '/offline.html', revision: null },
            ],
          }),
        ]
      : []),
  ],
};
