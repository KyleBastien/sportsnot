import React, { type ReactElement, type ReactNode } from 'react';
import { render, type RenderResult } from '@testing-library/react';
import { MantineProvider } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { AuthContext, type AuthContextValue } from '../app/context/AuthContext';

export function createMockAuthContext(
  overrides?: Partial<AuthContextValue>
): AuthContextValue {
  return {
    user: null,
    session: null,
    loading: false,
    signInWithMagicLink: async () => ({ error: null }),
    signInWithOtp: async () => ({ error: null }),
    verifyOtp: async () => ({ data: null, error: null }),
    signOut: async () => ({ error: null }),
    ...overrides,
  };
}

interface RenderWithAuthOptions {
  auth?: Partial<AuthContextValue>;
  route?: string;
  queryClient?: QueryClient;
  routerWrapper?: (children: ReactNode) => ReactElement;
}

export function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0, staleTime: 0 },
      mutations: { retry: false },
    },
  });
}

export function renderWithAuth(
  ui: ReactElement,
  options: RenderWithAuthOptions = {}
): RenderResult & { queryClient: QueryClient } {
  const queryClient = options.queryClient ?? createTestQueryClient();
  const auth = createMockAuthContext(options.auth);
  const routerWrapper =
    options.routerWrapper ??
    ((children: ReactNode) => (
      <MemoryRouter initialEntries={[options.route ?? '/']}>
        {children}
      </MemoryRouter>
    ));

  const result = render(
    <MantineProvider>
      <QueryClientProvider client={queryClient}>
        <AuthContext.Provider value={auth}>
          {routerWrapper(ui)}
        </AuthContext.Provider>
      </QueryClientProvider>
    </MantineProvider>
  );

  return { ...result, queryClient };
}

/** Returns a queryFn whose promise never resolves; lets tests assert
 *  "during isLoading=true" without timing flakiness. */
export function pendingQueryFn<T>(): () => Promise<T> {
  return () => new Promise<T>(() => undefined);
}

/** Returns a queryFn that resolves immediately with the provided value. */
export function resolvedQueryFn<T>(value: T): () => Promise<T> {
  return () => Promise.resolve(value);
}
