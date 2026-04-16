import { StrictMode, Suspense, lazy, type ReactNode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { MantineProvider } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import '@mantine/core/styles.css';
import './styles.css';
import { theme } from './theme';

import { AuthProvider } from './app/context/AuthContext';
import App from './app/app';

// Mock mode — lazy-load MockAuthProvider only when VITE_MOCK_MODE is 'true'
const MockAuthProvider =
  import.meta.env.VITE_MOCK_MODE === 'true'
    ? lazy(() =>
        import('./mock/MockAuthProvider').then((m) => ({
          default: m.MockAuthProvider,
        }))
      )
    : null;

function AuthWrapper({ children }: { children: ReactNode }) {
  if (MockAuthProvider) {
    return (
      <Suspense fallback={null}>
        <MockAuthProvider>{children}</MockAuthProvider>
      </Suspense>
    );
  }
  return <AuthProvider>{children}</AuthProvider>;
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5, // 5 minutes
      retry: 1,
    },
  },
});

const root = createRoot(document.getElementById('root') as HTMLElement);
root.render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <MantineProvider theme={theme} defaultColorScheme="auto">
        <BrowserRouter
          basename={(import.meta.env.BASE_HREF || '/').replace(/\/+$/, '')}
        >
          <AuthWrapper>
            <App />
          </AuthWrapper>
        </BrowserRouter>
      </MantineProvider>
    </QueryClientProvider>
  </StrictMode>
);
