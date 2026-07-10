const AUTH_TOKEN_KEY = "auth_token";

export const PARENT_TOKEN_PREFIX = "parent:";
export const VIEWER_TOKEN_PREFIX = "viewer:";

export function getAuthToken(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  return window.localStorage.getItem(AUTH_TOKEN_KEY);
}

export function setAuthToken(token: string): void {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(AUTH_TOKEN_KEY, token);
}

export function setParentToken(suffix = "dev"): void {
  setAuthToken(`${PARENT_TOKEN_PREFIX}${suffix}`);
}

export function setViewerToken(suffix = "dev"): void {
  setAuthToken(`${VIEWER_TOKEN_PREFIX}${suffix}`);
}

export function isParentToken(token: string | null): boolean {
  return token?.startsWith(PARENT_TOKEN_PREFIX) ?? false;
}

export function ensureAuthToken(): string {
  const existing = getAuthToken();
  if (existing) {
    return existing;
  }
  if (typeof window === "undefined") {
    return `${VIEWER_TOKEN_PREFIX}dev`;
  }
  setViewerToken();
  return getAuthToken() ?? `${VIEWER_TOKEN_PREFIX}dev`;
}
