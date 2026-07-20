import { type LoginOutcome, loginRequest } from "@/lib/api/auth";

const AUTH_TOKEN_KEY = "auth_token";
const AUTH_USER_ID_KEY = "auth_user_id";
const AUTH_ROLE_KEY = "auth_role";

export const PARENT_ROLE = "Parent";

/** Demo identities the auth bar offers, mapped to the backend user ids. */
export const IDENTITY_USER_IDS = {
  Viewer: 2,
  "Parent A": 101,
  "Parent B": 102,
} as const;

export type Identity = keyof typeof IDENTITY_USER_IDS;

export interface Session {
  token: string;
  userId: number;
  role: string;
}

export function getAuthToken(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  return window.localStorage.getItem(AUTH_TOKEN_KEY);
}

/** Low-level setter used by the API client tests; prefer login() in app code. */
export function setAuthToken(token: string): void {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(AUTH_TOKEN_KEY, token);
}

export function getSession(): Session | null {
  if (typeof window === "undefined") {
    return null;
  }
  const token = window.localStorage.getItem(AUTH_TOKEN_KEY);
  const userIdRaw = window.localStorage.getItem(AUTH_USER_ID_KEY);
  const role = window.localStorage.getItem(AUTH_ROLE_KEY);
  if (!token || !userIdRaw || !role) {
    return null;
  }
  const userId = Number(userIdRaw);
  if (!Number.isFinite(userId)) {
    return null;
  }
  return { token, userId, role };
}

function storeSession(session: Session): void {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(AUTH_TOKEN_KEY, session.token);
  window.localStorage.setItem(AUTH_USER_ID_KEY, String(session.userId));
  window.localStorage.setItem(AUTH_ROLE_KEY, session.role);
}

export function clearSession(): void {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.removeItem(AUTH_TOKEN_KEY);
  window.localStorage.removeItem(AUTH_USER_ID_KEY);
  window.localStorage.removeItem(AUTH_ROLE_KEY);
}

export function currentUserId(session: Session | null): number | null {
  return session?.userId ?? null;
}

export function canRequestOverride(session: Session | null): boolean {
  return session?.role === PARENT_ROLE;
}

export type LoginFn = (userId: number, passcode: string) => Promise<LoginOutcome>;

export interface LoginResult {
  ok: boolean;
  detail?: string;
  session?: Session;
}

export async function login(
  userId: number,
  passcode: string,
  loginFn: LoginFn = loginRequest,
): Promise<LoginResult> {
  const outcome = await loginFn(userId, passcode);
  if (!outcome.ok || !outcome.data) {
    return { ok: false, detail: outcome.detail ?? "Invalid credentials." };
  }
  const session: Session = {
    token: outcome.data.access_token,
    userId: outcome.data.user_id,
    role: outcome.data.role,
  };
  storeSession(session);
  return { ok: true, session };
}
