export const ACCESS_TOKEN_STORAGE_KEY = 'accessToken';
export const AUTH_LAST_ACTIVITY_STORAGE_KEY = 'hefaistos.lastActivityAt';
export const AUTH_SESSION_TIMEOUT_STORAGE_KEY = 'hefaistos.sessionTimeoutHours';
export const AUTH_SESSION_CHANGED_EVENT = 'hefaistos:auth-session-changed';

export const SESSION_TIMEOUT_HOURS_OPTIONS = [2, 4, 8, 12, 24] as const;
export type SessionTimeoutHours = (typeof SESSION_TIMEOUT_HOURS_OPTIONS)[number];
export const DEFAULT_SESSION_TIMEOUT_HOURS: SessionTimeoutHours = 4;

const SESSION_TIMEOUT_HOURS_SET = new Set<number>(SESSION_TIMEOUT_HOURS_OPTIONS);

export const normalizeSessionTimeoutHours = (value: unknown): SessionTimeoutHours => {
  let parsed = Number(value);
  if (!Number.isFinite(parsed) && typeof value === 'string') {
    const match = value.match(/(\d+)/);
    if (match) {
      parsed = Number(match[1]);
    }
  }
  return SESSION_TIMEOUT_HOURS_SET.has(parsed)
    ? (parsed as SessionTimeoutHours)
    : DEFAULT_SESSION_TIMEOUT_HOURS;
};

export const getStoredAccessToken = (): string | null => {
  return localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY);
};

export const emitAuthSessionChanged = (reason: string) => {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new CustomEvent(AUTH_SESSION_CHANGED_EVENT, {
    detail: { reason, at: Date.now() },
  }));
};

export const setStoredAccessToken = (token: string, reason = 'login') => {
  localStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, token);
  emitAuthSessionChanged(reason);
};

export const clearStoredAccessToken = (reason = 'logout') => {
  localStorage.removeItem(ACCESS_TOKEN_STORAGE_KEY);
  emitAuthSessionChanged(reason);
};

export const getStoredSessionTimeoutHours = (): SessionTimeoutHours => {
  return normalizeSessionTimeoutHours(localStorage.getItem(AUTH_SESSION_TIMEOUT_STORAGE_KEY));
};

export const setStoredSessionTimeoutHours = (hours: unknown, reason = 'session-timeout-updated'): SessionTimeoutHours => {
  const normalized = normalizeSessionTimeoutHours(hours);
  localStorage.setItem(AUTH_SESSION_TIMEOUT_STORAGE_KEY, String(normalized));
  emitAuthSessionChanged(reason);
  return normalized;
};

export const getStoredLastActivityAt = (): number | null => {
  const raw = localStorage.getItem(AUTH_LAST_ACTIVITY_STORAGE_KEY);
  if (!raw) return null;
  const parsed = Number(raw);
  if (!Number.isFinite(parsed) || parsed <= 0) return null;
  return parsed;
};

export const setStoredLastActivityAt = (timestamp = Date.now()) => {
  localStorage.setItem(AUTH_LAST_ACTIVITY_STORAGE_KEY, String(timestamp));
};

export const clearStoredLastActivityAt = () => {
  localStorage.removeItem(AUTH_LAST_ACTIVITY_STORAGE_KEY);
};

export const inactivityTimeoutMs = (hours: unknown): number => {
  return normalizeSessionTimeoutHours(hours) * 60 * 60 * 1000;
};

export const getInactivityDeadline = (
  lastActivityAt = getStoredLastActivityAt() ?? Date.now(),
  timeoutHours: unknown = getStoredSessionTimeoutHours(),
): number => {
  return lastActivityAt + inactivityTimeoutMs(timeoutHours);
};

export const isInactivityExpired = (
  now = Date.now(),
  options?: {
    timeoutHours?: unknown;
    lastActivityAt?: number | null;
  },
): boolean => {
  const timeoutHours = options?.timeoutHours ?? getStoredSessionTimeoutHours();
  const timeoutMs = inactivityTimeoutMs(timeoutHours);
  const lastActivityAt = options?.lastActivityAt ?? getStoredLastActivityAt();
  if (!lastActivityAt || !Number.isFinite(lastActivityAt)) return false;
  return now - lastActivityAt >= timeoutMs;
};

export const isAuthenticationMessage = (message: unknown): boolean => {
  const text = String(message || '').toLowerCase();
  if (!text) return false;
  return [
    'authentication required',
    'authentication credentials were not provided',
    'not logged in',
    'not authenticated',
    'user is not authenticated',
    'invalid token',
    'signature has expired',
    'token is expired',
    'jwt expired',
  ].some(fragment => text.includes(fragment));
};
