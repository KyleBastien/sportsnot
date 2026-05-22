import { Navigate, useParams } from 'react-router-dom';

export function RosterHistoryPage() {
  const { leagueId } = useParams<{ leagueId: string }>();

  if (!leagueId) {
    return <Navigate to="/" replace />;
  }

  return <Navigate to={`/roster/${leagueId}?round=1`} replace />;
}
