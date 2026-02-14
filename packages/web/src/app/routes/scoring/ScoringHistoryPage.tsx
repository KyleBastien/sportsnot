import { useParams } from 'react-router-dom';
import { Container, Title, Text, Alert, Stack } from '@mantine/core';

export function ScoringHistoryPage() {
  const { leagueId } = useParams<{ leagueId: string }>();

  if (!leagueId) {
    return (
      <Container size="md" py="xl">
        <Alert color="red" title="Error">
          No league selected.
        </Alert>
      </Container>
    );
  }

  return (
    <Container size="lg" py="xl">
      <Stack gap="xl">
        <Title order={2}>Scoring History</Title>
        <Text c="dimmed">View scoring events for this league.</Text>
      </Stack>
    </Container>
  );
}
