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
  Checkbox,
  PinInput,
} from '@mantine/core';
import { useAuthContext } from '../../context/AuthContext';
import logoSrc from '../../../assets/sportsnot-logo.png';
import {
  getSubtitleText,
  getSubmitButtonText,
  isOtpTokenComplete,
  OTP_ERROR_MESSAGE,
} from './loginPageUtils';

export function LoginPage() {
  const { signInWithMagicLink, signInWithOtp, verifyOtp } = useAuthContext();
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);
  const [useOtp, setUseOtp] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [otpSent, setOtpSent] = useState(false);
  const [otpToken, setOtpToken] = useState('');
  const [otpError, setOtpError] = useState<string | null>(null);
  const [verifying, setVerifying] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    if (useOtp) {
      const { error: authError } = await signInWithOtp(email);
      if (authError) {
        setError(authError.message);
      } else {
        setOtpSent(true);
      }
    } else {
      const { error: authError } = await signInWithMagicLink(email);
      if (authError) {
        setError(authError.message);
      } else {
        setSent(true);
      }
    }
    setLoading(false);
  };

  const handleVerifyOtp = async () => {
    setVerifying(true);
    setOtpError(null);

    const { error: authError } = await verifyOtp(email, otpToken);
    if (authError) {
      setOtpError(OTP_ERROR_MESSAGE);
      setOtpToken('');
    }
    setVerifying(false);
  };

  const handleBackToEmail = () => {
    setOtpSent(false);
    setOtpToken('');
    setOtpError(null);
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

  if (otpSent) {
    return (
      <Container size="xs" py="xl">
        <Paper shadow="md" p="xl" radius="md" withBorder>
          <Stack align="center" gap="md">
            <Title order={2}>Enter your code</Title>
            <Text ta="center" c="dimmed">
              We sent a 6-digit code to <strong>{email}</strong>
            </Text>

            {otpError && (
              <Alert color="red" title="Error">
                {otpError}
              </Alert>
            )}

            <PinInput
              length={6}
              type="number"
              value={otpToken}
              onChange={setOtpToken}
            />

            <Button
              fullWidth
              size="md"
              loading={verifying}
              disabled={!isOtpTokenComplete(otpToken)}
              onClick={handleVerifyOtp}
            >
              Verify Code
            </Button>

            <Button variant="subtle" onClick={handleBackToEmail}>
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
            {getSubtitleText(useOtp)}
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
              <Checkbox
                label="Use OTP Code?"
                checked={useOtp}
                onChange={(e) => setUseOtp(e.currentTarget.checked)}
              />
              <Button type="submit" loading={loading} fullWidth size="md">
                {getSubmitButtonText(useOtp)}
              </Button>
            </Stack>
          </form>
        </Stack>
      </Paper>
    </Container>
  );
}
