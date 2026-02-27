import { describe, it, expect } from '@rstest/core';
import { getSubtitleText, getSubmitButtonText } from './loginPageUtils';

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
});
