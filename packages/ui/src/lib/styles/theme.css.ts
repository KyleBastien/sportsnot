import {
  createGlobalTheme,
  createGlobalThemeContract,
  globalStyle,
} from '@vanilla-extract/css';

export const vars = createGlobalThemeContract({
  color: {
    primary: '',
    primaryDark: '',
    primaryLight: '',
    secondary: '',
    accent: '',
    background: '',
    surface: '',
    surfaceHover: '',
    text: '',
    textMuted: '',
    textInverse: '',
    border: '',
    success: '',
    warning: '',
    error: '',
    info: '',
  },
  space: {
    none: '',
    xs: '',
    sm: '',
    md: '',
    lg: '',
    xl: '',
    xxl: '',
  },
  fontSize: {
    xs: '',
    sm: '',
    md: '',
    lg: '',
    xl: '',
    xxl: '',
    xxxl: '',
  },
  fontWeight: {
    normal: '',
    medium: '',
    semibold: '',
    bold: '',
  },
  radius: {
    sm: '',
    md: '',
    lg: '',
    full: '',
  },
  shadow: {
    sm: '',
    md: '',
    lg: '',
  },
});

// Light mode (default)
createGlobalTheme(':root', vars, {
  color: {
    primary: '#1B3A5F',
    primaryDark: '#122845',
    primaryLight: '#2D5A8E',
    secondary: '#8C939A',
    accent: '#A67C2E',
    background: '#F5F6F8',
    surface: '#FFFFFF',
    surfaceHover: '#EEF0F3',
    text: '#1A1D21',
    textMuted: '#5C6370',
    textInverse: '#FFFFFF',
    border: '#D0D4DA',
    success: '#2F9E44',
    warning: '#F59F00',
    error: '#E03131',
    info: '#1B3A5F',
  },
  space: {
    none: '0',
    xs: '4px',
    sm: '8px',
    md: '16px',
    lg: '24px',
    xl: '32px',
    xxl: '48px',
  },
  fontSize: {
    xs: '0.75rem',
    sm: '0.875rem',
    md: '1rem',
    lg: '1.125rem',
    xl: '1.25rem',
    xxl: '1.5rem',
    xxxl: '2rem',
  },
  fontWeight: {
    normal: '400',
    medium: '500',
    semibold: '600',
    bold: '700',
  },
  radius: {
    sm: '4px',
    md: '8px',
    lg: '12px',
    full: '9999px',
  },
  shadow: {
    sm: '0 1px 2px rgba(0, 0, 0, 0.05)',
    md: '0 4px 6px rgba(0, 0, 0, 0.1)',
    lg: '0 10px 15px rgba(0, 0, 0, 0.15)',
  },
});

// Dark mode — overrides color tokens when Mantine dark scheme is active
const darkSelector = ':root[data-mantine-color-scheme="dark"]';

globalStyle(darkSelector, {
  vars: {
    [vars.color.primary]: '#4A8FD4',
    [vars.color.primaryDark]: '#3A7BC0',
    [vars.color.primaryLight]: '#6AACEB',
    [vars.color.secondary]: '#9EA5AD',
    [vars.color.accent]: '#DDB65C',
    [vars.color.background]: '#0F1318',
    [vars.color.surface]: '#1A1F28',
    [vars.color.surfaceHover]: '#242B36',
    [vars.color.text]: '#E8EAED',
    [vars.color.textMuted]: '#A0A8B2',
    [vars.color.textInverse]: '#1A1D21',
    [vars.color.border]: '#2E3642',
    [vars.color.success]: '#51CF66',
    [vars.color.warning]: '#FFD43B',
    [vars.color.error]: '#FF6B6B',
    [vars.color.info]: '#4A8FD4',
  },
});
