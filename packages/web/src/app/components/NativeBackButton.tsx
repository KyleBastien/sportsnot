import { useLocation, useNavigate } from 'react-router-dom';
import { ActionIcon } from '@mantine/core';
import { IconChevronLeft } from '@tabler/icons-react';
import { useIsNativeIOS } from '../hooks/useIsNativeIOS';
import { getNativeBackDestination } from '../navigation/nativeBackNavigation';

export function NativeBackButton() {
  const isNativeIOS = useIsNativeIOS();
  const { pathname } = useLocation();
  const navigate = useNavigate();

  if (!isNativeIOS) return null;

  const destination = getNativeBackDestination(pathname);
  if (!destination) return null;

  return (
    <ActionIcon
      variant="subtle"
      size="lg"
      aria-label="Go back"
      onClick={() => navigate(destination)}
    >
      <IconChevronLeft size={24} />
    </ActionIcon>
  );
}
