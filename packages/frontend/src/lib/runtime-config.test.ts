import { afterEach, describe, expect, it, vi } from 'vitest';
import { AUTH_STORAGE_KEYS, clearBrowserSessionState } from './runtime-config';

function memoryStorage(initial: Record<string, string>): Storage {
  const values = new Map(Object.entries(initial));
  return {
    get length() {
      return values.size;
    },
    clear: () => values.clear(),
    getItem: (key) => values.get(key) ?? null,
    key: (index) => [...values.keys()][index] ?? null,
    removeItem: (key) => {
      values.delete(key);
    },
    setItem: (key, value) => {
      values.set(key, value);
    },
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('clearBrowserSessionState', () => {
  it('removes every browser session value while preserving unrelated preferences', () => {
    const localStorage = memoryStorage({
      [AUTH_STORAGE_KEYS.elderId]: 'synthetic-elder-id',
      [AUTH_STORAGE_KEYS.caregiverId]: 'synthetic-caregiver-id',
      elderly_care_locale: 'en',
    });
    vi.stubGlobal('window', { localStorage });

    clearBrowserSessionState();

    expect(localStorage.getItem(AUTH_STORAGE_KEYS.elderId)).toBeNull();
    expect(localStorage.getItem(AUTH_STORAGE_KEYS.caregiverId)).toBeNull();
    expect(localStorage.getItem('elderly_care_locale')).toBe('en');
  });

  it('is a no-op during server rendering', () => {
    vi.stubGlobal('window', undefined);
    expect(() => clearBrowserSessionState()).not.toThrow();
  });
});
