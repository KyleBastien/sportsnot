import { describe, it, expect, afterEach } from '@rstest/core';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';
import { MantineProvider } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { LoginPage } from './LoginPage';
import { AuthProvider } from '../../context/AuthContext';

afterEach(cleanup);

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
        refetchOnMount: false,
        refetchInterval: false,
        refetchOnWindowFocus: false,
      },
    },
  });
}

function renderPage(queryClient?: QueryClient) {
  const qc = queryClient ?? createTestQueryClient();
  return render(
    <MantineProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <AuthProvider>
            <LoginPage />
          </AuthProvider>
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>
  );
}

describe('LoginPage', () => {
  it('renders sign in title', () => {
    renderPage();
    expect(screen.getByText('Sign in to SportsNot')).toBeTruthy();
  });

  it('renders magic link description text', () => {
    renderPage();
    expect(screen.getByText('Enter your email to receive a magic link')).toBeTruthy();
  });

  it('renders email input field', () => {
    renderPage();
    const emailInput = screen.getByPlaceholderText('you@example.com');
    expect(emailInput).toBeTruthy();
  });

  it('renders email label', () => {
    renderPage();
    expect(screen.getByText('Email')).toBeTruthy();
  });

  it('renders Send Magic Link button', () => {
    renderPage();
    expect(screen.getByText('Send Magic Link')).toBeTruthy();
  });

  it('allows typing in email input', () => {
    renderPage();
    const emailInput = screen.getByPlaceholderText('you@example.com') as HTMLInputElement;
    fireEvent.change(emailInput, { target: { value: 'test@example.com' } });
    expect(emailInput.value).toBe('test@example.com');
  });

  it('renders email input with type email', () => {
    renderPage();
    const emailInput = screen.getByPlaceholderText('you@example.com') as HTMLInputElement;
    expect(emailInput.type).toBe('email');
  });

  it('renders submit button inside a form', () => {
    const { container } = renderPage();
    const form = container.querySelector('form');
    expect(form).toBeTruthy();
    const button = form?.querySelector('button[type="submit"]');
    expect(button).toBeTruthy();
  });

  it('does not show error alert initially', () => {
    renderPage();
    expect(screen.queryByText('Error')).toBeNull();
  });
});
