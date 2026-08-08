/**
 * Security response headers for the served frontend.
 *
 * Kept as a pure function so it can be unit-tested and shared by
 * `next.config.ts`'s `headers()`. Mirrors the API's header set
 * (api/security_headers.py) so a browser gets consistent guarantees whichever
 * origin answered.
 *
 * On the Content-Security-Policy: a Next static export embeds inline RSC
 * bootstrap scripts (`self.__next_f`), so `script-src` must allow
 * `'unsafe-inline'` — a nonce-based policy would force every page to render
 * dynamically. What still delivers real protection without nonces is
 * `connect-src`: even if an inline script runs, it cannot POST a stolen
 * localStorage token to an attacker origin. `object-src`, `base-uri`,
 * `form-action`, and `frame-ancestors` close the other classic sinks.
 */

export interface SecurityHeader {
  key: string;
  value: string;
}

const HSTS = "max-age=63072000; includeSubDomains";

/** Extract just the origin from a configured API URL; null if unparseable. */
function apiOrigin(apiUrl: string | undefined): string | null {
  if (!apiUrl) {
    return null;
  }
  try {
    return new URL(apiUrl).origin;
  } catch {
    // A malformed value must not leak a broken token into the directive.
    return null;
  }
}

export function buildContentSecurityPolicy(apiUrl?: string): string {
  const origin = apiOrigin(apiUrl);
  const connectSrc = ["'self'", origin].filter(Boolean).join(" ");
  return [
    "default-src 'self'",
    // Next hydration needs inline; connect-src is what constrains exfiltration.
    "script-src 'self' 'unsafe-inline'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data:",
    `connect-src ${connectSrc}`,
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ].join("; ");
}

export function buildSecurityHeaders(apiUrl?: string): SecurityHeader[] {
  return [
    { key: "Content-Security-Policy", value: buildContentSecurityPolicy(apiUrl) },
    { key: "X-Frame-Options", value: "DENY" },
    { key: "X-Content-Type-Options", value: "nosniff" },
    { key: "Referrer-Policy", value: "no-referrer" },
    { key: "Strict-Transport-Security", value: HSTS },
  ];
}
