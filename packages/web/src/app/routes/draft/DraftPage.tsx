import { useNavigate, useParams } from 'react-router-dom';
import { useAuthContext } from '../../context/AuthContext';
import {
  DraftPageCompleteView,
  DraftPageLoadingState,
  DraftPageNoDraftState,
  DraftPageView,
} from './DraftPageView';
import { useDraftPageController } from './useDraftPageController';

export function DraftPage() {
  const { leagueId } = useParams<{ leagueId: string }>();
  const navigate = useNavigate();
  const { user } = useAuthContext();

  const { status, completeViewProps, readyViewProps } = useDraftPageController({
    leagueId: leagueId ?? '',
    userId: user?.id,
    navigate,
  });

  if (status === 'loading') {
    return <DraftPageLoadingState />;
  }

  if (!leagueId || status === 'no-draft') {
    return <DraftPageNoDraftState />;
  }

  if (status === 'completed') {
    return completeViewProps ? (
      <DraftPageCompleteView {...completeViewProps} />
    ) : (
      <DraftPageNoDraftState />
    );
  }

  return readyViewProps ? (
    <DraftPageView {...readyViewProps} />
  ) : (
    <DraftPageNoDraftState />
  );
}
