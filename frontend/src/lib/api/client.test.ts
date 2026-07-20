import { describe, expect, it, beforeEach, afterEach, vi } from "vitest";

import { createApiClient } from "@/lib/api/client";
import { setAuthToken } from "@/lib/auth";

describe("createApiClient", () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.restoreAllMocks();
    vi.unstubAllEnvs();
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("attaches Authorization header when token is present", async () => {
    setAuthToken("parent:dev");

    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const request = new Request(input, init);
      return new Response(JSON.stringify([]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });

    vi.stubGlobal("fetch", fetchMock);

    const client = createApiClient("http://localhost:3000");
    await client.GET("/api/v1/schedule/", {
      params: { query: { start_date: "2026-01-01", end_date: "2026-01-14" } },
    });

    const request = fetchMock.mock.calls[0]?.[0] as Request;
    expect(request.url).toBe(
      "http://localhost:3000/api/v1/schedule/?start_date=2026-01-01&end_date=2026-01-14",
    );
    expect(request.url).not.toContain(":8000");
    expect(request.headers.get("Authorization")).toBe("parent:dev");
  });

  it("uses NEXT_PUBLIC_API_URL when createApiClient is called with no baseUrl", async () => {
    vi.stubEnv(
      "NEXT_PUBLIC_API_URL",
      "https://custody-scheduler-api.fly.dev",
    );

    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const request = new Request(input, init);
      return new Response(JSON.stringify([]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    const client = createApiClient();
    await client.GET("/api/v1/schedule/", {
      params: { query: { start_date: "2026-01-01", end_date: "2026-01-14" } },
    });

    const request = fetchMock.mock.calls[0]?.[0] as Request;
    expect(request.url).toBe(
      "https://custody-scheduler-api.fly.dev/api/v1/schedule/?start_date=2026-01-01&end_date=2026-01-14",
    );
    expect(request.url).not.toContain(":8000");
    expect(request.url).not.toContain("localhost:3000");
  });
});
