import React, { createContext, useState, useContext, useEffect, useCallback } from 'react';
import { gql } from '@apollo/client';
import { useApolloClient } from '@apollo/client/react';
import {
  ACCESS_TOKEN_STORAGE_KEY,
  AUTH_SESSION_CHANGED_EVENT,
  AUTH_SESSION_TIMEOUT_STORAGE_KEY,
  clearStoredAccessToken,
  clearStoredLastActivityAt,
  getInactivityDeadline,
  getStoredAccessToken,
  getStoredLastActivityAt,
  getStoredSessionTimeoutHours,
  isAuthenticationMessage,
  isInactivityExpired,
  setStoredAccessToken,
  setStoredLastActivityAt,
  setStoredSessionTimeoutHours,
} from '../utils/authSession';

const GET_MY_SESSION_TIMEOUT = gql`
  query GetMySessionTimeout {
    me {
      id
      sessionTimeoutHours
    }
  }
`;

interface AuthContextType {
  isAuthenticated: boolean;
  sessionTimeoutHours: number;
  updateSessionTimeoutHours: (hours: number) => void;
  login: (token: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const apolloClient = useApolloClient();
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(() => !!getStoredAccessToken());
  const [sessionTimeoutHours, setSessionTimeoutHours] = useState<number>(() => getStoredSessionTimeoutHours());

  const clearApolloStore = useCallback(async () => {
    try {
      const apollo: any = (window as any).__APOLLO_CLIENT__ || apolloClient;
      if (apollo && typeof apollo.clearStore === 'function') {
        await apollo.clearStore();
      }
    } catch {}
  }, [apolloClient]);

  const login = useCallback(async (token: string) => {
    setStoredAccessToken(token, 'login');
    setStoredLastActivityAt(Date.now());
    setIsAuthenticated(true);
    setSessionTimeoutHours(getStoredSessionTimeoutHours());
    await clearApolloStore();
  }, [clearApolloStore]);

  const logout = useCallback(async () => {
    clearStoredAccessToken('logout');
    clearStoredLastActivityAt();
    setIsAuthenticated(false);
    await clearApolloStore();
  }, [clearApolloStore]);

  const updateSessionTimeoutHours = useCallback((hours: number) => {
    const normalized = setStoredSessionTimeoutHours(hours, 'session-timeout-updated');
    setSessionTimeoutHours(normalized);
    setStoredLastActivityAt(Date.now());
  }, []);

  useEffect(() => {
    const syncFromStorage = () => {
      setIsAuthenticated(!!getStoredAccessToken());
      setSessionTimeoutHours(getStoredSessionTimeoutHours());
    };

    const handleStorage = (event: StorageEvent) => {
      if (!event.key || event.key === ACCESS_TOKEN_STORAGE_KEY || event.key === AUTH_SESSION_TIMEOUT_STORAGE_KEY) {
        syncFromStorage();
      }
    };

    const handleSessionChange = () => {
      syncFromStorage();
    };

    window.addEventListener('storage', handleStorage);
    window.addEventListener(AUTH_SESSION_CHANGED_EVENT, handleSessionChange as EventListener);
    return () => {
      window.removeEventListener('storage', handleStorage);
      window.removeEventListener(AUTH_SESSION_CHANGED_EVENT, handleSessionChange as EventListener);
    };
  }, []);

  useEffect(() => {
    if (!isAuthenticated) return;
    let cancelled = false;

    const syncProfileTimeout = async () => {
      try {
        const result = await apolloClient.query<{ me?: { sessionTimeoutHours?: number | null } }>({
          query: GET_MY_SESSION_TIMEOUT,
          fetchPolicy: 'network-only',
        });
        if (cancelled) return;
        const normalized = setStoredSessionTimeoutHours(
          result.data?.me?.sessionTimeoutHours,
          'session-timeout-synced',
        );
        setSessionTimeoutHours(normalized);
      } catch (error: any) {
        if (isAuthenticationMessage(error?.message)) {
          void logout();
        }
      }
    };

    void syncProfileTimeout();
    return () => {
      cancelled = true;
    };
  }, [apolloClient, isAuthenticated, logout]);

  useEffect(() => {
    if (!isAuthenticated) return;

    const timeoutRef: { current: ReturnType<typeof setTimeout> | null } = { current: null };
    const intervalRef: { current: ReturnType<typeof setInterval> | null } = { current: null };
    const lastResetRef: { current: number } = { current: 0 };

    const logoutIfExpired = () => {
      if (!isInactivityExpired(Date.now(), { timeoutHours: sessionTimeoutHours })) return false;
      void logout();
      return true;
    };

    const scheduleFromLastActivity = () => {
      if (timeoutRef.current !== null) clearTimeout(timeoutRef.current);

      const now = Date.now();
      const storedLastActivity = getStoredLastActivityAt();
      if (!storedLastActivity) {
        setStoredLastActivityAt(now);
      }

      const deadline = getInactivityDeadline(storedLastActivity ?? now, sessionTimeoutHours);
      const msUntilLogout = Math.max(0, deadline - now);
      timeoutRef.current = setTimeout(() => {
        void logout();
      }, msUntilLogout);
    };

    const resetTimer = () => {
      if (logoutIfExpired()) return;
      setStoredLastActivityAt(Date.now());
      scheduleFromLastActivity();
    };

    const throttledResetTimer = () => {
      const now = Date.now();
      if (now - lastResetRef.current < 10_000) return;
      lastResetRef.current = now;
      resetTimer();
    };

    const onVisibilityOrFocus = () => {
      if (document.visibilityState === 'hidden') return;
      if (logoutIfExpired()) return;
      scheduleFromLastActivity();
    };

    if (logoutIfExpired()) return;
    scheduleFromLastActivity();

    const highFreqEvents = ['mousemove', 'scroll'];
    const lowFreqEvents = ['mousedown', 'keydown', 'touchstart', 'click'];
    highFreqEvents.forEach((ev) => window.addEventListener(ev, throttledResetTimer, { passive: true }));
    lowFreqEvents.forEach((ev) => window.addEventListener(ev, resetTimer, { passive: true }));
    document.addEventListener('visibilitychange', onVisibilityOrFocus);
    window.addEventListener('focus', onVisibilityOrFocus);

    intervalRef.current = setInterval(() => {
      if (logoutIfExpired()) return;
      scheduleFromLastActivity();
    }, 60_000);

    return () => {
      if (timeoutRef.current !== null) clearTimeout(timeoutRef.current);
      if (intervalRef.current !== null) clearInterval(intervalRef.current);
      highFreqEvents.forEach((ev) => window.removeEventListener(ev, throttledResetTimer));
      lowFreqEvents.forEach((ev) => window.removeEventListener(ev, resetTimer));
      document.removeEventListener('visibilitychange', onVisibilityOrFocus);
      window.removeEventListener('focus', onVisibilityOrFocus);
    };
  }, [isAuthenticated, logout, sessionTimeoutHours]);

  return (
    <AuthContext.Provider value={{ isAuthenticated, sessionTimeoutHours, updateSessionTimeoutHours, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
