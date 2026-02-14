import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Center, Loader, Text, Stack } from '@mantine/core';
import { supabase } from '@sportsnot/supabase';

export function AuthCallbackPage() {
  const navigate = useNavigate();

  useEffect(() => {
    supabase.auth.onAuthStateChange((event) => {
      if (event === 'SIGNED_IN') {
        navigate('/', { replace: true });
      }
    });
  }, [navigate]);

  return (
    <Center h="50vh">
      <Stack align="center" gap="md">
        <Loader size="lg" />
        <Text c="dimmed">Signing you in...</Text>
      </Stack>
    </Center>
  );
}
