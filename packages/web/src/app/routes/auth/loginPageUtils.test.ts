import { describe, it, expect } from '@rstest/core';
import {
  getSubtitleText,
  getSubmitButtonText,
  getOtpSentMessage,
  isOtpTokenComplete,
  OTP_ERROR_MESSAGE,
  RESEND_COOLDOWN_SECONDS,
  getResendButtonText,
} from './loginPageUtils';

describe('loginPageUtils', () => {
  describe('getSubtitleText', () => {
    it('should return OTP subtitle when useOtp is true', () => {
      expect(getSubtitleText(true)).toBe(
        'Enter your email to receive a one-time code'
      );
    });

    it('should return magic link subtitle when useOtp is false', () => {
      expect(getSubtitleText(false)).toBe(
        'Enter your email to receive a magic link'
      );
    });
  });

  describe('getSubmitButtonText', () => {
    it('should return "Send Code" when useOtp is true', () => {
      expect(getSubmitButtonText(true)).toBe('Send Code');
    });

    it('should return "Send Magic Link" when useOtp is false', () => {
      expect(getSubmitButtonText(false)).toBe('Send Magic Link');
    });
  });

  describe('getOtpSentMessage', () => {
    it('should include the email in the message', () => {
      expect(getOtpSentMessage('user@example.com')).toBe(
        'We sent a 6-digit code to user@example.com'
      );
    });

    it('should handle empty email', () => {
      expect(getOtpSentMessage('')).toBe('We sent a 6-digit code to ');
    });
  });

  describe('isOtpTokenComplete', () => {
    it('should return true for a 6-digit token', () => {
      expect(isOtpTokenComplete('123456')).toBe(true);
    });

    it('should return false for a token shorter than 6 characters', () => {
      expect(isOtpTokenComplete('12345')).toBe(false);
    });

    it('should return false for an empty token', () => {
      expect(isOtpTokenComplete('')).toBe(false);
    });

    it('should return false for a token longer than 6 characters', () => {
      expect(isOtpTokenComplete('1234567')).toBe(false);
    });
  });

  describe('OTP_ERROR_MESSAGE', () => {
    it('should have the correct error message', () => {
      expect(OTP_ERROR_MESSAGE).toBe(
        'Invalid or expired code. Please try again.'
      );
    });
  });

  describe('RESEND_COOLDOWN_SECONDS', () => {
    it('should be 60 seconds', () => {
      expect(RESEND_COOLDOWN_SECONDS).toBe(60);
    });
  });

  describe('getResendButtonText', () => {
    it('should return "Resend code" when cooldown is 0', () => {
      expect(getResendButtonText(0)).toBe('Resend code');
    });

    it('should return countdown text when cooldown is greater than 0', () => {
      expect(getResendButtonText(45)).toBe('Resend code (45s)');
    });

    it('should return countdown text with 1 second remaining', () => {
      expect(getResendButtonText(1)).toBe('Resend code (1s)');
    });

    it('should return countdown text at full cooldown', () => {
      expect(getResendButtonText(60)).toBe('Resend code (60s)');
    });

    it('should return "Resend code" for negative values', () => {
      expect(getResendButtonText(-1)).toBe('Resend code');
    });
  });
});
