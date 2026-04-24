import React, {
  useEffect,
  useLayoutEffect,
  useRef,
  type ReactNode,
} from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  canNativeSwipeBack,
  getNativeBackDestination,
} from '../navigation/nativeBackNavigation';
import {
  canStartNativeSwipeBack,
  shouldAbortNativeSwipeBackClaim,
  shouldClaimNativeSwipeBack,
  shouldCommitNativeSwipeBack,
} from '../navigation/nativeSwipeBackGesture';
import { isNativeMobilePlatform } from '../platform/nativeMobilePlatform';

const PREVIEW_CACHE_LIMIT = 12;
const PREVIEW_PARALLAX_RATIO = 0.12;
const PREVIEW_PARALLAX_MAX_PX = 36;
const SWIPE_BACK_ANIMATION_MS = 220;

type GesturePhase = 'pending' | 'dragging' | 'animating';

interface GestureSession {
  phase: GesturePhase;
  destination: string;
  viewportWidth: number;
  startX: number;
  startY: number;
  lastX: number;
  lastTime: number;
  distance: number;
  velocity: number;
  rafId: number | null;
  animationTimeoutId: number | null;
}

function getPrimaryTouch(
  event: React.TouchEvent<HTMLDivElement>
): { clientX: number; clientY: number } | null {
  const touch = event.touches[0] ?? event.changedTouches[0];

  if (!touch) {
    return null;
  }

  return {
    clientX: touch.clientX,
    clientY: touch.clientY,
  };
}

function getEventTimeStamp(event: React.TouchEvent<HTMLDivElement>): number {
  return typeof event.timeStamp === 'number' && event.timeStamp > 0
    ? event.timeStamp
    : performance.now();
}

function hasBlockingOverlay(documentRef: Document): boolean {
  return (
    documentRef.querySelector(
      '[role="dialog"], [role="menu"], [role="listbox"]'
    ) !== null
  );
}

function trimPreviewCache(cache: Map<string, HTMLElement>) {
  while (cache.size > PREVIEW_CACHE_LIMIT) {
    const oldestKey = cache.keys().next().value;

    if (!oldestKey) {
      return;
    }

    cache.delete(oldestKey);
  }
}

