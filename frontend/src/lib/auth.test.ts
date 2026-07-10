import { describe, expect, it, beforeEach } from "vitest";

import {
  ensureAuthToken,
  getAuthToken,
  isParentToken,
  setAuthToken,
  setParentToken,
  setViewerToken,
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

  it("ensures a default viewer token when missing", () => {
    expect(ensureAuthToken()).toBe("viewer:dev");
  });
});
