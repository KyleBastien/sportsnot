export const NATIVE_SWIPE_BACK_EDGE_ZONE_PX = 24;
export const NATIVE_SWIPE_BACK_INTENT_SLOP_PX = 12;
export const NATIVE_SWIPE_BACK_COMMIT_PROGRESS = 0.33;
export const NATIVE_SWIPE_BACK_COMMIT_VELOCITY_PX_PER_MS = 0.55;

interface NativeSwipeBackStartInput {
  touchCount: number;
  startX: number;
  isEligible: boolean;
  hasBlockingOverlay: boolean;
  edgeZonePx?: number;
}

interface NativeSwipeBackIntentInput {
  deltaX: number;
  deltaY: number;
  intentSlopPx?: number;
}

interface NativeSwipeBackCommitInput {
  distancePx: number;
  velocityPxPerMs: number;
  viewportWidthPx: number;
  progressThreshold?: number;
  velocityThresholdPxPerMs?: number;
}

export function canStartNativeSwipeBack({
  touchCount,
  startX,
  isEligible,
  hasBlockingOverlay,
  edgeZonePx = NATIVE_SWIPE_BACK_EDGE_ZONE_PX,
}: NativeSwipeBackStartInput): boolean {
  return (
    touchCount === 1 &&
    isEligible &&
    !hasBlockingOverlay &&
    startX <= edgeZonePx
  );
}

export function shouldClaimNativeSwipeBack({
  deltaX,
  deltaY,
  intentSlopPx = NATIVE_SWIPE_BACK_INTENT_SLOP_PX,
}: NativeSwipeBackIntentInput): boolean {
  const verticalDelta = Math.abs(deltaY);

  return deltaX > intentSlopPx && deltaX > verticalDelta;
}

export function shouldAbortNativeSwipeBackClaim({
  deltaX,
  deltaY,
  intentSlopPx = NATIVE_SWIPE_BACK_INTENT_SLOP_PX,
}: NativeSwipeBackIntentInput): boolean {
  const verticalDelta = Math.abs(deltaY);

  return verticalDelta > intentSlopPx && verticalDelta > Math.max(deltaX, 0);
}

export function shouldCommitNativeSwipeBack({
  distancePx,
  velocityPxPerMs,
  viewportWidthPx,
  progressThreshold = NATIVE_SWIPE_BACK_COMMIT_PROGRESS,
  velocityThresholdPxPerMs = NATIVE_SWIPE_BACK_COMMIT_VELOCITY_PX_PER_MS,
}: NativeSwipeBackCommitInput): boolean {
  const viewportWidth = Math.max(viewportWidthPx, 1);
  const commitDistance = viewportWidth * progressThreshold;

  return (
    distancePx >= commitDistance || velocityPxPerMs >= velocityThresholdPxPerMs
  );
}
