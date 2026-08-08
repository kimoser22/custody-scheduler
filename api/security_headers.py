"""Security response headers for the API.

Kept as a pure ``security_headers_for(path)`` helper plus a thin middleware so
the policy is unit-testable without spinning up the app. Mirrors the frontend's
header set (see frontend/src/lib/securityHeaders.ts); the two are intentionally
consistent so a browser gets the same guarantees whichever origin answers.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.requests import Request
from starlette.responses import Response

# Two years, matching a submittable HSTS preload policy. force_https already
# redirects at the Fly edge; HSTS closes the first-request SSL-strip window.
_HSTS = "max-age=63072000; includeSubDomains"

# The API serves JSON and ICS — responses that pull no sub-resources — so the
# tightest policy is correct. frame-ancestors/base-uri are belt-and-suspenders
# alongside X-Frame-Options.
_API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"

# Swagger UI / ReDoc are HTML that load a CDN bundle and run inline scripts, so
# the strict CSP would break them. Everything else still applies.
_CSP_EXEMPT_PREFIXES = ("/docs", "/redoc", "/openapi.json")


def security_headers_for(path: str) -> dict[str, str]:
    headers = {
        "X-Frame-Options": "DENY",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "Strict-Transport-Security": _HSTS,
    }
    if not path.startswith(_CSP_EXEMPT_PREFIXES):
        headers["Content-Security-Policy"] = _API_CSP
    return headers


async def security_headers_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    response = await call_next(request)
    for key, value in security_headers_for(request.url.path).items():
        # Never clobber a header a handler set deliberately.
        response.headers.setdefault(key, value)
    return response
