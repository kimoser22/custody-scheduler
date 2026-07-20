import { describe, expect, it } from "vitest";
import path from "node:path";

import { resolveOpenApiSource } from "./openapi-source";

const committed = path.join("openapi", "schema.json");

describe("resolveOpenApiSource", () => {
  it("uses committed schema.json when API_OPENAPI_URL is unset", () => {
    const source = resolveOpenApiSource({}, committed);
    expect(source).toEqual({ kind: "file", path: committed });
  });

  it("fetches API_OPENAPI_URL when set", () => {
    const source = resolveOpenApiSource(
      { API_OPENAPI_URL: "https://custody-scheduler-api.fly.dev/openapi.json" },
      committed,
    );
    expect(source).toEqual({
      kind: "url",
      url: "https://custody-scheduler-api.fly.dev/openapi.json",
    });
  });
});
