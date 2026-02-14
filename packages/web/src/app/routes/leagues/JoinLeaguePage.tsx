import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Container,
  Title,
  Text,
  TextInput,
  Button,
  Stack,
  Paper,
  Alert,
  Group,
} from '@mantine/core';
import { useAuthContext } from '../../context/AuthContext';
import { supabase } from '@sportsnot/supabase';

export function JoinLeaguePage() {
  const navigate = useNavigate();
  const { user } = useAuthContext();
  const [inviteCode, setInviteCode] = useState('');
  const [teamName, setTeamName] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [leaguePreview, setLeaguePreview] = useState<{
    id: string;
    name: string;
    memberCount: number;
    maxParticipants: number;
  } | null>(null);

  const handleLookup = async () => {
    setError(null);
    setLoading(true);

    const { data: league, error: lookupError } = await supabase
      .from('leagues')
      .select('id, name, max_participants, league_members(id)')
      .eq('invite_code', inviteCode.toUpperCase())
      .single();

    if (lookupError || !league) {
      setError('League not found. Check your invite code.');
      setLoading(false);
      return;
    }

    const memberCount = (league as any).league_members?.length ?? 0;

    if (memberCount >= league.max_participants) {
      setError('This league is full.');
      setLoading(false);
      return;
    }

    setLeaguePreview({
      id: league.id,
      name: league.name,
      memberCount,
      maxParticipants: league.max_participants,
    });
    setLoading(false);
  };

  const handleJoin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!user || !leaguePreview) return;

    setLoading(true);
    setError(null);

    const { error: joinError } = await supabase
      .from('league_members')
      .insert({
        league_id: leaguePreview.id,
        user_id: user.id,
        team_name: teamName,
      });

    if (joinError) {
      if (joinError.message.includes('unique')) {
        setError('You are already a member of this league.');
      } else {
        setError(joinError.message);
      }
      setLoading(false);
      return;
    }

    setLoading(false);
    navigate(`/leagues/${leaguePreview.id}`);
  };

  return (
    <Container size="sm" py="xl">
      <Paper shadow="md" p="xl" radius="md" withBorder>
        <Stack gap="md">
          <Title order={2}>Join a League</Title>
          <Text c="dimmed" size="sm">
            Enter an invite code to join an existing league
          </Text>

          {error && (
            <Alert color="red" title="Error">
              {error}
            </Alert>
          )}

          {!leaguePreview ? (
            <Stack gap="md">
              <TextInput
                label="Invite Code"
                placeholder="ABCD1234"
                required
                value={inviteCode}
                onChange={(e) =>
                  setInviteCode(e.currentTarget.value.toUpperCase())
                }
                size="md"
                styles={{
                  input: { textTransform: 'uppercase', letterSpacing: 2 },
                }}
              />
              <Button
                onClick={handleLookup}
                loading={loading}
                fullWidth
                size="md"
              >
                Find League
              </Button>
            </Stack>
          ) : (
            <form onSubmit={handleJoin}>
              <Stack gap="md">
                <Paper p="md" withBorder bg="gray.0">
                  <Group justify="space-between">
                    <div>
                      <Text fw={600}>{leaguePreview.name}</Text>
                      <Text size="sm" c="dimmed">
                        {leaguePreview.memberCount} /{' '}
                        {leaguePreview.maxParticipants} members
                      </Text>
                    </div>
                    <Button
                      variant="subtle"
                      size="xs"
                      onClick={() => setLeaguePreview(null)}
                    >
                      Change
                    </Button>
                  </Group>
                </Paper>

                <TextInput
                  label="Your Team Name"
                  placeholder="Puck Dynasty"
                  required
                  value={teamName}
                  onChange={(e) => setTeamName(e.currentTarget.value)}
                  size="md"
                />
                <Button type="submit" loading={loading} fullWidth size="md">
                  Join League
                </Button>
              </Stack>
            </form>
          )}
        </Stack>
      </Paper>
    </Container>
  );
}
