import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Container,
  Title,
  Text,
  TextInput,
  NumberInput,
  Button,
  Stack,
  Paper,
  Alert,
} from '@mantine/core';
import { useAuthContext } from '../../context/AuthContext';
import { supabase } from '@sportsnot/supabase';
import { generateInviteCode } from '@sportsnot/utils';
import { useMockCreateLeague } from '../../../mock/hooks/useMockLeagues';

const IS_MOCK = import.meta.env.VITE_MOCK_MODE === 'true';

export function CreateLeaguePage() {
  const navigate = useNavigate();
  const { user } = useAuthContext();
  const [name, setName] = useState('');
  const [teamName, setTeamName] = useState('');
  const [maxParticipants, setMaxParticipants] = useState<number>(8);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // eslint-disable-next-line react-hooks/rules-of-hooks
  const mockCreateLeague = IS_MOCK ? useMockCreateLeague() : null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!user) return;

    setLoading(true);
    setError(null);

    if (IS_MOCK && mockCreateLeague) {
      try {
        const result = await mockCreateLeague.mutateAsync({
          name,
          maxParticipants,
          teamName,
        });
        setLoading(false);
        navigate(`/leagues/${result.id}`);
      } catch (err: any) {
        setError(err.message);
        setLoading(false);
      }
      return;
    }

    const inviteCode = generateInviteCode();

    // Create the league
    const { data: league, error: leagueError } = await supabase
      .from('leagues')
      .insert({
        name,
        commissioner_id: user.id,
        invite_code: inviteCode,
        max_participants: maxParticipants,
      })
      .select()
      .single();

    if (leagueError) {
      setError(leagueError.message);
      setLoading(false);
      return;
    }

    // Auto-join as first member
    const { error: memberError } = await supabase
      .from('league_members')
      .insert({
        league_id: league.id,
        user_id: user.id,
        team_name: teamName,
      });

    if (memberError) {
      setError(memberError.message);
      setLoading(false);
      return;
    }

    setLoading(false);
    navigate(`/leagues/${league.id}`);
  };

  return (
    <Container size="sm" py="xl">
      <Paper shadow="md" p="xl" radius="md" withBorder>
        <Stack gap="md">
          <Title order={2}>Create a League</Title>
          <Text c="dimmed" size="sm">
            Set up your playoff hockey league and invite friends
          </Text>

          {error && (
            <Alert color="red" title="Error">
              {error}
            </Alert>
          )}

          <form onSubmit={handleSubmit}>
            <Stack gap="md">
              <TextInput
                label="League Name"
                placeholder="The Stanley Cup Chasers"
                required
                value={name}
                onChange={(e) => setName(e.currentTarget.value)}
                size="md"
              />
              <TextInput
                label="Your Team Name"
                placeholder="Puck Dynasty"
                required
                value={teamName}
                onChange={(e) => setTeamName(e.currentTarget.value)}
                size="md"
              />
              <NumberInput
                label="Max Participants"
                min={2}
                max={12}
                value={maxParticipants}
                onChange={(val) => setMaxParticipants(Number(val))}
                size="md"
              />
              <Button type="submit" loading={loading} fullWidth size="md">
                Create League
              </Button>
            </Stack>
          </form>
        </Stack>
      </Paper>
    </Container>
  );
}
