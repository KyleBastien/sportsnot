import { describe, expect, it } from '@rstest/core';
import {
  canStartNativeSwipeBack,
  shouldAbortNativeSwipeBackClaim,
  shouldClaimNativeSwipeBack,
  shouldCommitNativeSwipeBack,
} from './nativeSwipeBackGesture';

describe('nativeSwipeBackGesture', () => {
  it('requires a one-finger edge start on an eligible route', () => {
    expect(
      canStartNativeSwipeBack({
        touchCount: 1,
        startX: 18,
        isEligible: true,
        hasBlockingOverlay: false,
      })
    ).toBe(true);

    expect(
      canStartNativeSwipeBack({
        touchCount: 2,
        startX: 18,
        isEligible: true,
        hasBlockingOverlay: false,
      })
    ).toBe(false);

    expect(
      canStartNativeSwipeBack({
        touchCount: 1,
        startX: 48,
        isEligible: true,
        hasBlockingOverlay: false,
      })
    ).toBe(false);
  });

  it('does not start when route is blocked or overlay is open', () => {
    expect(
      canStartNativeSwipeBack({
        touchCount: 1,
        startX: 12,
        isEligible: false,
        hasBlockingOverlay: false,
      })
    ).toBe(false);

    expect(
      canStartNativeSwipeBack({
        touchCount: 1,
        startX: 12,
        isEligible: true,
        hasBlockingOverlay: true,
      })
    ).toBe(false);
  });

  it('claims horizontal intent and leaves vertical scroll alone', () => {
    expect(
      shouldClaimNativeSwipeBack({
        deltaX: 24,
        deltaY: 8,
      })
    ).toBe(true);

    expect(
      shouldClaimNativeSwipeBack({
        deltaX: 12,
        deltaY: 24,
      })
    ).toBe(false);

    expect(
      shouldAbortNativeSwipeBackClaim({
        deltaX: 8,
        deltaY: 24,
      })
    ).toBe(true);
  });

  it('commits on distance threshold or velocity threshold', () => {
    expect(
      shouldCommitNativeSwipeBack({
        distancePx: 140,
        velocityPxPerMs: 0.1,
        viewportWidthPx: 375,
      })
    ).toBe(true);

    expect(
      shouldCommitNativeSwipeBack({
        distancePx: 80,
        velocityPxPerMs: 0.7,
        viewportWidthPx: 375,
      })
    ).toBe(true);

    expect(
      shouldCommitNativeSwipeBack({
        distancePx: 80,
        velocityPxPerMs: 0.2,
        viewportWidthPx: 375,
      })
    ).toBe(false);
  });
});
