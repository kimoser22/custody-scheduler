"""Security response headers on the API.

The API returns JSON and ICS to programmatic clients and the SPA, so the
strictest CSP applies (default-src 'none') — those responses load no
sub-resources. The interactive docs are the one exception: Swagger UI is HTML
that pulls a CDN bundle and runs inline scripts, so the strict CSP would break
it. Everything else (framing, sniffing, referrer, HSTS) applies everywhere.
"""

from fastapi.testclient import TestClient

from api.security_headers import security_headers_for
from main import app

_ALWAYS = {
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}


def test_helper_sets_strict_csp_for_api_responses() -> None:
    headers = security_headers_for("/api/v1/health")
    csp = headers["Content-Security-Policy"]
    assert "default-src 'none'" in csp
    assert "frame-ancestors 'none'" in csp
    for key, value in _ALWAYS.items():
        assert headers[key] == value
    assert headers["Strict-Transport-Security"].startswith("max-age=")


def test_helper_omits_csp_for_docs_but_keeps_the_rest() -> None:
    """A default-src 'none' CSP would break Swagger UI's CDN bundle and inline
    scripts; the other protections still apply to the docs routes."""
    for path in ("/docs", "/redoc", "/openapi.json"):
        headers = security_headers_for(path)
        assert "Content-Security-Policy" not in headers
        assert headers["X-Frame-Options"] == "DENY"
        assert headers["X-Content-Type-Options"] == "nosniff"


def test_health_response_carries_the_headers(client_fixture: TestClient) -> None:
    response = client_fixture.get("/api/v1/health")
    assert response.status_code == 200
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert "default-src 'none'" in response.headers["Content-Security-Policy"]
    assert response.headers["Strict-Transport-Security"].startswith("max-age=")


def test_headers_present_even_on_error_responses(client_fixture: TestClient) -> None:
    """A 401 still frames the browser's trust decisions, so the headers must
    ride on failures too, not only 200s."""
    response = client_fixture.get("/api/v1/schedule/")  # unauthenticated -> 401
    assert response.status_code == 401
    assert response.headers["X-Frame-Options"] == "DENY"


def test_existing_cors_and_content_are_untouched(client_fixture: TestClient) -> None:
    """Adding headers must not disturb the response body or its content type."""
    response = client_fixture.get("/api/v1/health")
    assert response.json() == {"status": "ok"}
    assert response.headers["content-type"].startswith("application/json")
