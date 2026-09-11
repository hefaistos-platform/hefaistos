// src/setupTests.ts
import '@testing-library/jest-dom';
import { TextDecoder, TextEncoder } from 'util';
// Keep setup minimal; avoid mocking ESM-only modules globally to prevent Jest resolution issues.

// Mock window.matchMedia which is not available in jsdom but required by Ant Design.
// The implementation needs to return a valid MediaQueryList object with `matches`.
const mockMatchMedia = (query: string) => ({
  matches: false,
  media: query,
  onchange: null,
  addListener: jest.fn(), // deprecated but still used by antd
  removeListener: jest.fn(),
  addEventListener: jest.fn(),
  removeEventListener: jest.fn(),
  dispatchEvent: jest.fn(),
});

Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: mockMatchMedia,
});

Object.defineProperty(global, 'TextEncoder', {
  writable: true,
  value: TextEncoder,
});

Object.defineProperty(global, 'TextDecoder', {
  writable: true,
  value: TextDecoder,
});

class MockResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

Object.defineProperty(global, 'ResizeObserver', {
  writable: true,
  value: MockResizeObserver,
});
