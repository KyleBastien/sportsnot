import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Container,
  Title,
  Text,
  Stack,
  Card,
  Button,
  TextInput,
  Alert,
  Avatar,
  Group,
  Switch,
} from '@mantine/core';
import { supabase } from '@sportsnot/supabase';
import { useAuthContext } from '../../context/AuthContext';
import { usePushNotifications } from '../../hooks/usePushNotifications';

export function ProfilePage() {
  const { user, signOut } = useAuthContext();
  const navigate = useNavigate();
  const [displayName, setDisplayName] = useState(
    (user?.user_metadata?.['display_name'] as string) ?? ''
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const {
    supported: pushSupported,
    permission: pushPermission,
    subscribed: pushSubscribed,
    loading: pushLoading,
    preferences: pushPreferences,
    subscribe: pushSubscribe,
    unsubscribe: pushUnsubscribe,
    setPreferences: setPushPreferences,
  } = usePushNotifications();

  const handleSave = async () => {
    if (!displayName.trim()) {
      setError('Display name is required');
      return;
    }

    setSaving(true);
    setError('');

    const { error: updateError } = await supabase
      .from('users')
      .update({ display_name: displayName.trim() })
      .eq('id', user!.id);

    if (updateError) {
      setError(updateError.message);
    } else {
      setSuccess('Profile updated!');
      setTimeout(() => setSuccess(''), 3000);
    }
    setSaving(false);
  };

  const handleSignOut = async () => {
    await signOut();
    navigate('/auth/login');
  };

  const initial =
    displayName?.[0]?.toUpperCase() ??
    user?.email?.[0]?.toUpperCase() ??
    '?';

  return (
    <Container size="sm" py="xl">
      <Stack gap="xl">
        <Title order={2}>Profile</Title>

        {error && (
          <Alert color="red" onClose={() => setError('')} withCloseButton>
            {error}
          </Alert>
        )}
        {success && (
          <Alert color="green" onClose={() => setSuccess('')} withCloseButton>
            {success}
          </Alert>
        )}

        <Card shadow="sm" padding="lg" radius="md" withBorder>
          <Stack gap="md">
            <Group>
              <Avatar size="lg" radius="xl">
                {initial}
              </Avatar>
              <div>
                <Text fw={500}>{displayName || 'No name set'}</Text>
                <Text size="sm" c="dimmed">
                  {user?.email}
                </Text>
              </div>
            </Group>

            <TextInput
              label="Display Name"
              value={displayName}
              onChange={(e) => setDisplayName(e.currentTarget.value)}
              placeholder="Your display name"
            />

            <Button onClick={handleSave} loading={saving}>
              Save Profile
            </Button>
          </Stack>
        </Card>

        <Card shadow="sm" padding="lg" radius="md" withBorder>
          <Stack gap="md">
            <Title order={4}>Account</Title>
            <Text size="sm" c="dimmed">
              Signed in as {user?.email}
            </Text>
            <Button color="red" variant="outline" onClick={handleSignOut}>
              Sign Out
            </Button>
          </Stack>
        </Card>

        <Card shadow="sm" padding="lg" radius="md" withBorder>
          <Stack gap="md">
            <Title order={4}>Notification Settings</Title>

            {!pushSupported && (
              <Text size="sm" c="dimmed">
                Push notifications are not supported in this browser.
              </Text>
            )}

            {pushSupported && pushPermission === 'denied' && (
              <Alert color="yellow">
                Push notifications are blocked. Please enable them in your browser settings.
              </Alert>
            )}

            {pushSupported && pushPermission !== 'denied' && (
              <>
                {!pushSubscribed ? (
                  <Button
                    onClick={pushSubscribe}
                    loading={pushLoading}
                    variant="light"
                  >
                    Enable Push Notifications
                  </Button>
                ) : (
                  <>
                    <Text size="sm" c="green">
                      ✓ Push notifications enabled
                    </Text>

                    <Switch
                      label="Draft turn notifications"
                      description="Get notified when it's your turn to draft"
                      checked={pushPreferences.draftTurn}
                      onChange={(e) =>
                        setPushPreferences({
                          draftTurn: e.currentTarget.checked,
                        })
                      }
                    />

                    <Switch
                      label="Scoring milestone notifications"
                      description="Get notified on scoring milestones (goals, shutouts)"
                      checked={pushPreferences.scoringMilestones}
                      onChange={(e) =>
                        setPushPreferences({
                          scoringMilestones: e.currentTarget.checked,
                        })
                      }
                    />

                    <Button
                      color="red"
                      variant="subtle"
                      onClick={pushUnsubscribe}
                      loading={pushLoading}
                    >
                      Disable Push Notifications
                    </Button>
                  </>
                )}
              </>
            )}
          </Stack>
        </Card>
      </Stack>
    </Container>
  );
}