export function NativeSwipeBackFrame({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const frameRef = useRef<HTMLDivElement | null>(null);
  const underlayRef = useRef<HTMLDivElement | null>(null);
  const underlaySurfaceRef = useRef<HTMLDivElement | null>(null);
  const scrimRef = useRef<HTMLDivElement | null>(null);
  const pageRef = useRef<HTMLDivElement | null>(null);
  const pageSurfaceRef = useRef<HTMLDivElement | null>(null);
  const pageContentRef = useRef<HTMLDivElement | null>(null);
  const shadowRef = useRef<HTMLDivElement | null>(null);
  const previewCacheRef = useRef(new Map<string, HTMLElement>());
  const gestureRef = useRef<GestureSession | null>(null);
  const captureFrameRef = useRef<number | null>(null);
  const isNativeSwipeEnabled =
    isNativeMobilePlatform() && canNativeSwipeBack(pathname);

  const resetPresentation = () => {
    frameRef.current?.classList.remove(
      'native-swipe-back-frame--armed',
      'native-swipe-back-frame--active',
      'native-swipe-back-frame--animating'
    );

    if (underlaySurfaceRef.current) {
      underlaySurfaceRef.current.replaceChildren();
      underlaySurfaceRef.current.dataset.previewState = 'fallback';
    }

    if (underlayRef.current) {
      underlayRef.current.style.transform = '';
      underlayRef.current.style.opacity = '';
    }

    if (pageRef.current) {
      pageRef.current.style.transform = '';
    }

    if (scrimRef.current) {
      scrimRef.current.style.opacity = '';
    }

    if (shadowRef.current) {
      shadowRef.current.style.opacity = '';
    }
  };

  const clearGestureSession = () => {
    const session = gestureRef.current;

    if (!session) {
      return;
    }

    if (session.rafId != null) {
      cancelAnimationFrame(session.rafId);
    }

    if (session.animationTimeoutId != null) {
      window.clearTimeout(session.animationTimeoutId);
    }

    gestureRef.current = null;
  };

  const preparePreview = (destination: string) => {
    const underlaySurface = underlaySurfaceRef.current;

    if (!underlaySurface) {
      return;
    }

    const preview = previewCacheRef.current.get(destination);

    underlaySurface.replaceChildren();
    underlaySurface.dataset.previewState = preview ? 'cached' : 'fallback';

    if (preview) {
      underlaySurface.appendChild(preview.cloneNode(true));
    }
  };

  const applyDragPresentation = (distancePx: number) => {
    const session = gestureRef.current;

    if (!session || !underlayRef.current || !pageRef.current) {
      return;
    }

    const clampedDistance = Math.min(
      Math.max(distancePx, 0),
      session.viewportWidth
    );
    const progress = clampedDistance / Math.max(session.viewportWidth, 1);
    const previewOffset = Math.min(
      PREVIEW_PARALLAX_MAX_PX,
      session.viewportWidth * PREVIEW_PARALLAX_RATIO
    );

    pageRef.current.style.transform = `translate3d(${clampedDistance}px, 0, 0)`;
    underlayRef.current.style.transform = `translate3d(${
      -previewOffset * (1 - progress)
    }px, 0, 0)`;
    underlayRef.current.style.opacity = '1';

    if (scrimRef.current) {
      scrimRef.current.style.opacity = `${0.14 * (1 - progress)}`;
    }

    if (shadowRef.current) {
      shadowRef.current.style.opacity = `${0.18 * (1 - progress)}`;
    }
  };

  const scheduleDragFrame = () => {
    const session = gestureRef.current;

    if (!session || session.rafId != null) {
      return;
    }

    session.rafId = requestAnimationFrame(() => {
      const activeSession = gestureRef.current;

      if (!activeSession) {
        return;
      }

      activeSession.rafId = null;
      applyDragPresentation(activeSession.distance);
    });
  };

  const animateToDistance = (distancePx: number, onDone: () => void) => {
    const session = gestureRef.current;
    const frame = frameRef.current;

    if (!session || !frame) {
      onDone();
      return;
    }

    if (session.rafId != null) {
      cancelAnimationFrame(session.rafId);
      session.rafId = null;
    }

    session.phase = 'animating';
    frame.classList.add('native-swipe-back-frame--animating');

    requestAnimationFrame(() => {
      applyDragPresentation(distancePx);
    });

    session.animationTimeoutId = window.setTimeout(() => {
      const activeSession = gestureRef.current;

      if (!activeSession) {
        return;
      }

      activeSession.animationTimeoutId = null;
      onDone();
    }, SWIPE_BACK_ANIMATION_MS);
  };

  const cancelGesture = (animate = false) => {
    const session = gestureRef.current;

    if (!session) {
      resetPresentation();
      return;
    }

    if (session.phase === 'dragging' && animate) {
      animateToDistance(0, () => {
        clearGestureSession();
        resetPresentation();
      });
      return;
    }

    clearGestureSession();
    resetPresentation();
  };

  const updateGestureMetrics = (
    event: React.TouchEvent<HTMLDivElement>,
    session: GestureSession
  ) => {
    const touch = getPrimaryTouch(event);

    if (!touch) {
      return;
    }

    const time = getEventTimeStamp(event);
    const deltaX = Math.max(0, touch.clientX - session.startX);
    const timeDelta = Math.max(time - session.lastTime, 1);

    session.distance = Math.min(deltaX, session.viewportWidth);
    session.velocity = Math.max(0, touch.clientX - session.lastX) / timeDelta;
    session.lastX = touch.clientX;
    session.lastTime = time;
  };

  const handleTouchStart = (event: React.TouchEvent<HTMLDivElement>) => {
    if (!isNativeSwipeEnabled || gestureRef.current?.phase === 'animating') {
      return;
    }

    const destination = getNativeBackDestination(pathname);
    const touch = getPrimaryTouch(event);

    if (!destination || !touch) {
      return;
    }

    const frameWidth = Math.max(
      frameRef.current?.clientWidth ?? 0,
      window.innerWidth,
      1
    );

    if (
      !canStartNativeSwipeBack({
        touchCount: event.touches.length,
        startX: touch.clientX,
        isEligible: true,
        hasBlockingOverlay: hasBlockingOverlay(document),
      })
    ) {
      return;
    }

    clearGestureSession();
    preparePreview(destination);
    frameRef.current?.classList.add('native-swipe-back-frame--armed');

    gestureRef.current = {
      phase: 'pending',
      destination,
      viewportWidth: frameWidth,
      startX: touch.clientX,
      startY: touch.clientY,
      lastX: touch.clientX,
      lastTime: getEventTimeStamp(event),
      distance: 0,
      velocity: 0,
      rafId: null,
      animationTimeoutId: null,
    };
  };

  const handleTouchMove = (event: React.TouchEvent<HTMLDivElement>) => {
    const session = gestureRef.current;

    if (!session || session.phase === 'animating') {
      return;
    }

    if (event.touches.length !== 1) {
      cancelGesture(session.phase === 'dragging');
      return;
    }

    updateGestureMetrics(event, session);

    const deltaY =
      (event.touches[0]?.clientY ?? session.startY) - session.startY;

    if (session.phase === 'pending') {
      if (
        shouldAbortNativeSwipeBackClaim({
          deltaX: session.distance,
          deltaY,
        })
      ) {
        cancelGesture();
        return;
      }

      if (
        !shouldClaimNativeSwipeBack({
          deltaX: session.distance,
          deltaY,
        })
      ) {
        return;
      }

      session.phase = 'dragging';
      frameRef.current?.classList.add('native-swipe-back-frame--active');
    }

    event.preventDefault();
    scheduleDragFrame();
  };

  const handleTouchEnd = (event: React.TouchEvent<HTMLDivElement>) => {
    const session = gestureRef.current;

    if (!session) {
      return;
    }

    updateGestureMetrics(event, session);

    if (session.phase !== 'dragging') {
      cancelGesture();
      return;
    }

    const shouldCommit = shouldCommitNativeSwipeBack({
      distancePx: session.distance,
      velocityPxPerMs: session.velocity,
      viewportWidthPx: session.viewportWidth,
    });

    if (!shouldCommit) {
      animateToDistance(0, () => {
        clearGestureSession();
        resetPresentation();
      });
      return;
    }

    animateToDistance(session.viewportWidth, () => {
      const destination = session.destination;

      clearGestureSession();
      navigate(destination);
    });
  };

  useLayoutEffect(() => {
    resetPresentation();
    clearGestureSession();

    if (captureFrameRef.current != null) {
      cancelAnimationFrame(captureFrameRef.current);
    }

    if (!isNativeMobilePlatform()) {
      return;
    }

    captureFrameRef.current = requestAnimationFrame(() => {
      captureFrameRef.current = requestAnimationFrame(() => {
        const currentSurface = pageContentRef.current;

        if (!currentSurface) {
          captureFrameRef.current = null;
          return;
        }

        const snapshot = currentSurface.cloneNode(true) as HTMLElement;
        const cache = previewCacheRef.current;

        cache.delete(pathname);
        cache.set(pathname, snapshot);
        trimPreviewCache(cache);
        captureFrameRef.current = null;
      });
    });

    return () => {
      if (captureFrameRef.current != null) {
        cancelAnimationFrame(captureFrameRef.current);
        captureFrameRef.current = null;
      }
    };
  }, [pathname]);

  useEffect(() => {
    return () => {
      if (captureFrameRef.current != null) {
        cancelAnimationFrame(captureFrameRef.current);
      }

      clearGestureSession();
    };
  }, []);

  return (
    <div
      ref={frameRef}
      className="native-swipe-back-frame"
      data-native-swipe-back-frame=""
      data-native-swipe-enabled={isNativeSwipeEnabled ? 'true' : 'false'}
      onTouchStart={handleTouchStart}
      onTouchMove={handleTouchMove}
      onTouchEnd={handleTouchEnd}
      onTouchCancel={() => cancelGesture(true)}
    >
      <div
        ref={underlayRef}
        className="native-swipe-back-frame__underlay"
        aria-hidden="true"
      >
        <div
          ref={underlaySurfaceRef}
          className="native-swipe-back-frame__underlay-surface"
          data-preview-state="fallback"
        />
        <div
          ref={scrimRef}
          className="native-swipe-back-frame__underlay-scrim"
        />
      </div>

      <div ref={pageRef} className="native-swipe-back-frame__page">
        <div
          ref={pageSurfaceRef}
          className="native-swipe-back-frame__page-surface"
        >
          <div
            ref={pageContentRef}
            className="native-swipe-back-frame__page-content"
          >
            {children}
          </div>
        </div>
        <div
          ref={shadowRef}
          className="native-swipe-back-frame__page-shadow"
          aria-hidden="true"
        />
      </div>
    </div>
  );
}
