import { describe, expect, it } from "vitest";

import {
  addDays,
  formatLocalDate,
  getMonthRange,
  localTodayDate,
  shiftMonth,
} from "@/lib/calendar";

describe("calendar helpers", () => {
  it("formats local dates as YYYY-MM-DD without UTC shifting", () => {
    expect(formatLocalDate(new Date(2026, 6, 15))).toBe("2026-07-15");
  });

  it("returns local today without UTC shifting", () => {
    expect(localTodayDate(new Date(2026, 7, 7, 23, 30))).toBe("2026-08-07");
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

  it("addDays rolls across month and year boundaries", () => {
    expect(addDays("2026-01-31", 1)).toBe("2026-02-01");
    expect(addDays("2026-12-31", 1)).toBe("2027-01-01");
    expect(addDays("2026-08-10", 45)).toBe("2026-09-24");
  });

  it("addDays stays on local calendar parts across a DST spring-forward day", () => {
    // US DST spring-forward 2026-03-08; calendar add must not skip a civil day.
    expect(addDays("2026-03-07", 1)).toBe("2026-03-08");
    expect(addDays("2026-03-08", 1)).toBe("2026-03-09");
  });
});
