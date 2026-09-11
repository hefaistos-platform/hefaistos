const trimTrailingSlash = (value: string): string => value.replace(/\/+$/, '');

const normalizeApiBaseUrl = (value: string): string => {
  const trimmed = trimTrailingSlash(value.trim());
  if (trimmed.endsWith('/graphql')) {
    return trimTrailingSlash(trimmed.slice(0, -'/graphql'.length));
  }
  return trimmed;
};

const readNodeEnv = (key: string): string | undefined => {
  if (typeof process === 'undefined' || !process.env) {
    return undefined;
  }
  return process.env[key];
};

const readEnv = (viteKey: string, legacyKey: string): string | undefined => {
  return readNodeEnv(viteKey) || readNodeEnv(legacyKey);
};

export const isDevEnvironment = (): boolean => {
  const mode = readNodeEnv('NODE_ENV');
  return !mode || mode === 'development' || mode === 'test';
};

export const getApiBaseUrl = (): string => {
  const configured = readEnv('VITE_API_URL', 'REACT_APP_API_URL');
  if (configured && configured.trim().length > 0) {
    return normalizeApiBaseUrl(configured);
  }
  return typeof window !== 'undefined' ? trimTrailingSlash(window.location.origin) : '';
};

export const getNavigatorBaseUrl = (): string | undefined => {
  const configured = readEnv('VITE_NAVIGATOR_URL', 'REACT_APP_NAVIGATOR_URL');
  if (configured && configured.trim().length > 0) {
    return configured;
  }
  return undefined;
};
