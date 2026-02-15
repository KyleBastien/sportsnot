import { Alert } from '@mantine/core';

export function MockModeBanner() {
  return (
    <Alert
      color="yellow"
      radius={0}
      styles={{
        root: {
          position: 'sticky',
          top: 0,
          zIndex: 1000,
          textAlign: 'center',
          fontWeight: 700,
          padding: '6px 16px',
        },
      }}
    >
      🧪 Mock Mode
    </Alert>
  );
}
