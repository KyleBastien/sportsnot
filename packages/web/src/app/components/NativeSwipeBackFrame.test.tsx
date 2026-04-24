import { afterEach, describe, expect, it } from '@rstest/core';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import React, { useLayoutEffect, type ReactNode } from 'react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { NativeSwipeBackFrame } from './NativeSwipeBackFrame';

interface RuntimeWindow extends Window {
  CapacitorCustomPlatform?: { name: string };
}

function setRuntimePlatform(platform: 'ios' | 'android' | null) {
  const runtimeWindow = window as RuntimeWindow;

  if (platform) {
    runtimeWindow.CapacitorCustomPlatform = { name: platform };
    return;
  }

  delete runtimeWindow.CapacitorCustomPlatform;
}

function dispatchTouch(
  element: HTMLElement,
  type: 'touchstart' | 'touchmove' | 'touchend',
  touches: Array<{ clientX: number; clientY: number }>
) {
  const event = new Event(type, {
    bubbles: true,
    cancelable: true,
  });

  const touchList = touches.map((touch, index) => ({
    identifier: index,
    target: element,
    clientX: touch.clientX,
    clientY: touch.clientY,
    pageX: touch.clientX,
    pageY: touch.clientY,
    screenX: touch.clientX,
    screenY: touch.clientY,
  }));

  Object.defineProperties(event, {
    touches: {
      value: type === 'touchend' ? [] : touchList,
    },
    targetTouches: {
      value: type === 'touchend' ? [] : touchList,
    },
    changedTouches: {
      value: touchList,
    },
  });

  fireEvent(element, event);
}

async function waitForFrame() {
  await new Promise<void>((resolve) => {
    requestAnimationFrame(() => resolve());
  });
}

function renderHarness(
  initialEntries: string[],
  profileContent: ReactNode = <div>Profile</div>
) {
  render(
    <MemoryRouter initialEntries={initialEntries}>
      <NativeSwipeBackFrame>
        <Routes>
          <Route path="/" element={<div>Dashboard</div>} />
          <Route path="/profile" element={profileContent} />
          <Route path="/draft/:leagueId" element={<div>Draft</div>} />
        </Routes>
      </NativeSwipeBackFrame>
    </MemoryRouter>
  );

  return screen.getByText(
    initialEntries[0] === '/profile' ? 'Profile' : 'Dashboard'
  );
}

afterEach(() => {
  cleanup();
  setRuntimePlatform(null);
});

describe('NativeSwipeBackFrame', () => {
  it('enables swipe frame on native iOS', () => {
    setRuntimePlatform('ios');
    renderHarness(['/profile']);

    expect(
      document
        .querySelector('[data-native-swipe-back-frame]')
        ?.getAttribute('data-native-swipe-enabled')
    ).toBe('true');
  });

  it('enables swipe frame on native Android', () => {
    setRuntimePlatform('android');
    renderHarness(['/profile']);

    expect(
      document
        .querySelector('[data-native-swipe-back-frame]')
        ?.getAttribute('data-native-swipe-enabled')
    ).toBe('true');
  });

  it('keeps swipe frame disabled on web', () => {
    renderHarness(['/profile']);

    expect(
      document
        .querySelector('[data-native-swipe-back-frame]')
        ?.getAttribute('data-native-swipe-enabled')
    ).toBe('false');
  });

  it('does not re-render route content during drag updates', async () => {
    setRuntimePlatform('ios');

    let commitCount = 0;

    function RenderCounter({ onCommit }: { onCommit: () => void }) {
      useLayoutEffect(() => {
        onCommit();
      }, [onCommit]);

      return <div>Profile</div>;
    }

    renderHarness(
      ['/profile'],
      <RenderCounter
        onCommit={() => {
          commitCount += 1;
        }}
      />
    );

    const frame = document.querySelector(
      '[data-native-swipe-back-frame]'
    ) as HTMLElement | null;

    if (!frame) {
      throw new Error('Native swipe frame not found');
    }

    dispatchTouch(frame, 'touchstart', [{ clientX: 12, clientY: 80 }]);
    dispatchTouch(frame, 'touchmove', [{ clientX: 96, clientY: 84 }]);
    await waitForFrame();

    expect(commitCount).toBe(1);
  });
});
