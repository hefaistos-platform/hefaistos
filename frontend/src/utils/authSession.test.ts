import {
  AUTH_LAST_ACTIVITY_STORAGE_KEY,
  AUTH_SESSION_TIMEOUT_STORAGE_KEY,
  DEFAULT_SESSION_TIMEOUT_HOURS,
  getStoredSessionTimeoutHours,
  isInactivityExpired,
  normalizeSessionTimeoutHours,
  setStoredSessionTimeoutHours,
} from './authSession';

describe('authSession utils', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  test('normalizeSessionTimeoutHours keeps allowed values and falls back for invalid', () => {
    expect(normalizeSessionTimeoutHours(8)).toBe(8);
    expect(normalizeSessionTimeoutHours('12')).toBe(12);
    expect(normalizeSessionTimeoutHours('A_8')).toBe(8);
    expect(normalizeSessionTimeoutHours(6)).toBe(DEFAULT_SESSION_TIMEOUT_HOURS);
    expect(normalizeSessionTimeoutHours('abc')).toBe(DEFAULT_SESSION_TIMEOUT_HOURS);
  });

  test('setStoredSessionTimeoutHours stores normalized value', () => {
    setStoredSessionTimeoutHours(24);
    expect(getStoredSessionTimeoutHours()).toBe(24);

    setStoredSessionTimeoutHours(99);
    expect(localStorage.getItem(AUTH_SESSION_TIMEOUT_STORAGE_KEY)).toBe(String(DEFAULT_SESSION_TIMEOUT_HOURS));
  });

  test('isInactivityExpired compares against timeout correctly', () => {
    const now = Date.now();
    localStorage.setItem(AUTH_LAST_ACTIVITY_STORAGE_KEY, String(now - (4 * 60 * 60 * 1000) - 1));
    setStoredSessionTimeoutHours(4);
    expect(isInactivityExpired(now)).toBe(true);

    localStorage.setItem(AUTH_LAST_ACTIVITY_STORAGE_KEY, String(now - (4 * 60 * 60 * 1000) + 60_000));
    expect(isInactivityExpired(now)).toBe(false);
  });
});
