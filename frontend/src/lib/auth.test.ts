import { describe, expect, it, beforeEach } from "vitest";

import {
  canRequestOverride,
  ensureAuthToken,
  getAuthToken,
  isParentToken,
  setAuthToken,
  setParentAToken,
  setParentBToken,
  setParentToken,
  setViewerToken,
  userIdFromToken,
} from "@/lib/auth";

describe("auth", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("reads and writes auth token from localStorage", () => {
    setAuthToken("viewer:dev");
    expect(getAuthToken()).toBe("viewer:dev");
  });

  it("sets parent and viewer dev tokens", () => {
    setParentToken();
    expect(getAuthToken()).toBe("parent:dev");
    expect(isParentToken(getAuthToken())).toBe(true);

    setViewerToken();
    expect(getAuthToken()).toBe("viewer:dev");
    expect(isParentToken(getAuthToken())).toBe(false);
  });

  it("sets Parent A and Parent B persona tokens", () => {
    setParentAToken();
    expect(getAuthToken()).toBe("parent:a");
    expect(isParentToken(getAuthToken())).toBe(true);

    setParentBToken();
    expect(getAuthToken()).toBe("parent:b");
    expect(isParentToken(getAuthToken())).toBe(true);
  });

  it("maps tokens to stable user ids matching the backend", () => {
    expect(userIdFromToken("parent:a")).toBe(101);
    expect(userIdFromToken("parent:b")).toBe(102);
    expect(userIdFromToken("parent:dev")).toBe(1);
    expect(userIdFromToken("viewer:dev")).toBe(2);
    expect(userIdFromToken(null)).toBeNull();
  });

  it("allows only parent tokens to request overrides", () => {
    expect(canRequestOverride("parent:a")).toBe(true);
    expect(canRequestOverride("parent:b")).toBe(true);
    expect(canRequestOverride("viewer:dev")).toBe(false);
    expect(canRequestOverride(null)).toBe(false);
  });

  it("ensures a default viewer token when missing", () => {
    expect(ensureAuthToken()).toBe("viewer:dev");
  });
});
