import { describe, expect, it } from "vitest";

import { buildSecurityHeaders } from "@/lib/securityHeaders";

function headerMap(apiUrl?: string): Record<string, string> {
  return Object.fromEntries(
    buildSecurityHeaders(apiUrl).map(({ key, value }) => [key, value]),
  );
}

describe("buildSecurityHeaders", () => {
  it("sets the robust static headers", () => {
    const h = headerMap();
    expect(h["X-Frame-Options"]).toBe("DENY");
    expect(h["X-Content-Type-Options"]).toBe("nosniff");
    expect(h["Referrer-Policy"]).toBe("no-referrer");
    expect(h["Strict-Transport-Security"]).toMatch(/^max-age=\d+/);
  });

  it("locks the directives a static Next export can enforce", () => {
    const csp = headerMap()["Content-Security-Policy"];
    // Clickjacking, base-tag injection, plugin/object injection, form hijack.
    expect(csp).toContain("frame-ancestors 'none'");
    expect(csp).toContain("object-src 'none'");
    expect(csp).toContain("base-uri 'self'");
    expect(csp).toContain("form-action 'self'");
  });

  it("never allows eval", () => {
    expect(headerMap()["Content-Security-Policy"]).not.toContain("unsafe-eval");
  });

  it("restricts connect-src to self so an injected script cannot POST the token out", () => {
    // The direct mitigation for localStorage token theft: even if an inline
    // script runs (Next needs 'unsafe-inline' for hydration), fetch/XHR/beacon
    // to an attacker origin is blocked.
    const csp = headerMap()["Content-Security-Policy"];
    const connect = csp
      .split(";")
      .map((d) => d.trim())
      .find((d) => d.startsWith("connect-src"));
    expect(connect).toBeDefined();
    expect(connect).toContain("'self'");
    expect(connect).not.toContain("*");
  });

  it("adds the API origin (not its path) to connect-src when configured", () => {
    const connect = headerMap("https://custody-scheduler-api.fly.dev/api/v1")
      ["Content-Security-Policy"].split(";")
      .map((d) => d.trim())
      .find((d) => d.startsWith("connect-src"));
    expect(connect).toContain("https://custody-scheduler-api.fly.dev");
    // Only the origin belongs in CSP, never the path.
    expect(connect).not.toContain("/api/v1");
  });

  it("ignores a malformed API url rather than emitting a broken directive", () => {
    const connect = headerMap("not-a-url")
      ["Content-Security-Policy"].split(";")
      .map((d) => d.trim())
      .find((d) => d.startsWith("connect-src"));
    expect(connect).toBe("connect-src 'self'");
  });
});
