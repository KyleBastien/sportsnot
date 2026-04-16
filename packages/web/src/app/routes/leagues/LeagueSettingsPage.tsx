import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Container,
  Title,
  Text,
  Stack,
  Group,
  Card,
  Button,
  TextInput,
  NumberInput,
  Alert,
  Modal,
  Loader,
  Center,
  Table,
  ActionIcon,
  CopyButton,
  Tooltip,
  Switch,
} from '@mantine/core';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { supabase } from '@sportsnot/supabase';
import { useAuthContext } from '../../context/AuthContext';
import { generateInviteCode } from '@sportsnot/utils';
import { useMockLeague } from '../../../mock/hooks/useMockLeagues';

const IS_MOCK = import.meta.env.VITE_MOCK_MODE === 'true';

interface SettingsMemberRow {
  id: string;
  user_id: string;
  team_name: string;
  total_points: number;
  users?: { display_name?: string } | null;
}

export function LeagueSettingsPage() {
  const { leagueId } = useParams<{ leagueId: string }>();
  const { user } = useAuthContext();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const mockResult = useMockLeague(leagueId);

  const [leagueName, setLeagueName] = useState(
    IS_MOCK && mockResult.data ? mockResult.data.name : ''
  );
  const [maxParticipants, setMaxParticipants] = useState<number>(
    IS_MOCK && mockResult.data ? mockResult.data.max_participants : 12
  );
  const [allowIrSlots, setAllowIrSlots] = useState<boolean>(
    IS_MOCK && mockResult.data
      ? (mockResult.data.allow_ir_slots ?? true)
      : true
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [removeMemberId, setRemoveMemberId] = useState<string | null>(null);

  const realResult = useQuery({
    queryKey: ['league-settings', leagueId],
    queryFn: async () => {
      const { data, error: fetchError } = await supabase
        .from('leagues')
        .select(
          '*, league_members(id, user_id, team_name, total_points, users(display_name))'
        )
        .eq('id', leagueId!)
        .single();

      if (fetchError) throw fetchError;

      setLeagueName(data.name);
      setMaxParticipants(data.max_participants);
      setAllowIrSlots(data.allow_ir_slots ?? true);
      return data;
    },
    enabled: !IS_MOCK && !!leagueId,
  });

  const { data: league, isLoading } = IS_MOCK ? mockResult : realResult;

  const isCommissioner = league?.commissioner_id === user?.id;
  const canModify = isCommissioner && league?.status === 'setup';
  // IR setting can be changed during setup or while round 1 draft is in progress
  const canModifyIr =
    isCommissioner &&
    (league?.status === 'setup' ||
      (league?.status === 'drafting' && (league?.current_round ?? 0) <= 1));

  const handleSave = async () => {
    if (!leagueId || !leagueName.trim()) return;
    if (IS_MOCK) {
      setSuccess('Settings saved!');
      setTimeout(() => setSuccess(''), 3000);
      return;
    }
    setSaving(true);
    setError('');

    const { error: updateError } = await supabase
      .from('leagues')
      .update({
        name: leagueName.trim(),
        max_participants: maxParticipants,
        allow_ir_slots: allowIrSlots,
      })
      .eq('id', leagueId);

    if (updateError) {
      setError(updateError.message);
    } else {
      setSuccess('Settings saved!');
      queryClient.invalidateQueries({ queryKey: ['league', leagueId] });
      setTimeout(() => setSuccess(''), 3000);
    }
    setSaving(false);
  };

  const handleRegenerateCode = async () => {
    if (!leagueId) return;
    if (IS_MOCK) {
      setSuccess('Invite code regenerated!');
      setTimeout(() => setSuccess(''), 3000);
      return;
    }
    const newCode = generateInviteCode();

    const { error: updateError } = await supabase
      .from('leagues')
      .update({ invite_code: newCode })
      .eq('id', leagueId);

    if (updateError) {
      setError(updateError.message);
    } else {
      queryClient.invalidateQueries({
        queryKey: ['league-settings', leagueId],
      });
      setSuccess('Invite code regenerated!');
      setTimeout(() => setSuccess(''), 3000);
    }
  };

  const removeMember = useMutation({
    mutationFn: async (memberId: string) => {
      if (IS_MOCK) return;
      const { error: removeError } = await supabase
        .from('league_members')
        .delete()
        .eq('id', memberId);

      if (removeError) throw removeError;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ['league-settings', leagueId],
      });
      setRemoveMemberId(null);
      setSuccess('Member removed.');
      setTimeout(() => setSuccess(''), 3000);
    },
    onError: (err: Error) => setError(err.message),
  });

  const handleStartDraft = async () => {
    if (!league) return;
    if (IS_MOCK) {
      navigate(`/draft/${leagueId}`);
      return;
    }
    const members = league.league_members ?? [];
    if (members.length < 2) {
      setError('Need at least 2 members to start a draft');
      return;
    }

    // Randomize draft order for round 1
    const memberUserIds = members.map((m: SettingsMemberRow) => m.user_id);
    const shuffled = [...memberUserIds].sort(() => Math.random() - 0.5);

    const { error: draftError } = await supabase.from('drafts').insert({
      league_id: leagueId,
      round: (league.current_round ?? 0) + 1,
      status: 'active',
      current_pick: 1,
      draft_order: shuffled,
      started_at: new Date().toISOString(),
    });

    if (draftError) {
      setError(draftError.message);
      return;
    }

    await supabase
      .from('leagues')
      .update({
        status: 'drafting',
        current_round: (league.current_round ?? 0) + 1,
      })
      .eq('id', leagueId);

    navigate(`/draft/${leagueId}`);
  };

  if (isLoading) {
    return (
      <Center h="50vh">
        <Loader size="lg" />
      </Center>
    );
  }

  if (!league) {
    return (
      <Container size="md" py="xl">
        <Alert color="red">League not found</Alert>
      </Container>
    );
  }

  if (!isCommissioner) {
    return (
      <Container size="md" py="xl">
        <Alert color="yellow" title="Access Denied">
          Only the commissioner can manage league settings.
        </Alert>
      </Container>
    );
  }

  const members = league.league_members ?? [];

  return (
    <Container size="md" py="xl">
      <Stack gap="xl">
        <Group justify="space-between">
          <Title order={2}>League Settings</Title>
          <Button
            variant="subtle"
            onClick={() => navigate(`/leagues/${leagueId}`)}
          >
            Back to League
          </Button>
        </Group>

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

        {/* General Settings */}
        <Card shadow="sm" padding="lg" radius="md" withBorder>
          <Stack gap="md">
            <Title order={4}>General</Title>
            <TextInput
              label="League Name"
              value={leagueName}
              onChange={(e) => setLeagueName(e.currentTarget.value)}
              disabled={!canModify}
            />
            <NumberInput
              label="Max Participants"
              value={maxParticipants}
              onChange={(val) => setMaxParticipants(Number(val) || 12)}
              min={2}
              max={12}
              disabled={!canModify}
            />
            <Switch
              label="Allow IR (Injured Reserve) Slots"
              description="When disabled, IR Forward and IR Defenseman roster slots are removed from drafts and rosters."
              checked={allowIrSlots}
              onChange={(event) =>
                setAllowIrSlots(event.currentTarget.checked)
              }
              disabled={!canModifyIr}
            />
            {(canModify || canModifyIr) && (
              <Button onClick={handleSave} loading={saving}>
                Save Changes
              </Button>
            )}
          </Stack>
        </Card>

        {/* Invite Code */}
        <Card shadow="sm" padding="lg" radius="md" withBorder>
          <Stack gap="md">
            <Title order={4}>Invite Code</Title>
            <Group>
              <Text ff="monospace" fw={700} size="lg">
                {league.invite_code}
              </Text>
              <CopyButton value={league.invite_code}>
                {({ copied, copy }) => (
                  <Tooltip label={copied ? 'Copied' : 'Copy'}>
                    <Button
                      variant="light"
                      size="xs"
                      onClick={copy}
                      color={copied ? 'teal' : 'blue'}
                    >
                      {copied ? 'Copied!' : 'Copy'}
                    </Button>
                  </Tooltip>
                )}
              </CopyButton>
            </Group>
            {canModify && (
              <Button variant="outline" onClick={handleRegenerateCode}>
                Regenerate Code
              </Button>
            )}
          </Stack>
        </Card>

        {/* Members */}
        <Card shadow="sm" padding="lg" radius="md" withBorder>
          <Stack gap="md">
            <Title order={4}>Members ({members.length})</Title>
            <Table>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Player</Table.Th>
                  <Table.Th>Team Name</Table.Th>
                  <Table.Th>Points</Table.Th>
                  {canModify && <Table.Th>Actions</Table.Th>}
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {members.map((m: SettingsMemberRow) => (
                  <Table.Tr key={m.id}>
                    <Table.Td>
                      {m.users?.display_name ?? 'Unknown'}
                      {m.user_id === league.commissioner_id && ' 👑'}
                    </Table.Td>
                    <Table.Td>{m.team_name}</Table.Td>
                    <Table.Td>{m.total_points ?? 0}</Table.Td>
                    {canModify && (
                      <Table.Td>
                        {m.user_id !== league.commissioner_id && (
                          <ActionIcon
                            color="red"
                            variant="subtle"
                            onClick={() => setRemoveMemberId(m.id)}
                          >
                            ✕
                          </ActionIcon>
                        )}
                      </Table.Td>
                    )}
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Stack>
        </Card>

        {/* Draft Controls */}
        <Card shadow="sm" padding="lg" radius="md" withBorder>
          <Stack gap="md">
            <Title order={4}>Draft Controls</Title>
            <Text c="dimmed" size="sm">
              Status: <strong>{league.status}</strong> | Round:{' '}
              <strong>{league.current_round ?? 0}</strong>
            </Text>
            {league.status === 'setup' && (
              <Button color="green" onClick={handleStartDraft}>
                Start Round 1 Draft
              </Button>
            )}
            {league.status === 'active' && (
              <Button color="green" onClick={handleStartDraft}>
                Start Round {(league.current_round ?? 0) + 1} Re-Draft
              </Button>
            )}
          </Stack>
        </Card>

        {/* Remove Member Modal */}
        <Modal
          opened={!!removeMemberId}
          onClose={() => setRemoveMemberId(null)}
          title="Remove Member"
        >
          <Stack gap="md">
            <Text>
              Are you sure you want to remove this member from the league?
            </Text>
            <Group justify="flex-end">
              <Button variant="subtle" onClick={() => setRemoveMemberId(null)}>
                Cancel
              </Button>
              <Button
                color="red"
                loading={removeMember.isPending}
                onClick={() =>
                  removeMemberId && removeMember.mutate(removeMemberId)
                }
              >
                Remove
              </Button>
            </Group>
          </Stack>
        </Modal>
      </Stack>
    </Container>
  );
}
