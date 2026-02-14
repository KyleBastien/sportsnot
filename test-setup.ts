// Polyfill vanilla-extract file scope for tests that import @sportsnot/ui
import { setFileScope, endFileScope } from '@vanilla-extract/css/fileScope';
setFileScope('test');

// Polyfill for jsdom missing APIs needed by Mantine
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
});

// ResizeObserver polyfill for Mantine floating components (Tooltip, Popover)
class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as Record<string, unknown>).ResizeObserver = ResizeObserverMock;
