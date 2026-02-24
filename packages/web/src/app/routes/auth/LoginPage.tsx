import React, { useState } from 'react';
import {
  Container,
  Title,
  Text,
  TextInput,
  Button,
  Stack,
  Paper,
  Alert,
  Image,
} from '@mantine/core';
import { useAuthContext } from '../../context/AuthContext';
import logoSrc from '../../../assets/sportsnot-logo.png';

export function LoginPage() {
  const { signInWithMagicLink } = useAuthContext();
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    const { error: authError } = await signInWithMagicLink(email);

    if (authError) {
      setError(authError.message);
    } else {
      setSent(true);
    }
    setLoading(false);
  };

  if (sent) {
    return (
      <Container size="xs" py="xl">
        <Paper shadow="md" p="xl" radius="md" withBorder>
          <Stack align="center" gap="md">
            <Title order={2}>Check your email</Title>
            <Text ta="center" c="dimmed">
              We sent a magic link to <strong>{email}</strong>. Click the link
              in the email to sign in.
            </Text>
            <Button variant="subtle" onClick={() => setSent(false)}>
              Use a different email
            </Button>
          </Stack>
        </Paper>
      </Container>
    );
  }

  return (
    <Container size="xs" py="xl">
      <Paper shadow="md" p="xl" radius="md" withBorder>
        <Stack gap="md" align="center">
          <Image
            src={logoSrc}
            alt="SportsNot Fantasy Hockey"
            h={60}
            w="auto"
            fit="contain"
          />
          <Title order={2} ta="center">
            Sign in to SportsNot
          </Title>
          <Text ta="center" c="dimmed" size="sm">
            Enter your email to receive a magic link
          </Text>

          {error && (
            <Alert color="red" title="Error">
              {error}
            </Alert>
          )}

          <form onSubmit={handleSubmit}>
            <Stack gap="md">
              <TextInput
                label="Email"
                placeholder="you@example.com"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.currentTarget.value)}
                size="md"
              />
              <Button type="submit" loading={loading} fullWidth size="md">
                Send Magic Link
              </Button>
            </Stack>
          </form>
        </Stack>
      </Paper>
    </Container>
  );
}
