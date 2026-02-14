import { Component, type ReactNode, type ErrorInfo } from 'react';
import { Container, Title, Text, Button, Stack, Alert } from '@mantine/core';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  override componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('ErrorBoundary caught:', error, errorInfo);
  }

  override render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <Container size="sm" py="xl">
          <Stack align="center" gap="lg">
            <Title order={2}>Something went wrong</Title>
            <Alert color="red" title="Error Details" maw={500} w="100%">
              <Text size="sm">{this.state.error?.message ?? 'Unknown error'}</Text>
            </Alert>
            <Button onClick={() => window.location.reload()}>
              Reload Page
            </Button>
          </Stack>
        </Container>
      );
    }

    return this.props.children;
  }
}
