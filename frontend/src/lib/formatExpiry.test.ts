import { describe, expect, it } from "vitest";

import { formatExpiryLabel } from "@/lib/formatExpiry";

describe("formatExpiryLabel", () => {
  it("formats a future expiry with relative hours and UTC absolute", () => {
    const now = new Date("2026-01-16T10:00:00Z");
    expect(formatExpiryLabel("2026-01-16T12:00:00", now)).toBe(
      "Expires in 2 hours · 2026-01-16 12:00:00 UTC",
    );
  });

  it("formats already-past expiry", () => {
    const now = new Date("2026-01-16T13:00:00Z");
    expect(formatExpiryLabel("2026-01-16T12:00:00Z", now)).toBe(
      "Expired · 2026-01-16 12:00:00 UTC",
    );
  });
});
