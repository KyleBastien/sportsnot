import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.sportsnot.app',
  appName: 'SportsNot',
  webDir: 'packages/web/dist',
  ios: {
    contentInset: 'never',
    scheme: 'SportsNot',
  },
  server: {
    androidScheme: 'https',
    iosScheme: 'https',
  },
};

export default config;
