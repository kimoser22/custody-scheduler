import { describe, expect, it } from "vitest";

import { formatLocalDate, getMonthRange, shiftMonth } from "@/lib/calendar";

describe("calendar helpers", () => {
  it("formats local dates as YYYY-MM-DD without UTC shifting", () => {
    expect(formatLocalDate(new Date(2026, 6, 15))).toBe("2026-07-15");
  });

  it("returns the first and last day of the reference month", () => {
    expect(getMonthRange(new Date(2026, 6, 15))).toEqual({
      startDate: "2026-07-01",
      endDate: "2026-07-31",
    });
  });

  it("shifts from January to previous December", () => {
    const previous = shiftMonth(new Date(2026, 0, 15), -1);
    expect(getMonthRange(previous)).toEqual({
      startDate: "2025-12-01",
      endDate: "2025-12-31",
    });
  });

  it("shifts from January to next February", () => {
    const next = shiftMonth(new Date(2026, 0, 15), 1);
    expect(getMonthRange(next)).toEqual({
      startDate: "2026-02-01",
      endDate: "2026-02-28",
    });
  });
});
