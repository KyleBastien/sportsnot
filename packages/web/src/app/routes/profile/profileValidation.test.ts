import { describe, it, expect } from '@rstest/core';
import {
  DISPLAY_NAME_MAX_LENGTH,
  validateDisplayName,
} from './profileValidation';

describe('profileValidation', () => {
  describe('DISPLAY_NAME_MAX_LENGTH', () => {
    it('should be 30', () => {
      expect(DISPLAY_NAME_MAX_LENGTH).toBe(30);
    });
  });

  describe('validateDisplayName', () => {
    it('should reject an empty string', () => {
      expect(validateDisplayName('')).toBe('Display name is required');
    });

    it('should reject a whitespace-only string', () => {
      expect(validateDisplayName('   ')).toBe('Display name is required');
      expect(validateDisplayName('\t')).toBe('Display name is required');
    });

    it('should accept a valid name', () => {
      expect(validateDisplayName('Player One')).toBeNull();
    });

    it('should accept a name at exactly 30 characters', () => {
      const name = 'A'.repeat(30);
      expect(name.length).toBe(30);
      expect(validateDisplayName(name)).toBeNull();
    });

    it('should accept a single character name', () => {
      expect(validateDisplayName('A')).toBeNull();
    });
  });

  describe('character count display', () => {
    it('should produce correct count string for empty input', () => {
      const name = '';
      const countStr = `${name.length}/${DISPLAY_NAME_MAX_LENGTH}`;
      expect(countStr).toBe('0/30');
    });

    it('should produce correct count string for partial input', () => {
      const name = 'Hello World';
      const countStr = `${name.length}/${DISPLAY_NAME_MAX_LENGTH}`;
      expect(countStr).toBe('11/30');
    });

    it('should produce correct count string at max length', () => {
      const name = 'A'.repeat(30);
      const countStr = `${name.length}/${DISPLAY_NAME_MAX_LENGTH}`;
      expect(countStr).toBe('30/30');
    });
  });
});
