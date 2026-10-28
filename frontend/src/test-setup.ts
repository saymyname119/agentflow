import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach, beforeEach } from 'vitest';

beforeEach(() => {
  window.history.replaceState(null, '', '/#/workspace');
  vi.spyOn(window, 'scrollTo').mockImplementation(() => {});
  // Observe persistence attempts without relying on Node's experimental Web Storage.
  for (const name of ['localStorage', 'sessionStorage'])
    vi.stubGlobal(name, {
      setItem: vi.fn(),
      getItem: vi.fn(),
      removeItem: vi.fn(),
      clear: vi.fn(),
      length: 0,
    });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});
