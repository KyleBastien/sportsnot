export function getSubtitleText(useOtp: boolean): string {
  return useOtp
    ? 'Enter your email to receive a one-time code'
    : 'Enter your email to receive a magic link';
}

export function getSubmitButtonText(useOtp: boolean): string {
  return useOtp ? 'Send Code' : 'Send Magic Link';
}
