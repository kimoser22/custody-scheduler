import { describe, expect, it, beforeEach } from "vitest";

import {
  IDENTITY_USER_IDS,
  canRequestOverride,
  clearSession,
  currentUserId,
  getAuthToken,
  getSession,
  login,
  setAuthToken,
} from "@/lib/auth";
import type { LoginOutcome } from "@/lib/api/auth";

describe("auth", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("reads and writes the raw auth token from localStorage", () => {
    setAuthToken("some.signed.token");
    expect(getAuthToken()).toBe("some.signed.token");
  });

  it("returns no session when nothing is stored", () => {
    expect(getSession()).toBeNull();
    expect(currentUserId(getSession())).toBeNull();
    expect(canRequestOverride(getSession())).toBe(false);
  });

  it("stores token, user id, and role on successful login", async () => {
    const fakeLogin = async (): Promise<LoginOutcome> => ({
      ok: true,
      status: 200,
      data: {
        access_token: "signed.parent.token",
        token_type: "bearer",
        user_id: 101,
        role: "Parent",
      },
    });

    const result = await login(101, "alpha-pass", fakeLogin);

    expect(result.ok).toBe(true);
    expect(getAuthToken()).toBe("signed.parent.token");
    const session = getSession();
    expect(session).toEqual({
      token: "signed.parent.token",
      userId: 101,
      role: "Parent",
    });
    expect(currentUserId(session)).toBe(101);
    expect(canRequestOverride(session)).toBe(true);
  });

  it("treats a Viewer session as unable to request overrides", async () => {
    const fakeLogin = async (): Promise<LoginOutcome> => ({
      ok: true,
      status: 200,
      data: {
        access_token: "signed.viewer.token",
        token_type: "bearer",
        user_id: 2,
        role: "Viewer",
      },
    });

    await login(2, "viewer-pass", fakeLogin);

    expect(canRequestOverride(getSession())).toBe(false);
  });

  it("does not store a session on failed login and surfaces the detail", async () => {
    const fakeLogin = async (): Promise<LoginOutcome> => ({
      ok: false,
      status: 401,
      detail: "Invalid credentials.",
    });

    const result = await login(101, "wrong", fakeLogin);

    expect(result.ok).toBe(false);
    expect(result.detail).toBe("Invalid credentials.");
    expect(getSession()).toBeNull();
    expect(getAuthToken()).toBeNull();
  });

  it("clears a stored session", async () => {
    setAuthToken("x");
    window.localStorage.setItem("auth_user_id", "101");
    window.localStorage.setItem("auth_role", "Parent");

    clearSession();

    expect(getSession()).toBeNull();
    expect(getAuthToken()).toBeNull();
  });

  it("maps demo identities to the backend user ids", () => {
    expect(IDENTITY_USER_IDS["Parent A"]).toBe(101);
    expect(IDENTITY_USER_IDS["Parent B"]).toBe(102);
    expect(IDENTITY_USER_IDS["Viewer"]).toBe(2);
  });
});
