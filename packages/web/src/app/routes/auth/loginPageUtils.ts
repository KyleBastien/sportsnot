export function getSubtitleText(useOtp: boolean): string {
  return useOtp
    ? 'Enter your email to receive a one-time code'
    : 'Enter your email to receive a magic link';
}

export function getSubmitButtonText(useOtp: boolean): string {
  return useOtp ? 'Send Code' : 'Send Magic Link';
}

export function getOtpSentMessage(email: string): string {
  return `We sent a 6-digit code to ${email}`;
}

export function isOtpTokenComplete(token: string): boolean {
  return token.length === 6;
}

export const OTP_ERROR_MESSAGE = 'Invalid or expired code. Please try again.';

export const RESEND_COOLDOWN_SECONDS = 60;

export function getResendButtonText(cooldown: number): string {
  return cooldown > 0 ? `Resend code (${cooldown}s)` : 'Resend code';
}
