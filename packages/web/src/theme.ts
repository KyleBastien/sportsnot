import { createTheme, type MantineColorsTuple } from '@mantine/core';

// Navy blue 10-shade scale (primary)
const navy: MantineColorsTuple = [
  '#E8EDF4', // 0 — lightest
  '#C4D1E3', // 1
  '#9DB4D0', // 2
  '#7597BD', // 3
  '#4E7AAA', // 4
  '#2D5A8E', // 5
  '#1B3A5F', // 6 — base (primary)
  '#122845', // 7 — dark
  '#0C1C31', // 8
  '#07111F', // 9 — darkest
];

// Gold 10-shade scale (accent)
const gold: MantineColorsTuple = [
  '#FDF6E8', // 0
  '#F8E8C4', // 1
  '#F0D699', // 2
  '#E7C36E', // 3
  '#DDB65C', // 4
  '#D4A843', // 5
  '#A67C2E', // 6 — base (accessible on white ≥3:1)
  '#8E6923', // 7
  '#836122', // 8
  '#604718', // 9
];

export const theme = createTheme({
  primaryColor: 'navy',
  primaryShade: { light: 6, dark: 4 },
  colors: {
    navy,
    gold,
  },
  fontFamily:
    '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
  headings: {
    fontFamily:
      '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
  },
  components: {
    Button: {
      defaultProps: {
        radius: 'md',
      },
    },
    ActionIcon: {
      defaultProps: {
        radius: 'md',
      },
    },
    Paper: {
      defaultProps: {
        radius: 'md',
      },
    },
  },
});
