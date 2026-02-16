import { describe, it, expect } from '@rstest/core';
import { routes } from './routes';

describe('routes', () => {
  describe('leagues', () => {
    it('should generate correct league dashboard path with plural /leagues/', () => {
      expect(routes.leagues.dashboard('abc-123')).toBe('/leagues/abc-123');
    });

    it('should not generate singular /league/ path', () => {
      const path = routes.leagues.dashboard('test-id');
      expect(path).not.toContain('/league/test-id');
      expect(path).toContain('/leagues/test-id');
    });

    it('should generate correct league settings path', () => {
      expect(routes.leagues.settings('abc-123')).toBe(
        '/leagues/abc-123/settings'
      );
    });

    it('should generate correct create league path', () => {
      expect(routes.leagues.create()).toBe('/leagues/create');
    });

    it('should generate correct join league path', () => {
      expect(routes.leagues.join()).toBe('/leagues/join');
    });
  });

  describe('draft', () => {
    it('should generate correct draft lobby path', () => {
      expect(routes.draft.lobby('draft-1')).toBe('/draft/draft-1/lobby');
    });

    it('should generate correct draft board path', () => {
      expect(routes.draft.board('draft-1')).toBe('/draft/draft-1');
    });
  });
});
