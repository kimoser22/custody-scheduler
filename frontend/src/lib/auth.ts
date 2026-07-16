const AUTH_TOKEN_KEY = "auth_token";

export const PARENT_TOKEN_PREFIX = "parent:";
export const VIEWER_TOKEN_PREFIX = "viewer:";

const PARENT_TOKEN_USER_IDS: Record<string, number> = {
  dev: 1,
  a: 101,
  b: 102,
};

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

export function setParentAToken(): void {
  setParentToken("a");
}

export function setParentBToken(): void {
  setParentToken("b");
}

export function setViewerToken(suffix = "dev"): void {
  setAuthToken(`${VIEWER_TOKEN_PREFIX}${suffix}`);
}

export function isParentToken(token: string | null): boolean {
  return token?.startsWith(PARENT_TOKEN_PREFIX) ?? false;
}

export function canRequestOverride(token: string | null): boolean {
  return isParentToken(token);
}

export function userIdFromToken(token: string | null): number | null {
  if (!token) {
    return null;
  }
  if (token.startsWith(VIEWER_TOKEN_PREFIX)) {
    return 2;
  }
  if (!token.startsWith(PARENT_TOKEN_PREFIX)) {
    return null;
  }
  const suffix = token.slice(PARENT_TOKEN_PREFIX.length);
  return PARENT_TOKEN_USER_IDS[suffix] ?? 1;
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
